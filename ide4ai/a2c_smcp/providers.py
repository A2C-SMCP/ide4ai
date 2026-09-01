"""Project-aware MCP tool and resource providers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from mcp.types import Resource, Tool
from pydantic import AnyUrl, BaseModel, ConfigDict, Field, model_validator

from ide4ai.a2c_smcp.catalog import (
    CatalogChanges,
    ResourceBinding,
    ToolBinding,
    ToolBindingNotAvailableError,
    ToolCallOutcome,
    ToolInvoker,
)
from ide4ai.a2c_smcp.projects import Project, ProjectHost, ProjectLspConfig, ProjectNotFoundError
from ide4ai.a2c_smcp.resources import WindowResource
from ide4ai.a2c_smcp.tools.base import BaseTool


class _ProjectIdentifier(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["project_id"],
                    "properties": {"project_id": {"type": "string", "format": "uuid"}},
                    "not": {"required": ["name"]},
                },
                {
                    "required": ["name"],
                    "properties": {"name": {"type": "string", "minLength": 1}},
                    "not": {"required": ["project_id"]},
                },
            ]
        },
    )

    project_id: UUID | None = Field(default=None, description="Stable project UUID")
    name: str | None = Field(default=None, description="Case-insensitive project name")

    @model_validator(mode="after")
    def require_one_identifier(self) -> _ProjectIdentifier:
        if (self.project_id is None) == (self.name is None):
            raise ValueError("Provide exactly one of project_id or name")
        return self

    @property
    def identifier(self) -> UUID | str:
        return self.project_id if self.project_id is not None else self.name or ""


class _ProjectDeleteInput(_ProjectIdentifier):
    force: bool = Field(default=False, description="Release a loaded runtime even when it has active calls")


class _ProjectCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique project name")
    root_dir: str = Field(description="Existing project root directory")
    lsp: ProjectLspConfig = Field(default_factory=ProjectLspConfig)


class _ProjectUnloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = Field(default=False, description="Release resources even when the project has active calls")


class ProjectToolProvider:
    """Project registry and selection tools, available without loading an IDE."""

    def __init__(self, host: ProjectHost) -> None:
        self._host = host

    def bindings(self, current_project: Project | None) -> tuple[ToolBinding, ...]:
        bindings = [
            self._binding(
                "project_create", "Create an immutable project registration.", _ProjectCreateInput, self._create
            ),
            self._binding(
                "project_delete",
                "Delete a registered project and release its runtime.",
                _ProjectDeleteInput,
                self._delete,
            ),
            self._binding("project_list", "List registered projects and the current selection.", None, self._list),
            self._binding(
                "project_switch", "Select a project for subsequent MCP calls.", _ProjectIdentifier, self._switch
            ),
        ]
        if current_project is not None:
            captured_project = current_project

            async def unload(arguments: dict[str, Any], *, captured: Project = captured_project) -> ToolCallOutcome:
                try:
                    return await self._unload(arguments, captured)
                except ProjectNotFoundError as exc:
                    raise ToolBindingNotAvailableError(str(exc)) from exc

            bindings.append(
                self._binding(
                    "project_unload",
                    "Release the current project's IDE, Workspace, and LSP runtime.",
                    _ProjectUnloadInput,
                    unload,
                )
            )
        return tuple(bindings)

    @staticmethod
    def _binding(
        name: str,
        description: str,
        model: type[BaseModel] | None,
        invoke: ToolInvoker,
    ) -> ToolBinding:
        schema = model.model_json_schema() if model is not None else {"type": "object", "additionalProperties": False}
        return ToolBinding(Tool(name=name, description=description, inputSchema=schema), invoke)

    async def _create(self, arguments: dict[str, Any]) -> ToolCallOutcome:
        data = _ProjectCreateInput.model_validate(arguments)
        before = self._host.current_project
        project = self._host.create_project(name=data.name, root_dir=data.root_dir, lsp=data.lsp)
        changed = before != self._host.current_project
        return ToolCallOutcome(
            {"project": project.model_dump(mode="json")},
            CatalogChanges(tools=changed, resources=changed),
        )

    async def _list(self, arguments: dict[str, Any]) -> ToolCallOutcome:
        if arguments:
            raise ValueError("project_list does not accept arguments")
        current = self._host.current_project
        projects = [
            {**project.model_dump(mode="json"), "current": current is not None and project.id == current.id}
            for project in self._host.list_projects()
        ]
        return ToolCallOutcome({"projects": projects})

    async def _switch(self, arguments: dict[str, Any]) -> ToolCallOutcome:
        data = _ProjectIdentifier.model_validate(arguments)
        project = self._host.switch_project(data.identifier)
        return ToolCallOutcome(
            {"project": project.model_dump(mode="json")},
            CatalogChanges(tools=True, resources=True),
        )

    async def _delete(self, arguments: dict[str, Any]) -> ToolCallOutcome:
        data = _ProjectDeleteInput.model_validate(arguments)
        project = self._host.delete_project(data.identifier, force=data.force)
        return ToolCallOutcome(
            {"project": project.model_dump(mode="json")},
            CatalogChanges(tools=True, resources=True),
        )

    async def _unload(self, arguments: dict[str, Any], project: Project) -> ToolCallOutcome:
        data = _ProjectUnloadInput.model_validate(arguments)
        unloaded = self._host.unload_project(project, force=data.force)
        return ToolCallOutcome(
            {"project": project.model_dump(mode="json"), "unloaded": unloaded},
            CatalogChanges(tools=True, resources=True),
        )


class IDEToolProvider:
    """Bind generic IDE tool classes to the captured current project per call."""

    def __init__(self, host: ProjectHost, tool_types: Sequence[type[BaseTool]]) -> None:
        self._host = host
        self._tool_types = tuple(tool_types)

    def bindings(self, current_project: Project | None) -> tuple[ToolBinding, ...]:
        if current_project is None:
            return ()
        captured_project = current_project
        bindings: list[ToolBinding] = []
        for tool_type in self._tool_types:
            descriptor = tool_type()

            async def invoke(
                arguments: dict[str, Any],
                *,
                captured: Project = captured_project,
                kind: type[BaseTool] = tool_type,
            ) -> ToolCallOutcome:
                try:
                    with self._host.lease_project(captured) as (_, ide):
                        return ToolCallOutcome(await kind(ide).execute(arguments))
                except ProjectNotFoundError as exc:
                    raise ToolBindingNotAvailableError(str(exc)) from exc

            bindings.append(
                ToolBinding(
                    Tool(name=descriptor.name, description=descriptor.description, inputSchema=descriptor.input_schema),
                    invoke,
                )
            )
        return tuple(bindings)


class WindowResourceProvider:
    """Expose the selected project's IDE window without loading it during discovery."""

    def __init__(self, host: ProjectHost) -> None:
        self._host = host

    def bindings(self, current_project: Project | None) -> tuple[ResourceBinding, ...]:
        if current_project is None:
            return ()
        captured_project = current_project
        # Project names are display labels and may contain URI delimiters. The
        # immutable UUID keeps discovery URIs valid, unique, and non-ambiguous.
        uri = f"window://{captured_project.id}?priority=0&fullscreen=true"

        async def read(requested_uri: str, *, captured: Project = captured_project) -> str:
            with self._host.lease_project(captured) as (_, ide):
                resource = WindowResource(ide, priority=0, fullscreen=True)
                if requested_uri != resource.uri:
                    resource.update_from_uri(requested_uri)
                return await resource.read()

        return (
            ResourceBinding(
                Resource(
                    uri=AnyUrl(uri),
                    name=f"IDE Window - {captured_project.name}",
                    description="IDE window content for the current project.",
                    mimeType="text/plain",
                ),
                read,
            ),
        )
