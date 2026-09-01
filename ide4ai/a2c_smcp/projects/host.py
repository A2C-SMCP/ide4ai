"""MCP-session project selection and runtime ownership."""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from ide4ai.a2c_smcp.projects.errors import ProjectBusyError, ProjectError, ProjectNotSelectedError
from ide4ai.a2c_smcp.projects.models import Project, ProjectLspConfig
from ide4ai.a2c_smcp.projects.registry import ProjectRegistry
from ide4ai.a2c_smcp.projects.runtime import IDEFactory, ProjectRuntime
from ide4ai.ide import IDE


class ProjectHost:
    """Own session-local selection and process-local project runtimes."""

    def __init__(self, registry: ProjectRegistry, ide_factory: IDEFactory) -> None:
        self.registry = registry
        self._ide_factory = ide_factory
        self._current_project_id: UUID | None = None
        self._runtimes: dict[UUID, ProjectRuntime] = {}
        self._deleting_project_ids: set[UUID] = set()
        self._closed = False
        self._lock = threading.RLock()

    @property
    def current_project(self) -> Project | None:
        with self._lock:
            self._ensure_open()
            return self._current_project_unlocked()

    def list_projects(self) -> tuple[Project, ...]:
        with self._lock:
            self._ensure_open()
            projects = self.registry.list()
            self._reconcile_selection(projects)
            return projects

    def create_project(
        self,
        *,
        name: str,
        root_dir: str | Path,
        lsp: ProjectLspConfig | None = None,
    ) -> Project:
        with self._lock:
            self._ensure_open()
            project = self.registry.create(name=name, root_dir=root_dir, lsp=lsp)
            projects = self.registry.list()
            self._reconcile_selection(projects)
            return project

    def switch_project(self, identifier: str | UUID) -> Project:
        with self._lock:
            self._ensure_open()
            project = self.registry.find(identifier)
            self._current_project_id = project.id
            return project

    def unload_current(self, *, force: bool = False) -> bool:
        with self._lock:
            project = self._require_current_unlocked()
        return self.unload_project(project, force=force)

    def unload_project(self, project: Project, *, force: bool = False) -> bool:
        """Unload a captured project without following a later selection change."""
        with self._lock:
            self._ensure_open()
            self.registry.find(project.id)
            runtime = self._runtimes.get(project.id)
            if runtime is None:
                return False
            return runtime.unload(force=force)

    def delete_project(self, identifier: str | UUID, *, force: bool = False) -> Project:
        project = self.prepare_delete(identifier, force=force)
        try:
            return self.commit_delete(project)
        except BaseException:
            self.cancel_delete(project)
            raise

    def prepare_delete(self, identifier: str | UUID, *, force: bool = False) -> Project:
        """Reserve a project for deletion and release its IDE before async cleanup."""

        with self._lock:
            self._ensure_open()
            project = self.registry.find(identifier)
            if project.id in self._deleting_project_ids:
                raise ProjectBusyError(f"Project deletion is already in progress: {project.name}")
            self._deleting_project_ids.add(project.id)
            runtime = self._runtimes.get(project.id)
            try:
                if runtime is not None:
                    runtime.unload(force=force)
            except BaseException:
                self._deleting_project_ids.discard(project.id)
                raise
            return project

    def commit_delete(self, project: Project) -> Project:
        """Persist a prepared deletion after provider-owned resources are closed."""

        with self._lock:
            self._ensure_open()
            if project.id not in self._deleting_project_ids:
                raise ProjectError(f"Project deletion was not prepared: {project.name}")
            try:
                deleted = self.registry.delete(project.id)
            except BaseException:
                self._deleting_project_ids.discard(project.id)
                raise
            self._runtimes.pop(project.id, None)
            if self._current_project_id == project.id:
                self._current_project_id = None
            self._deleting_project_ids.discard(project.id)
            self._reconcile_selection(self.registry.list())
            return deleted

    def cancel_delete(self, project: Project) -> None:
        """Release a deletion reservation so the operation can be retried."""

        with self._lock:
            self._deleting_project_ids.discard(project.id)

    @contextmanager
    def lease_current(self) -> Iterator[tuple[Project, IDE]]:
        """Pin the selected project before a call starts, surviving later switches."""
        with self._lock:
            project = self._require_current_unlocked()
        with self.lease_project(project) as leased:
            yield leased

    @contextmanager
    def lease_project(self, project: Project) -> Iterator[tuple[Project, IDE]]:
        """Lease an already captured project without consulting later selection changes."""
        with self._lock:
            self._ensure_open()
            persisted_project = self.registry.find(project.id)
            if project.id in self._deleting_project_ids:
                raise ProjectBusyError(f"Project deletion is in progress: {project.name}")
            runtime = self._runtimes.get(project.id)
            if runtime is None:
                runtime = ProjectRuntime(persisted_project, self._ide_factory)
                self._runtimes[project.id] = runtime
            lease = runtime.lease()
            ide = lease.__enter__()
        try:
            yield persisted_project, ide
        finally:
            lease.__exit__(*sys.exc_info())

    def close(self) -> None:
        with self._lock:
            if self._closed and not self._runtimes:
                return
            self._closed = True
            runtimes = tuple(self._runtimes.items())
            self._current_project_id = None
            self._deleting_project_ids.clear()
        errors: list[BaseException] = []
        closed_ids: list[UUID] = []
        for project_id, runtime in runtimes:
            try:
                runtime.close()
                closed_ids.append(project_id)
            except Exception as exc:
                errors.append(exc)
        with self._lock:
            for project_id in closed_ids:
                self._runtimes.pop(project_id, None)
        if errors:
            raise ProjectError(f"Failed to close {len(errors)} project runtime(s)") from errors[0]

    def _current_project_unlocked(self) -> Project | None:
        projects = self.registry.list()
        self._reconcile_selection(projects)
        if self._current_project_id is None:
            return None
        return next((project for project in projects if project.id == self._current_project_id), None)

    def _require_current_unlocked(self) -> Project:
        self._ensure_open()
        project = self._current_project_unlocked()
        if project is None:
            raise ProjectNotSelectedError("No project selected; call project_switch first")
        return project

    def _reconcile_selection(self, projects: tuple[Project, ...]) -> None:
        known_ids = {project.id for project in projects}
        if self._current_project_id not in known_ids:
            self._current_project_id = projects[0].id if len(projects) == 1 else None

    def _ensure_open(self) -> None:
        if self._closed:
            raise ProjectError("Project host is closed")
