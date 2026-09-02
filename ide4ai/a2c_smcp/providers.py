"""Project-aware MCP tool and resource providers."""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from typing import Any

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import BlobResourceContents, CallToolResult, Resource, TextContent, TextResourceContents, Tool
from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from ide4ai.a2c_smcp.catalog import (
    CatalogChanges,
    ResourceBinding,
    ResourceUpdateListener,
    ToolBinding,
    ToolBindingNotAvailableError,
    ToolCallOutcome,
    ToolInvoker,
)
from ide4ai.a2c_smcp.projects import (
    MAX_TERMINAL_CLOSE_DEADLINE_MS,
    Project,
    ProjectHost,
    ProjectLspConfig,
    ProjectNotFoundError,
    ProjectTerminalNotAvailableError,
    ProjectTerminalRuntimeManager,
    TerminalStartOptions,
)
from ide4ai.a2c_smcp.resource_events import ResourceUpdate
from ide4ai.a2c_smcp.resources import WindowResource
from ide4ai.a2c_smcp.tools.base import BaseTool


class _ProjectNameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Unique, case-insensitive project name")


class _ProjectDeleteInput(_ProjectNameInput):
    force: bool = Field(default=False, description="Release a loaded runtime even when it has active calls")


class _ProjectCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique project name")
    root_dir: str = Field(description="Existing project root directory")
    lsp: ProjectLspConfig = Field(default_factory=ProjectLspConfig)


class _ProjectUnloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = Field(default=False, description="Release resources even when the project has active calls")


class _TerminalStartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cwd: str | None = Field(
        default=None,
        description="Initial cwd within the current project; defaults to the project's immutable root_dir",
    )
    startup_command: str | None = Field(
        default=None,
        min_length=1,
        description="Default initialization command applied by each later shell_open",
    )
    shell: str | None = Field(default=None, min_length=1, description="Optional absolute shell executable")
    environment: dict[str, str] = Field(
        default_factory=dict,
        description="Environment overrides merged onto the server environment; values are never returned",
    )
    command_timeout_ms: int = Field(default=120_000, ge=1, le=86_400_000)
    shutdown_grace_ms: int = Field(default=3_000, ge=1, le=MAX_TERMINAL_CLOSE_DEADLINE_MS)
    close_timeout_ms: int = Field(default=5_000, ge=1, le=MAX_TERMINAL_CLOSE_DEADLINE_MS)

    def to_options(self) -> TerminalStartOptions:
        return TerminalStartOptions(**self.model_dump())


class _TerminalCloseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ProjectOutput(BaseModel):
    """Public project representation; internal runtime identity is intentionally hidden."""

    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True)

    name: str
    root_dir: str
    lsp: ProjectLspConfig


def _project_output(project: Project) -> dict[str, Any]:
    return _ProjectOutput.model_validate(project).model_dump(mode="json")


class ProjectToolProvider:
    """Project registry and selection tools, available without loading an IDE."""

    def __init__(
        self,
        host: ProjectHost,
        terminal_manager: ProjectTerminalRuntimeManager | None = None,
    ) -> None:
        self._host = host
        self._terminal_manager = terminal_manager

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
                "project_switch", "Select a project for subsequent MCP calls.", _ProjectNameInput, self._switch
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
                    "Release the current project's Terminal, IDE, Workspace, and LSP runtime.",
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
            {"project": _project_output(project)},
            CatalogChanges(tools=changed, resources=changed),
        )

    async def _list(self, arguments: dict[str, Any]) -> ToolCallOutcome:
        if arguments:
            raise ValueError("project_list does not accept arguments")
        registered, current = self._host.project_view()
        projects = [_project_output(project) for project in registered]
        return ToolCallOutcome(
            {
                "projects": projects,
                "current_project": current.name if current is not None else None,
            }
        )

    async def _switch(self, arguments: dict[str, Any]) -> ToolCallOutcome:
        data = _ProjectNameInput.model_validate(arguments)
        project = self._host.switch_project(data.name)
        return ToolCallOutcome(
            {"project": _project_output(project)},
            CatalogChanges(tools=True, resources=True),
        )

    async def _delete(self, arguments: dict[str, Any]) -> ToolCallOutcome:
        data = _ProjectDeleteInput.model_validate(arguments)
        project = self._host.prepare_delete(data.name, force=data.force)
        try:
            if self._terminal_manager is not None:
                await self._terminal_manager.remove(project)
        except BaseException as exc:
            self._host.cancel_delete(project)
            if isinstance(exc, Exception):
                return self._terminal_cleanup_failure(project, operation="delete", error=exc)
            raise
        try:
            project = self._host.commit_delete(project)
        except Exception as exc:
            self._host.cancel_delete(project)
            if self._terminal_manager is not None:
                self._terminal_manager.cancel_remove(project)
            return self._delete_commit_failure(project, error=exc)
        return ToolCallOutcome(
            {"project": _project_output(project)},
            CatalogChanges(tools=True, resources=True),
        )

    async def _unload(self, arguments: dict[str, Any], project: Project) -> ToolCallOutcome:
        data = _ProjectUnloadInput.model_validate(arguments)
        unloaded = self._host.unload_project(project, force=data.force)
        if self._terminal_manager is not None:
            try:
                await self._terminal_manager.close(project)
            except Exception as exc:
                return self._terminal_cleanup_failure(project, operation="unload", error=exc)
        return ToolCallOutcome(
            {"project": _project_output(project), "unloaded": unloaded},
            CatalogChanges(tools=True, resources=True),
        )

    @staticmethod
    def _terminal_cleanup_failure(
        project: Project,
        *,
        operation: str,
        error: Exception,
    ) -> ToolCallOutcome:
        return ToolCallOutcome(
            CallToolResult(
                content=[TextContent(type="text", text=str(error))],
                structuredContent={
                    "success": False,
                    "error": {
                        "code": "PROJECT_TERMINAL_CLEANUP_FAILED",
                        "message": str(error),
                        "operation": operation,
                        "project_name": project.name,
                        "project_deleted": False,
                        "terminal_cleanup_pending": True,
                    },
                },
                isError=True,
            ),
            CatalogChanges(tools=True, resources=True),
        )

    @staticmethod
    def _delete_commit_failure(project: Project, *, error: Exception) -> ToolCallOutcome:
        return ToolCallOutcome(
            CallToolResult(
                content=[TextContent(type="text", text=str(error))],
                structuredContent={
                    "success": False,
                    "error": {
                        "code": "PROJECT_DELETE_COMMIT_FAILED",
                        "message": str(error),
                        "operation": "delete",
                        "project_name": project.name,
                        "project_deleted": False,
                        "terminal_cleanup_pending": False,
                    },
                },
                isError=True,
            ),
            CatalogChanges(tools=True, resources=True),
        )


class TerminalToolProvider:
    """Expose one state-specific lifecycle action for the embedded TFBash runtime."""

    def __init__(self, host: ProjectHost, terminal_manager: ProjectTerminalRuntimeManager) -> None:
        self._host = host
        self._terminal_manager = terminal_manager

    def bindings(self, current_project: Project | None) -> tuple[ToolBinding, ...]:
        if current_project is None:
            return ()
        captured_project = current_project
        must_close = self._terminal_manager.requires_close(captured_project)
        tool_name = "terminal_close" if must_close else "terminal_start"
        input_model: type[BaseModel] = _TerminalCloseInput if must_close else _TerminalStartInput

        async def invoke(arguments: dict[str, Any]) -> ToolCallOutcome:
            try:
                project = self._host.registry.find(captured_project.id)
            except ProjectNotFoundError as exc:
                raise ToolBindingNotAvailableError(str(exc)) from exc
            was_available = bool(self._terminal_manager.list_tools(project))
            was_resource_available = bool(self._terminal_manager.list_resources(project))
            try:
                if must_close:
                    _TerminalCloseInput.model_validate(arguments)
                    transition = await self._terminal_manager.close(project)
                else:
                    data = _TerminalStartInput.model_validate(arguments)
                    transition = await self._terminal_manager.start(project, data.to_options())
            except Exception as exc:
                is_available = bool(self._terminal_manager.list_tools(project))
                is_resource_available = bool(self._terminal_manager.list_resources(project))
                state = self._terminal_manager.state(project).value
                return ToolCallOutcome(
                    CallToolResult(
                        content=[TextContent(type="text", text=str(exc))],
                        structuredContent={
                            "success": False,
                            "error": {
                                "code": "TERMINAL_CLOSE_FAILED" if must_close else "TERMINAL_START_FAILED",
                                "message": str(exc),
                                "operation": tool_name,
                                "project_name": project.name,
                                "state": state,
                            },
                        },
                        isError=True,
                    ),
                    CatalogChanges(
                        tools=was_available != is_available,
                        resources=was_resource_available != is_resource_available,
                    ),
                )
            return ToolCallOutcome(
                {
                    "project": _project_output(project),
                    "terminal": {
                        "enabled": bool(self._terminal_manager.list_tools(project)),
                        "state": transition.state.value,
                        "root_dir": project.root_dir,
                        "configuration": (
                            transition.configuration.public_summary() if transition.configuration is not None else None
                        ),
                    },
                },
                CatalogChanges(
                    tools=transition.changed or was_available != bool(self._terminal_manager.list_tools(project)),
                    resources=was_resource_available != bool(self._terminal_manager.list_resources(project)),
                ),
            )

        return (
            ToolBinding(
                Tool(
                    name=tool_name,
                    description=(
                        "Start the current project's embedded TFBash runtime. The workspace root is inherited "
                        "from the immutable project; this does not create a Shell."
                        if not must_close
                        else "Gracefully close the current project's TFBash runtime and all of its Shells; "
                        "remaining managed processes are force-killed after the configured grace period."
                    ),
                    inputSchema=input_model.model_json_schema(),
                ),
                invoke,
            ),
        )


class TFBashToolProvider:
    """Forward TFBash's native tool definitions and results without protocol duplication."""

    def __init__(self, host: ProjectHost, terminal_manager: ProjectTerminalRuntimeManager) -> None:
        self._host = host
        self._terminal_manager = terminal_manager

    def bindings(self, current_project: Project | None) -> tuple[ToolBinding, ...]:
        if current_project is None:
            return ()
        captured_project = current_project
        bindings: list[ToolBinding] = []
        for definition in self._terminal_manager.list_tools(captured_project):
            tool_name = definition.name

            async def invoke(
                arguments: dict[str, Any],
                *,
                captured: Project = captured_project,
                name: str = tool_name,
            ) -> ToolCallOutcome:
                try:
                    project = self._host.registry.find(captured.id)
                    result = await self._terminal_manager.call_tool(project, name, arguments)
                except (ProjectNotFoundError, ProjectTerminalNotAvailableError) as exc:
                    raise ToolBindingNotAvailableError(str(exc)) from exc
                return ToolCallOutcome(result)

            bindings.append(ToolBinding(definition, invoke))
        return tuple(bindings)


class TFBashResourceProvider:
    """Forward TFBash Resource definitions, contents, and update events."""

    def __init__(self, host: ProjectHost, terminal_manager: ProjectTerminalRuntimeManager) -> None:
        self._host = host
        self._terminal_manager = terminal_manager

    def bindings(self, current_project: Project | None) -> tuple[ResourceBinding, ...]:
        if current_project is None:
            return ()
        captured_project = current_project
        bindings: list[ResourceBinding] = []
        for definition in self._terminal_manager.list_resources(captured_project):

            async def read(
                requested_uri: str, *, captured: Project = captured_project
            ) -> tuple[ReadResourceContents, ...]:
                project = self._host.registry.find(captured.id)
                result = self._terminal_manager.read_resource(project, requested_uri)
                return tuple(_to_read_resource_contents(content) for content in result.contents)

            bindings.append(ResourceBinding(definition, read))
        return tuple(bindings)

    def subscribe_updates(self, listener: ResourceUpdateListener) -> Callable[[], None]:
        return self._terminal_manager.subscribe_resource_updates(listener)

    def is_update_current(self, update: ResourceUpdate) -> bool:
        return self._terminal_manager.is_resource_update_current(update)


def _to_read_resource_contents(content: TextResourceContents | BlobResourceContents) -> ReadResourceContents:
    if isinstance(content, TextResourceContents):
        payload: str | bytes = content.text
    else:
        payload = base64.b64decode(content.blob, validate=True)
    return ReadResourceContents(content=payload, mime_type=content.mimeType, meta=content.meta)


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

        async def read(
            requested_uri: str,
            *,
            captured: Project = captured_project,
        ) -> tuple[ReadResourceContents, ...]:
            with self._host.lease_project(captured) as (_, ide):
                resource = WindowResource(ide, priority=0, fullscreen=True)
                if requested_uri != resource.uri:
                    resource.update_from_uri(requested_uri)
                return (ReadResourceContents(content=await resource.read(), mime_type="text/plain"),)

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
