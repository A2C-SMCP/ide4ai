"""Lazy per-project IDE runtime with active-call lifecycle guards."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from enum import Enum
from typing import Any

from ide4ai.a2c_smcp.projects.errors import ProjectBusyError, ProjectError
from ide4ai.a2c_smcp.projects.models import Project
from ide4ai.ide import IDE

IDEFactory = Callable[[Project], IDE]


class _RuntimeState(Enum):
    UNLOADED = "unloaded"
    LOADED = "loaded"
    CLOSING = "closing"
    TERMINATING = "terminating"
    CLOSE_FAILED = "close_failed"
    CLOSED = "closed"


def create_ide_factory(defaults: Mapping[str, Any]) -> IDEFactory:
    """Create project IDEs while preserving server-wide non-project defaults."""

    immutable_defaults = dict(defaults)

    def factory(project: Project) -> IDE:
        kwargs = {
            **immutable_defaults,
            "root_dir": project.root_dir,
            "project_name": project.name,
            "language_profiles": project.lsp.to_profiles(),
            "lsp_settings": project.lsp.to_settings(),
        }
        return IDE(**kwargs)

    return factory


class ProjectRuntime:
    """Own one lazily-created IDE and track calls using it."""

    def __init__(self, project: Project, ide_factory: IDEFactory) -> None:
        self.project = project
        self._ide_factory = ide_factory
        self._ide: IDE | None = None
        self._active_calls = 0
        self._state = _RuntimeState.UNLOADED
        self._lock = threading.RLock()

    @property
    def loaded(self) -> bool:
        with self._lock:
            return self._ide is not None

    @property
    def active_calls(self) -> int:
        with self._lock:
            return self._active_calls

    @contextmanager
    def lease(self) -> Iterator[IDE]:
        with self._lock:
            if self._state is _RuntimeState.CLOSED:
                raise ProjectError(f"Project runtime is closed: {self.project.name}")
            if self._state in (
                _RuntimeState.CLOSING,
                _RuntimeState.TERMINATING,
                _RuntimeState.CLOSE_FAILED,
            ):
                raise ProjectBusyError(f"Project runtime is releasing resources: {self.project.name}")
            if self._state is _RuntimeState.UNLOADED:
                self._ide = self._ide_factory(self.project)
                self._state = _RuntimeState.LOADED
            if self._ide is None:
                raise ProjectError(f"Project runtime has no IDE in state {self._state.value}: {self.project.name}")
            ide = self._ide
            self._active_calls += 1
        try:
            yield ide
        finally:
            with self._lock:
                self._active_calls -= 1
                if self._active_calls == 0 and self._state is _RuntimeState.TERMINATING and self._ide is None:
                    self._state = _RuntimeState.UNLOADED

    def unload(self, *, force: bool = False) -> bool:
        """Release loaded resources, returning whether a runtime was loaded."""
        return self._release(force=force, permanent=False)

    def close(self) -> None:
        """Permanently close this runtime during server shutdown."""
        self._release(force=True, permanent=True)

    def _release(self, *, force: bool, permanent: bool) -> bool:
        with self._lock:
            if self._state is _RuntimeState.CLOSED:
                return False
            if self._state in (_RuntimeState.CLOSING, _RuntimeState.TERMINATING):
                raise ProjectBusyError(f"Project runtime is already releasing resources: {self.project.name}")
            if self._active_calls and not force:
                raise ProjectBusyError(
                    f"Project has {self._active_calls} active call(s); use force=true to unload: {self.project.name}"
                )
            ide = self._ide
            if ide is None:
                self._state = _RuntimeState.CLOSED if permanent else _RuntimeState.UNLOADED
                return False
            self._state = _RuntimeState.TERMINATING if self._active_calls else _RuntimeState.CLOSING
        try:
            ide.close()
        except Exception:
            with self._lock:
                self._state = _RuntimeState.CLOSE_FAILED
            raise
        with self._lock:
            self._ide = None
            if permanent:
                self._state = _RuntimeState.CLOSED
            elif self._active_calls:
                self._state = _RuntimeState.TERMINATING
            else:
                self._state = _RuntimeState.UNLOADED
        return True
