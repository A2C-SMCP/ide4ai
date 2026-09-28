"""Persistent, immutable project configuration models."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ide4ai.languages import configured_language_profiles
from ide4ai.lsp.manager import LanguageProfile, LspMode, LspSettings


def roots_refer_to_same_location(left: str, right: str) -> bool:
    """Compare canonical roots by filesystem identity whenever possible."""
    try:
        return os.path.samefile(left, right)
    except OSError:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


class ProjectLspConfig(BaseModel):
    """Serializable per-project LSP selection and profile overrides."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: LspMode = "auto"
    language_id: str | None = None
    profile_language_id: str | None = None
    server_command: tuple[str, ...] | None = None
    file_extensions: tuple[str, ...] = ()
    root_markers: tuple[str, ...] = ()

    @field_validator("language_id", "profile_language_id")
    @classmethod
    def validate_optional_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("language identifiers cannot be blank")
        return normalized

    @field_validator("server_command")
    @classmethod
    def validate_server_command(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is not None and (not value or any(not part for part in value)):
            raise ValueError("server_command must contain non-empty arguments")
        return value

    @field_validator("file_extensions")
    @classmethod
    def validate_file_extensions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not extension.startswith(".") for extension in value):
            raise ValueError("file extensions must start with '.'")
        return value

    @model_validator(mode="after")
    def validate_selection(self) -> ProjectLspConfig:
        LspSettings(mode=self.mode, language_id=self.language_id)
        target_language = self.profile_language_id or self.language_id
        if target_language is None and (self.file_extensions or self.root_markers) and self.server_command is None:
            raise ValueError("LSP profile overrides require a language id")
        configured_language_profiles(
            language_id=target_language,
            server_command=self.server_command,
            file_extensions=self.file_extensions,
            root_markers=self.root_markers,
        )
        return self

    def to_settings(self) -> LspSettings:
        return LspSettings(mode=self.mode, language_id=self.language_id)

    def to_profiles(self) -> tuple[LanguageProfile, ...]:
        return configured_language_profiles(
            language_id=self.profile_language_id or self.language_id,
            server_command=self.server_command,
            file_extensions=self.file_extensions,
            root_markers=self.root_markers,
        )


class Project(BaseModel):
    """An immutable project record stored in the registry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    name: str
    root_dir: str
    lsp: ProjectLspConfig = Field(default_factory=ProjectLspConfig)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project name cannot be blank")
        return normalized

    @field_validator("root_dir")
    @classmethod
    def validate_root_dir(cls, value: str) -> str:
        if not value:
            raise ValueError("project root cannot be blank")
        root = Path(value)
        if not root.is_absolute():
            raise ValueError("project root must be absolute")
        if str(root.resolve(strict=False)) != value:
            raise ValueError("project root must be normalized")
        return value


def _validate_unique_projects(projects: tuple[Project, ...]) -> None:
    ids: set[UUID] = set()
    names: set[str] = set()
    roots: list[str] = []
    for project in projects:
        if project.id in ids:
            raise ValueError(f"duplicate project id: {project.id}")
        normalized_name = project.name.casefold()
        if normalized_name in names:
            raise ValueError(f"duplicate project name: {project.name}")
        if any(roots_refer_to_same_location(root, project.root_dir) for root in roots):
            raise ValueError(f"duplicate project root: {project.root_dir}")
        ids.add(project.id)
        names.add(normalized_name)
        roots.append(project.root_dir)


class ProjectRegistryDocumentV1(BaseModel):
    """Read-only legacy shape used solely for one-time migration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1] = 1
    projects: tuple[Project, ...] = ()

    @model_validator(mode="after")
    def validate_unique_projects(self) -> ProjectRegistryDocumentV1:
        _validate_unique_projects(self.projects)
        return self


class ProjectRegistryDocument(BaseModel):
    """Canonical server-owned project metadata, including the persisted selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[2] = 2
    projects: tuple[Project, ...] = ()
    current_project_id: UUID | None = None

    @model_validator(mode="after")
    def validate_project_metadata(self) -> ProjectRegistryDocument:
        _validate_unique_projects(self.projects)
        project_ids = {project.id for project in self.projects}
        if not project_ids and self.current_project_id is not None:
            raise ValueError("current_project_id must be null when projects is empty")
        if project_ids and self.current_project_id not in project_ids:
            raise ValueError("current_project_id must identify exactly one registered project")
        return self
