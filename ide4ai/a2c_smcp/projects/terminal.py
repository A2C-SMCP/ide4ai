"""Project-scoped lifecycle management for embedded TFBash runtimes."""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, cast

import anyio
from mcp.types import CallToolResult, Tool
from tfbash_mcp import EmbeddedShellConfig, EmbeddedShellRuntime  # type: ignore[import-untyped]

from ide4ai.a2c_smcp.projects.errors import ProjectError
from ide4ai.a2c_smcp.projects.models import Project


class ProjectTerminalNotAvailableError(ProjectError):
    """The selected project's embedded terminal runtime is not open."""


class ProjectTerminalState(str, Enum):
    """Agent-visible lifecycle states for one project's TFBash runtime."""

    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    FAILED = "failed"


class EmbeddedTerminalRuntime(Protocol):
    """The public subset of TFBash used by the project host."""

    def list_tools(self) -> tuple[Tool, ...]: ...

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object] | None = None,
    ) -> CallToolResult: ...

    async def aclose(self) -> None: ...


TerminalRuntimeFactory = Callable[[Project], Awaitable[EmbeddedTerminalRuntime]]


async def create_embedded_terminal_runtime(project: Project) -> EmbeddedTerminalRuntime:
    """Create the official TFBash 0.2 runtime for one canonical project root."""

    return cast(
        EmbeddedTerminalRuntime,
        await EmbeddedShellRuntime.create(
            EmbeddedShellConfig(
                workspace_root=project.root_dir,
                default_cwd=project.root_dir,
            )
        ),
    )


@dataclass(slots=True)
class _ProjectTerminalEntry:
    project: Project
    operation_lock: anyio.Lock = field(default_factory=anyio.Lock)
    state: ProjectTerminalState = ProjectTerminalState.CLOSED
    runtime: EmbeddedTerminalRuntime | None = None
    failure: str | None = None
    retired: bool = False


class ProjectTerminalRuntimeManager:
    """Own one independently switchable embedded TFBash runtime per project."""

    def __init__(self, runtime_factory: TerminalRuntimeFactory = create_embedded_terminal_runtime) -> None:
        self._runtime_factory = runtime_factory
        self._entries: dict[object, _ProjectTerminalEntry] = {}
        self._lock = threading.RLock()
        self._shutdown_started = False

    def state(self, project: Project) -> ProjectTerminalState:
        with self._lock:
            entry = self._entries.get(project.id)
            return ProjectTerminalState.CLOSED if entry is None else entry.state

    def failure(self, project: Project) -> str | None:
        with self._lock:
            entry = self._entries.get(project.id)
            return None if entry is None else entry.failure

    def requires_disable(self, project: Project) -> bool:
        """Return whether the next state action must close or finish closing a runtime."""

        with self._lock:
            entry = self._entries.get(project.id)
            return entry is not None and (
                entry.runtime is not None
                or entry.state
                in (ProjectTerminalState.OPENING, ProjectTerminalState.OPEN, ProjectTerminalState.CLOSING)
            )

    def list_tools(self, project: Project) -> tuple[Tool, ...]:
        runtime = self._open_runtime(project)
        if runtime is None:
            return ()
        try:
            return runtime.list_tools()
        except RuntimeError:
            return ()

    async def set_enabled(self, project: Project, *, enabled: bool) -> bool:
        """Open or close a project's runtime, returning whether availability changed."""

        with self._lock:
            if enabled and self._shutdown_started:
                raise ProjectTerminalNotAvailableError("Terminal manager shutdown has started")
            entry = self._entries.get(project.id)
            if entry is None:
                entry = _ProjectTerminalEntry(project=project)
                self._entries[project.id] = entry
        async with entry.operation_lock:
            if enabled:
                if entry.retired:
                    raise ProjectTerminalNotAvailableError(
                        f"Terminal runtime belongs to a deleted project: {project.name}"
                    )
                return await self._enable(entry)
            return await self._disable(entry)

    async def call_tool(
        self,
        project: Project,
        name: str,
        arguments: Mapping[str, object],
    ) -> CallToolResult:
        runtime = self._open_runtime(project)
        if runtime is None:
            raise ProjectTerminalNotAvailableError(f"Terminal is not enabled for project: {project.name}")
        try:
            return await runtime.call_tool(name, arguments)
        except RuntimeError as exc:
            raise ProjectTerminalNotAvailableError(
                f"Terminal is closing or closed for project: {project.name}"
            ) from exc

    async def remove(self, project: Project) -> bool:
        """Permanently retire and close a deleted project's runtime."""

        entry = self._entry(project)
        async with entry.operation_lock:
            with self._lock:
                entry.retired = True
            return await self._disable(entry)

    async def aclose_all(self) -> None:
        """Close every runtime, retrying failed TFBash cleanup on later calls."""

        errors: list[BaseException] = []
        with anyio.CancelScope(shield=True):
            with self._lock:
                self._shutdown_started = True
                entries = tuple(self._entries.values())
            for entry in entries:
                try:
                    async with entry.operation_lock:
                        await self._disable(entry)
                except BaseException as exc:
                    errors.append(exc)
        if errors:
            cancelled_class = anyio.get_cancelled_exc_class()
            if isinstance(errors[0], cancelled_class):
                raise errors[0]
            raise ProjectError(f"Failed to close {len(errors)} project Terminal runtime(s)") from errors[0]

    @property
    def has_live_runtimes(self) -> bool:
        with self._lock:
            return any(entry.runtime is not None for entry in self._entries.values())

    def prepare_sync_close(self) -> None:
        """Atomically stop new enables and reject close while async work remains."""

        with self._lock:
            self._shutdown_started = True
            requires_async_close = any(
                entry.runtime is not None or entry.state in (ProjectTerminalState.OPENING, ProjectTerminalState.CLOSING)
                for entry in self._entries.values()
            )
        if requires_async_close:
            raise ProjectError("Enabled or transitioning Terminal runtimes require 'await server.aclose()'")

    def _entry(self, project: Project) -> _ProjectTerminalEntry:
        with self._lock:
            entry = self._entries.get(project.id)
            if entry is None:
                entry = _ProjectTerminalEntry(project=project)
                self._entries[project.id] = entry
            return entry

    def _open_runtime(self, project: Project) -> EmbeddedTerminalRuntime | None:
        with self._lock:
            entry = self._entries.get(project.id)
            if entry is None or entry.state is not ProjectTerminalState.OPEN:
                return None
            return entry.runtime

    async def _enable(self, entry: _ProjectTerminalEntry) -> bool:
        with self._lock:
            if self._shutdown_started:
                raise ProjectTerminalNotAvailableError("Terminal manager shutdown has started")
            if entry.retired:
                raise ProjectTerminalNotAvailableError(
                    f"Terminal runtime belongs to a deleted project: {entry.project.name}"
                )
            if entry.state is ProjectTerminalState.OPEN:
                return False
            if entry.runtime is not None:
                raise ProjectError(f"Terminal cleanup must succeed before reopening project: {entry.project.name}")
            entry.state = ProjectTerminalState.OPENING
            entry.failure = None
        try:
            runtime = await self._runtime_factory(entry.project)
        except BaseException as exc:
            with self._lock:
                entry.state = ProjectTerminalState.FAILED
                entry.failure = str(exc)
            raise
        with self._lock:
            entry.runtime = runtime
            entry.state = ProjectTerminalState.OPEN
            shutdown_started = self._shutdown_started
        if shutdown_started:
            await self._disable(entry)
            raise ProjectTerminalNotAvailableError("Terminal manager shutdown has started")
        return True

    async def _disable(self, entry: _ProjectTerminalEntry) -> bool:
        with self._lock:
            runtime = entry.runtime
            if runtime is None:
                changed = entry.state is not ProjectTerminalState.CLOSED
                entry.state = ProjectTerminalState.CLOSED
                entry.failure = None
                return changed
            was_open = entry.state is ProjectTerminalState.OPEN
            entry.state = ProjectTerminalState.CLOSING
            entry.failure = None
        try:
            await runtime.aclose()
        except BaseException as exc:
            with self._lock:
                entry.state = ProjectTerminalState.FAILED
                entry.failure = str(exc)
            raise
        with self._lock:
            entry.runtime = None
            entry.state = ProjectTerminalState.CLOSED
        return was_open
