"""Concurrent, crash-safe persistence for immutable project records."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

from filelock import FileLock
from pydantic import ValidationError

from ide4ai.a2c_smcp.projects.errors import ProjectConflictError, ProjectNotFoundError, ProjectRegistryError
from ide4ai.a2c_smcp.projects.models import (
    Project,
    ProjectLspConfig,
    ProjectRegistryDocument,
    roots_refer_to_same_location,
)


class ProjectRegistry:
    """A versioned JSON registry protected across threads and processes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self._lock = threading.RLock()
        self._file_lock = FileLock(f"{self.path}.lock")

    def list(self) -> tuple[Project, ...]:
        with self._locked():
            document = self._read_unlocked()
            return tuple(sorted(document.projects, key=lambda project: (project.name.casefold(), str(project.id))))

    def create(self, *, name: str, root_dir: str | Path, lsp: ProjectLspConfig | None = None) -> Project:
        canonical_root = self._canonical_root(root_dir)
        candidate = Project(id=uuid4(), name=name, root_dir=str(canonical_root), lsp=lsp or ProjectLspConfig())
        with self._locked():
            document = self._read_unlocked()
            self._ensure_unique(document.projects, candidate)
            self._write_unlocked(ProjectRegistryDocument(projects=(*document.projects, candidate)))
        return candidate

    def delete(self, identifier: str | UUID) -> Project:
        with self._locked():
            document = self._read_unlocked()
            project = self._find(document.projects, identifier)
            remaining = tuple(item for item in document.projects if item.id != project.id)
            self._write_unlocked(ProjectRegistryDocument(projects=remaining))
            return project

    def find(self, identifier: str | UUID) -> Project:
        with self._locked():
            return self._find(self._read_unlocked().projects, identifier)

    def _locked(self) -> _RegistryLock:
        return _RegistryLock(self._lock, self._file_lock, self.path.parent.mkdir)

    def _read_unlocked(self) -> ProjectRegistryDocument:
        if not self.path.exists():
            return ProjectRegistryDocument()
        try:
            content = self.path.read_text(encoding="utf-8")
            return ProjectRegistryDocument.model_validate_json(content)
        except (OSError, ValidationError, ValueError) as exc:
            raise ProjectRegistryError(f"Cannot read project registry {self.path}: {exc}") from exc

    def _write_unlocked(self, document: ProjectRegistryDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
            self._sync_parent_directory()
        except OSError as exc:
            raise ProjectRegistryError(f"Cannot write project registry {self.path}: {exc}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _sync_parent_directory(self) -> None:
        if not hasattr(os, "O_DIRECTORY"):
            return
        try:
            descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _canonical_root(root_dir: str | Path) -> Path:
        root = Path(root_dir).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")
        return root

    @staticmethod
    def _ensure_unique(projects: tuple[Project, ...], candidate: Project) -> None:
        candidate_name = candidate.name.casefold()
        for project in projects:
            if project.name.casefold() == candidate_name:
                raise ProjectConflictError(f"Project name already exists: {candidate.name}")
            if roots_refer_to_same_location(project.root_dir, candidate.root_dir):
                raise ProjectConflictError(f"Project root already exists: {candidate.root_dir}")

    @staticmethod
    def _find(projects: tuple[Project, ...], identifier: str | UUID) -> Project:
        if isinstance(identifier, UUID):
            match = next((project for project in projects if project.id == identifier), None)
        else:
            match = next(
                (project for project in projects if project.name.casefold() == identifier.casefold()),
                None,
            )
        if match is not None:
            return match
        raise ProjectNotFoundError(f"Project not found: {identifier}")


class _RegistryLock:
    def __init__(
        self,
        thread_lock: threading.RLock,
        file_lock: FileLock,
        mkdir: Callable[..., None],
    ) -> None:
        self._thread_lock = thread_lock
        self._file_lock = file_lock
        self._mkdir = mkdir

    def __enter__(self) -> None:
        self._thread_lock.acquire()
        try:
            self._mkdir(parents=True, exist_ok=True)
            self._file_lock.acquire()
        except BaseException:
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._file_lock.release()
        self._thread_lock.release()
