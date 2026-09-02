"""Project-scoped lifecycle management for embedded TFBash runtimes."""

from __future__ import annotations

import os
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, cast

import anyio
from mcp.types import CallToolResult, Tool
from tfbash_mcp import EmbeddedShellConfig, EmbeddedShellRuntime  # type: ignore[import-untyped]

from ide4ai.a2c_smcp.projects.errors import ProjectError
from ide4ai.a2c_smcp.projects.models import Project

MAX_TERMINAL_CLOSE_DEADLINE_MS = 60_000


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


@dataclass(frozen=True, slots=True)
class TerminalStartOptions:
    """Validated, project-scoped inputs for one embedded Terminal runtime."""

    cwd: str | None = None
    startup_command: str | None = None
    shell: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    command_timeout_ms: int = 120_000
    shutdown_grace_ms: int = 3_000
    close_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if self.startup_command is not None and (not self.startup_command or "\x00" in self.startup_command):
            raise ValueError("startup_command must be non-empty and NUL-free")
        if self.shell is not None and (not self.shell or "\x00" in self.shell):
            raise ValueError("shell must be non-empty and NUL-free")
        if not 1 <= self.command_timeout_ms <= 86_400_000:
            raise ValueError("command_timeout_ms must be between 1 and 86400000")
        if not 1 <= self.shutdown_grace_ms <= MAX_TERMINAL_CLOSE_DEADLINE_MS:
            raise ValueError("shutdown_grace_ms must be between 1 and 60000")
        if not 1 <= self.close_timeout_ms <= MAX_TERMINAL_CLOSE_DEADLINE_MS:
            raise ValueError("close_timeout_ms must be between 1 and 60000")
        if self.close_timeout_ms <= self.shutdown_grace_ms:
            raise ValueError("close_timeout_ms must exceed shutdown_grace_ms")
        environment = dict(self.environment)
        if any(
            not isinstance(key, str) or not isinstance(value, str) or not key or "\x00" in key or "\x00" in value
            for key, value in environment.items()
        ):
            raise ValueError("environment keys must be non-empty and all values must be NUL-free strings")
        object.__setattr__(self, "environment", MappingProxyType(environment))

    def resolve_for(self, project: Project) -> TerminalStartOptions:
        """Resolve cwd within the immutable project root without widening its boundary."""

        root = Path(project.root_dir).resolve(strict=True)
        cwd = Path(self.cwd).resolve(strict=True) if self.cwd is not None else root
        if not cwd.is_dir():
            raise ValueError("cwd must be an existing directory")
        try:
            cwd.relative_to(root)
        except ValueError as exc:
            raise ValueError("cwd must be within the current project root") from exc
        return TerminalStartOptions(
            cwd=str(cwd),
            startup_command=self.startup_command,
            shell=self.shell,
            environment=self.environment,
            command_timeout_ms=self.command_timeout_ms,
            shutdown_grace_ms=self.shutdown_grace_ms,
            close_timeout_ms=self.close_timeout_ms,
        )

    def public_summary(self) -> dict[str, object]:
        """Return effective non-secret configuration safe for MCP responses."""

        return {
            "cwd": self.cwd,
            "shell": self.shell,
            "startup_command_configured": self.startup_command is not None,
            "environment_override_count": len(self.environment),
            "command_timeout_ms": self.command_timeout_ms,
            "shutdown_grace_ms": self.shutdown_grace_ms,
            "close_timeout_ms": self.close_timeout_ms,
        }


@dataclass(frozen=True, slots=True)
class TerminalTransitionResult:
    """Stable result captured while the per-project operation lock is held."""

    changed: bool
    state: ProjectTerminalState
    configuration: TerminalStartOptions | None


TerminalRuntimeFactory = Callable[[Project, TerminalStartOptions], Awaitable[EmbeddedTerminalRuntime]]


async def create_embedded_terminal_runtime(
    project: Project,
    options: TerminalStartOptions,
) -> EmbeddedTerminalRuntime:
    """Create the official TFBash 0.2 runtime for one canonical project root."""

    environment = dict(os.environ)
    environment.update(options.environment)
    return cast(
        EmbeddedTerminalRuntime,
        await EmbeddedShellRuntime.create(
            EmbeddedShellConfig(
                workspace_root=project.root_dir,
                default_cwd=options.cwd,
                shell=options.shell,
                startup_command=options.startup_command,
                environment=environment,
                command_timeout_ms=options.command_timeout_ms,
                shutdown_grace_ms=options.shutdown_grace_ms,
                close_timeout_ms=options.close_timeout_ms,
            )
        ),
    )


@dataclass(slots=True)
class _ProjectTerminalEntry:
    project: Project
    operation_lock: anyio.Lock = field(default_factory=anyio.Lock)
    state: ProjectTerminalState = ProjectTerminalState.CLOSED
    runtime: EmbeddedTerminalRuntime | None = None
    configuration: TerminalStartOptions | None = None
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

    def requires_close(self, project: Project) -> bool:
        """Return whether the only safe convergence action is Terminal close."""

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

    async def start(
        self,
        project: Project,
        options: TerminalStartOptions,
    ) -> TerminalTransitionResult:
        """Converge one project's Terminal to open without toggle semantics."""

        resolved = options.resolve_for(project)
        with self._lock:
            if self._shutdown_started:
                raise ProjectTerminalNotAvailableError("Terminal manager shutdown has started")
            entry = self._entries.get(project.id)
            if entry is None:
                entry = _ProjectTerminalEntry(project=project)
                self._entries[project.id] = entry
        async with entry.operation_lock:
            if entry.retired:
                raise ProjectTerminalNotAvailableError(f"Terminal runtime belongs to a deleted project: {project.name}")
            return await self._start(entry, resolved)

    async def close(self, project: Project) -> TerminalTransitionResult:
        """Converge one project's Terminal to closed with retryable cleanup."""

        entry = self._entry(project)
        async with entry.operation_lock:
            return await self._close(entry)

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
            try:
                return (await self._close(entry)).changed
            except BaseException:
                with self._lock:
                    entry.retired = False
                raise

    def cancel_remove(self, project: Project) -> None:
        """Restore a closed entry when the owning project deletion is rolled back."""

        with self._lock:
            entry = self._entries.get(project.id)
            if entry is not None:
                entry.retired = False

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
                        await self._close(entry)
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

    async def _start(
        self,
        entry: _ProjectTerminalEntry,
        configuration: TerminalStartOptions,
    ) -> TerminalTransitionResult:
        with self._lock:
            if self._shutdown_started:
                raise ProjectTerminalNotAvailableError("Terminal manager shutdown has started")
            if entry.retired:
                raise ProjectTerminalNotAvailableError(
                    f"Terminal runtime belongs to a deleted project: {entry.project.name}"
                )
            if entry.state is ProjectTerminalState.OPEN:
                return TerminalTransitionResult(False, entry.state, entry.configuration)
            if entry.runtime is not None:
                raise ProjectError(f"Terminal cleanup must succeed before reopening project: {entry.project.name}")
            entry.state = ProjectTerminalState.OPENING
            entry.failure = None
            entry.configuration = configuration
        try:
            runtime = await self._runtime_factory(entry.project, configuration)
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
            await self._close(entry)
            raise ProjectTerminalNotAvailableError("Terminal manager shutdown has started")
        return TerminalTransitionResult(True, ProjectTerminalState.OPEN, configuration)

    async def _close(self, entry: _ProjectTerminalEntry) -> TerminalTransitionResult:
        with self._lock:
            runtime = entry.runtime
            if runtime is None:
                changed = entry.state is not ProjectTerminalState.CLOSED
                entry.state = ProjectTerminalState.CLOSED
                entry.failure = None
                entry.configuration = None
                return TerminalTransitionResult(changed, ProjectTerminalState.CLOSED, None)
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
            entry.configuration = None
        return TerminalTransitionResult(True, ProjectTerminalState.CLOSED, None)
