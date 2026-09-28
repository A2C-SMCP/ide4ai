"""Project-aware MCP protocol server."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anyio
from jsonschema import FormatChecker  # type: ignore[import-untyped]
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as validate_json_schema
from loguru import logger
from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, Resource, TextContent, Tool
from pydantic import AnyUrl
from pydantic import ValidationError as PydanticValidationError

from ide4ai.a2c_smcp.catalog import (
    DynamicResourceCatalog,
    DynamicToolCatalog,
    ResourceProvider,
    ToolBindingNotAvailableError,
    ToolProvider,
)
from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.projects import ProjectError, ProjectHost, ProjectNotFoundError
from ide4ai.a2c_smcp.resource_updates import ResourceUpdateHub


class _SubscribableResourceServer(Server[object, object]):
    """Advertise Resource subscriptions supported by the dynamic catalog."""

    def get_capabilities(
        self,
        notification_options: NotificationOptions,
        experimental_capabilities: dict[str, dict[str, Any]],
    ) -> types.ServerCapabilities:
        capabilities = super().get_capabilities(notification_options, experimental_capabilities)
        resources = capabilities.resources
        if resources is None:
            return capabilities
        return capabilities.model_copy(
            update={
                "resources": types.ResourcesCapability(
                    subscribe=True,
                    listChanged=resources.listChanged,
                )
            }
        )


class BaseMCPServer:
    """Serve dynamic tools and resources for one stdio MCP project session."""

    def __init__(
        self,
        config: MCPServerConfig,
        server_name: str,
        host: ProjectHost,
        tool_providers: tuple[ToolProvider, ...],
        resource_providers: tuple[ResourceProvider, ...],
    ) -> None:
        self.config = config
        self.project_host = host
        self.tool_catalog = DynamicToolCatalog(tool_providers)
        self.resource_catalog = DynamicResourceCatalog(resource_providers)
        self._resource_update_hub = ResourceUpdateHub(
            host,
            self.resource_catalog.subscribe_updates,
            self.resource_catalog.is_update_current,
        )

        @asynccontextmanager
        async def lifespan(_: Server[object, object]) -> AsyncIterator[object]:
            self._resource_update_hub.connect()
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(self._resource_update_hub.run)
                try:
                    yield object()
                finally:
                    self._resource_update_hub.stop()

        self.server = _SubscribableResourceServer(server_name, lifespan=lifespan)
        self._closed = False
        self._setup_handlers()
        logger.info("MCP Server initialized: server={}, transport={}", server_name, config.transport)

    def close(self) -> None:
        """Close synchronous project resources.

        Async integrations should call :meth:`aclose`, which also releases
        provider-owned resources before closing the project host.
        """
        self._close_sync_resources()

    def _close_sync_resources(self) -> None:
        """Close resources that do not require an async context."""

        if getattr(self, "_closed", True):
            return
        host = getattr(self, "project_host", None)
        if host is not None:
            host.close()
        self._closed = True

    async def aclose(self) -> None:
        """Release async provider resources before synchronous project state."""

        errors: list[BaseException] = []
        with anyio.CancelScope(shield=True):
            try:
                await self._close_async_resources()
            except BaseException as exc:
                errors.append(exc)
            try:
                self._close_sync_resources()
            except BaseException as exc:
                errors.append(exc)
        if errors:
            for additional_error in errors[1:]:
                logger.error("Additional server shutdown error: {}", repr(additional_error))
            raise errors[0]

    async def _close_async_resources(self) -> None:
        """Hook for concrete servers that own asynchronous runtimes."""

    def __del__(self) -> None:
        try:
            self.close()
        except Exception as exc:
            logger.error("Error closing MCP server during finalization: {}", exc)

    def _setup_handlers(self) -> None:
        @self.server.list_tools()  # type: ignore[no-untyped-call]
        async def list_tools() -> list[Tool]:
            snapshot = self.project_host.current_project
            tools = [binding.definition for binding in self.tool_catalog.bindings(snapshot)]
            logger.debug("Listed tools: {}", [tool.name for tool in tools])
            return tools

        # Providers validate their own inputs. Disabling the SDK's cached-schema validation
        # ensures a disappeared tool always reaches our state-aware stale-tool error path.
        @self.server.call_tool(validate_input=False)
        async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any] | CallToolResult:
            snapshot = self.project_host.current_project
            binding = self.tool_catalog.find(snapshot, name)
            if binding is None:
                return self._tool_error(
                    "TOOL_NOT_AVAILABLE_FOR_CURRENT_PROJECT",
                    f"Tool is not available for the current project state: {name}",
                    tool=name,
                    project_name=snapshot.name if snapshot else None,
                )
            try:
                validate_json_schema(
                    instance=arguments,
                    schema=binding.definition.inputSchema,
                    format_checker=FormatChecker(),
                )
            except JsonSchemaValidationError as exc:
                return self._tool_error(
                    "TOOL_INPUT_VALIDATION_FAILED",
                    exc.message,
                    tool=name,
                    project_name=snapshot.name if snapshot else None,
                )
            try:
                outcome = await binding.invoke(arguments)
            except ToolBindingNotAvailableError:
                return self._tool_error(
                    "TOOL_NOT_AVAILABLE_FOR_CURRENT_PROJECT",
                    f"The project captured for tool {name} no longer exists",
                    tool=name,
                    project_name=snapshot.name if snapshot else None,
                )
            except PydanticValidationError as exc:
                return self._tool_error("TOOL_INPUT_VALIDATION_FAILED", str(exc), tool=name)
            except ProjectNotFoundError as exc:
                return self._tool_error("PROJECT_NOT_FOUND", str(exc), tool=name)
            except (ProjectError, ValueError) as exc:
                logger.warning("Tool call rejected: name={}, error={}", name, exc)
                return self._tool_error("TOOL_EXECUTION_FAILED", str(exc), tool=name)
            except Exception as exc:
                logger.exception("Tool execution failed: name={}", name)
                return self._tool_error("TOOL_EXECUTION_FAILED", str(exc), tool=name)
            try:
                await self._notify_catalog_changes(
                    tools=outcome.changes.tools,
                    resources=outcome.changes.resources,
                )
            except Exception as exc:
                logger.warning("Catalog notification failed after successful tool call: name={}, error={}", name, exc)
            return outcome.result

        @self.server.list_resources()  # type: ignore[no-untyped-call]
        async def list_resources() -> list[Resource]:
            snapshot = self.project_host.current_project
            resources = [binding.definition for binding in self.resource_catalog.bindings(snapshot)]
            logger.debug("Listed resources: {}", [str(resource.uri) for resource in resources])
            return resources

        @self.server.read_resource()  # type: ignore[no-untyped-call]
        async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
            uri_str = str(uri)
            snapshot = self.project_host.current_project
            binding = self.resource_catalog.find(snapshot, uri_str)
            if binding is None:
                raise ValueError(f"Resource is not available for the current project state: {uri_str}")
            try:
                return list(await binding.read(uri_str))
            except McpError:
                raise
            except Exception as exc:
                logger.exception("Resource read failed: uri={}", uri_str)
                raise ValueError(f"Resource read failed: {exc}") from exc

        @self.server.subscribe_resource()  # type: ignore[no-untyped-call]
        async def subscribe_resource(uri: AnyUrl) -> None:
            snapshot = self.project_host.current_project
            if self.resource_catalog.find(snapshot, str(uri)) is None:
                raise ValueError(f"Resource is not available for the current project state: {uri}")
            self._resource_update_hub.subscribe(self.server.request_context.session, uri)

        @self.server.unsubscribe_resource()  # type: ignore[no-untyped-call]
        async def unsubscribe_resource(uri: AnyUrl) -> None:
            self._resource_update_hub.unsubscribe(self.server.request_context.session, uri)

    async def _notify_catalog_changes(self, *, tools: bool, resources: bool) -> None:
        if not tools and not resources:
            return
        try:
            session = self.server.request_context.session
        except LookupError:
            logger.debug("Catalog changed outside an MCP request; no notification session is available")
            return
        if tools:
            await session.send_tool_list_changed()
        if resources:
            await session.send_resource_list_changed()

    @staticmethod
    def _tool_error(code: str, message: str, **details: Any) -> CallToolResult:
        structured = {"success": False, "error": {"code": code, "message": message, **details}}
        return CallToolResult(
            content=[TextContent(type="text", text=message)],
            structuredContent=structured,
            isError=True,
        )

    def initialization_options(self) -> Any:
        """Advertise dynamic list support to stdio clients."""
        return self.server.create_initialization_options(
            notification_options=NotificationOptions(tools_changed=True, resources_changed=True)
        )

    async def run(self) -> None:
        if self.config.transport != "stdio":
            raise ValueError(
                "Multi-project MCP currently supports stdio transport only; "
                f"unsupported transport: {self.config.transport}"
            )
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(read_stream, write_stream, self.initialization_options())
        finally:
            await self.aclose()
