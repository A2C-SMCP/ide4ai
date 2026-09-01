"""Unit coverage for project-driven MCP catalogs."""

from __future__ import annotations

from typing import Any, cast

import anyio
import pytest
from confz import DataSource
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import Resource, ServerNotification, Tool
from pydantic import AnyUrl

from ide4ai.a2c_smcp.catalog import (
    CatalogChanges,
    DynamicResourceCatalog,
    DynamicToolCatalog,
    ResourceBinding,
    ToolBinding,
    ToolCallOutcome,
)
from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.projects import ProjectHost, ProjectRegistry
from ide4ai.a2c_smcp.providers import IDEToolProvider, ProjectToolProvider, WindowResourceProvider
from ide4ai.a2c_smcp.server import BaseMCPServer
from ide4ai.a2c_smcp.tools.base import BaseTool
from ide4ai.ide import IDE


class _FakeIDE:
    def __init__(self, project_name: str) -> None:
        self.project_name = project_name

    def close(self) -> None:
        pass


class _ProjectNameTool(BaseTool):
    @property
    def name(self) -> str:
        return "ProjectName"

    @property
    def description(self) -> str:
        return "Return the captured project name."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"project": self.ide.project_name}


class _NotificationProvider:
    def bindings(self, current_project):
        def binding(name: str, changes: CatalogChanges) -> ToolBinding:
            async def invoke(arguments: dict[str, Any]) -> ToolCallOutcome:
                return ToolCallOutcome({"notified": name}, changes)

            return ToolBinding(
                Tool(name=name, inputSchema={"type": "object", "additionalProperties": False}),
                invoke,
            )

        return (
            binding("NotifyNeither", CatalogChanges()),
            binding("NotifyResources", CatalogChanges(resources=True)),
            binding("NotifyTools", CatalogChanges(tools=True)),
        )


def _host(tmp_path) -> tuple[ProjectHost, list[str]]:
    created: list[str] = []

    def factory(project):
        created.append(project.name)
        return cast(IDE, _FakeIDE(project.name))

    return ProjectHost(ProjectRegistry(tmp_path / "projects.json"), factory), created


def test_catalog_without_selection_only_exposes_project_management(tmp_path) -> None:
    host, created = _host(tmp_path)
    catalog = DynamicToolCatalog((ProjectToolProvider(host), IDEToolProvider(host, (_ProjectNameTool,))))

    names = [binding.definition.name for binding in catalog.bindings(host.current_project)]

    assert names == ["project_create", "project_delete", "project_list", "project_switch"]
    switch = catalog.find(None, "project_switch")
    assert switch is not None
    assert switch.definition.inputSchema["required"] == ["name"]
    assert set(switch.definition.inputSchema["properties"]) == {"name"}
    assert created == []


@pytest.mark.asyncio
async def test_project_tools_expose_name_as_the_only_public_identifier(tmp_path) -> None:
    host, _ = _host(tmp_path)
    provider = ProjectToolProvider(host)
    create = next(binding for binding in provider.bindings(None) if binding.definition.name == "project_create")

    created = await create.invoke({"name": "one", "root_dir": str(tmp_path)})

    assert "id" not in created.result["project"]
    bindings = provider.bindings(host.current_project)
    project_list = next(binding for binding in bindings if binding.definition.name == "project_list")
    listed = await project_list.invoke({})
    assert "id" not in listed.result["projects"][0]

    switch = next(binding for binding in bindings if binding.definition.name == "project_switch")
    switched = await switch.invoke({"name": "one"})
    assert "id" not in switched.result["project"]

    unload = next(binding for binding in bindings if binding.definition.name == "project_unload")
    unloaded = await unload.invoke({})
    assert "id" not in unloaded.result["project"]

    delete = next(binding for binding in bindings if binding.definition.name == "project_delete")
    deleted = await delete.invoke({"name": "one"})
    assert "id" not in deleted.result["project"]


def test_selected_catalog_is_sorted_and_discovery_does_not_load_ide(tmp_path) -> None:
    host, created = _host(tmp_path)
    host.create_project(name="one", root_dir=tmp_path)
    catalog = DynamicToolCatalog((ProjectToolProvider(host), IDEToolProvider(host, (_ProjectNameTool,))))

    names = [binding.definition.name for binding in catalog.bindings(host.current_project)]

    assert names == [
        "project_create",
        "project_delete",
        "project_list",
        "project_switch",
        "project_unload",
        "ProjectName",
    ]
    assert created == []
    resources = WindowResourceProvider(host).bindings(host.current_project)
    assert [str(binding.definition.uri) for binding in resources] == [
        f"window://{host.current_project.id}?priority=0&fullscreen=true"
    ]
    assert created == []


def test_multiple_registered_projects_require_explicit_selection(tmp_path) -> None:
    host, _ = _host(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    host.create_project(name="first", root_dir=first_root)
    host.create_project(name="second", root_dir=second_root)
    restarted = ProjectHost(host.registry, lambda project: cast(IDE, _FakeIDE(project.name)))
    catalog = DynamicToolCatalog((ProjectToolProvider(restarted), IDEToolProvider(restarted, (_ProjectNameTool,))))

    assert restarted.current_project is None
    assert [binding.definition.name for binding in catalog.bindings(None)] == [
        "project_create",
        "project_delete",
        "project_list",
        "project_switch",
    ]


def test_resource_uri_uses_project_id_and_old_uri_cannot_cross_switch(tmp_path) -> None:
    host, _ = _host(tmp_path)
    catalog = DynamicResourceCatalog((WindowResourceProvider(host),))
    previous_uri: str | None = None
    for index, name in enumerate(("my project", "foo:bar", "foo?bar", "foo#bar", "项目")):
        root = tmp_path / str(index)
        root.mkdir()
        project = host.create_project(name=name, root_dir=root)
        host.switch_project(project.id)
        current = host.current_project
        assert current is not None
        binding = catalog.bindings(current)[0]
        uri = str(binding.definition.uri)
        assert uri.startswith(f"window://{project.id}")
        assert binding.definition.name == f"IDE Window - {name}"
        if previous_uri is not None:
            assert catalog.find(current, previous_uri) is None
        previous_uri = uri


@pytest.mark.asyncio
async def test_project_mutations_report_exact_catalog_invalidations(tmp_path) -> None:
    host, _ = _host(tmp_path)
    provider = ProjectToolProvider(host)
    create = next(binding for binding in provider.bindings(None) if binding.definition.name == "project_create")
    created = await create.invoke({"name": "one", "root_dir": str(tmp_path)})
    assert created.changes.tools is True
    assert created.changes.resources is True

    selected = host.current_project
    assert selected is not None
    selected_bindings = provider.bindings(selected)
    unload = next(binding for binding in selected_bindings if binding.definition.name == "project_unload")
    unloaded = await unload.invoke({})
    assert unloaded.changes.tools is True
    assert unloaded.changes.resources is True

    switch = next(binding for binding in selected_bindings if binding.definition.name == "project_switch")
    switched = await switch.invoke({"name": selected.name})
    assert switched.changes.tools is True
    assert switched.changes.resources is True

    delete = next(binding for binding in selected_bindings if binding.definition.name == "project_delete")
    deleted = await delete.invoke({"name": selected.name})
    assert deleted.changes.tools is True
    assert deleted.changes.resources is True


@pytest.mark.asyncio
async def test_tool_binding_keeps_request_start_project_snapshot(tmp_path) -> None:
    host, created = _host(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = host.create_project(name="first", root_dir=first_root)
    provider = IDEToolProvider(host, (_ProjectNameTool,))
    captured_binding = provider.bindings(host.current_project)[0]
    host.create_project(name="second", root_dir=second_root)
    host.switch_project("second")

    outcome = await captured_binding.invoke({})

    assert outcome.result == {"project": first.name}
    assert created == ["first"]


@pytest.mark.asyncio
async def test_unload_binding_keeps_request_start_project_snapshot(tmp_path) -> None:
    host, created = _host(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    host.create_project(name="first", root_dir=first_root)
    ide_binding = IDEToolProvider(host, (_ProjectNameTool,)).bindings(host.current_project)[0]
    await ide_binding.invoke({})
    project_provider = ProjectToolProvider(host)
    unload_binding = next(
        binding
        for binding in project_provider.bindings(host.current_project)
        if binding.definition.name == "project_unload"
    )
    host.create_project(name="second", root_dir=second_root)
    host.switch_project("second")

    await unload_binding.invoke({})
    await ide_binding.invoke({})

    assert created == ["first", "first"]


def test_duplicate_tool_names_are_rejected(tmp_path) -> None:
    host, _ = _host(tmp_path)

    class DuplicateProvider:
        def bindings(self, current_project):
            async def invoke(arguments: dict[str, Any]) -> ToolCallOutcome:
                return ToolCallOutcome({})

            return (ToolBinding(Tool(name="same", inputSchema={"type": "object"}), invoke),)

    catalog = DynamicToolCatalog((DuplicateProvider(), DuplicateProvider()))

    with pytest.raises(ValueError, match="Duplicate MCP tool name: same"):
        catalog.bindings(None)


def test_duplicate_resource_base_uris_are_rejected() -> None:
    class ResourceProvider:
        def __init__(self, priority: int) -> None:
            self.priority = priority

        def bindings(self, current_project):
            async def read(uri: str) -> str:
                return uri

            return (
                ResourceBinding(
                    Resource(
                        uri=AnyUrl(f"window://same-project?priority={self.priority}"),
                        name=str(self.priority),
                    ),
                    read,
                ),
            )

    catalog = DynamicResourceCatalog((ResourceProvider(0), ResourceProvider(1)))

    with pytest.raises(ValueError, match="Duplicate MCP resource base URI: window://same-project"):
        catalog.bindings(None)


@pytest.mark.asyncio
async def test_notification_dispatch_covers_independent_paths_and_send_failure(tmp_path, monkeypatch) -> None:
    host, _ = _host(tmp_path)
    with MCPServerConfig.change_config_sources(
        DataSource(data={"transport": "stdio", "project_registry_path": str(tmp_path / "projects.json")})
    ):
        server = BaseMCPServer(
            MCPServerConfig(),
            "notification-test",
            host,
            (_NotificationProvider(),),
            (),
        )
    notifications: list[str] = []

    async def handle_message(message: Any) -> None:
        if isinstance(message, ServerNotification):
            notifications.append(message.root.method)

    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                lambda: server.server.run(
                    server_streams[0],
                    server_streams[1],
                    server.initialization_options(),
                    raise_exceptions=True,
                )
            )
            async with ClientSession(*client_streams, message_handler=handle_message) as client:
                await client.initialize()
                assert (await client.call_tool("NotifyNeither", {})).isError is False
                assert notifications == []

                assert (await client.call_tool("NotifyTools", {})).isError is False
                assert notifications == ["notifications/tools/list_changed"]
                notifications.clear()

                assert (await client.call_tool("NotifyResources", {})).isError is False
                assert notifications == ["notifications/resources/list_changed"]
                notifications.clear()

                async def fail_notification(*, tools: bool, resources: bool) -> None:
                    raise RuntimeError("notification transport failed")

                monkeypatch.setattr(server, "_notify_catalog_changes", fail_notification)
                result = await client.call_tool("NotifyTools", {})
                assert result.isError is False
                assert result.structuredContent == {"notified": "NotifyTools"}
                assert notifications == []
            task_group.cancel_scope.cancel()
    server.close()
