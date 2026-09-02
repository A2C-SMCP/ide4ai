"""Unit coverage for project-driven MCP catalogs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import anyio
import pytest
from confz import DataSource
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import (
    CallToolResult,
    ReadResourceResult,
    Resource,
    ServerNotification,
    TextContent,
    TextResourceContents,
    Tool,
)
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
from ide4ai.a2c_smcp.projects import (
    ProjectBusyError,
    ProjectHost,
    ProjectRegistry,
    ProjectTerminalRuntimeManager,
)
from ide4ai.a2c_smcp.providers import (
    IDEToolProvider,
    ProjectToolProvider,
    TerminalToolProvider,
    TFBashResourceProvider,
    TFBashToolProvider,
    WindowResourceProvider,
)
from ide4ai.a2c_smcp.resource_events import ResourceUpdate
from ide4ai.a2c_smcp.resource_updates import ResourceUpdateHub
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


class _FakeEmbeddedRuntime:
    TOOL_NAMES = (
        "shell_open",
        "shell_exec",
        "shell_read",
        "shell_write",
        "shell_signal",
        "shell_list",
        "shell_close",
    )

    def __init__(self, project_name: str, *, close_failures: int = 0) -> None:
        self.project_name = project_name
        self.closed = False
        self.close_failures = close_failures
        self.resource_listeners: set[Callable[[AnyUrl], None]] = set()

    def list_tools(self) -> tuple[Tool, ...]:
        if self.closed:
            raise RuntimeError("closed")
        return tuple(
            Tool(
                name=name,
                inputSchema={"type": "object", "additionalProperties": False},
                outputSchema={"type": "object"},
                _meta={"a2c_tool_meta": {"tags": ["BuildIn"]}},
            )
            for name in self.TOOL_NAMES
        )

    def list_resources(self) -> tuple[Resource, ...]:
        if self.closed:
            raise RuntimeError("closed")
        return (
            Resource(
                uri=AnyUrl("window://io.github.a2c-smcp.tfbash/shell-overview"),
                name="Shell Overview",
                mimeType="text/markdown",
            ),
        )

    def read_resource(self, uri: str | AnyUrl) -> ReadResourceResult:
        if self.closed:
            raise RuntimeError("closed")
        return ReadResourceResult(
            contents=[TextResourceContents(uri=AnyUrl(uri), mimeType="text/markdown", text=self.project_name)]
        )

    def subscribe_resource_updates(self, listener: Callable[[AnyUrl], None]) -> Callable[[], None]:
        self.resource_listeners.add(listener)

        def unsubscribe() -> None:
            self.resource_listeners.discard(listener)

        return unsubscribe

    async def call_tool(self, name: str, arguments=None) -> CallToolResult:
        if self.closed:
            raise RuntimeError("closed")
        return CallToolResult(
            content=[TextContent(type="text", text=name)],
            structuredContent={"project": self.project_name, "tool": name},
        )

    async def aclose(self) -> None:
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("cleanup failed")
        self.closed = True


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
    empty_bindings = provider.bindings(None)
    project_list = next(binding for binding in empty_bindings if binding.definition.name == "project_list")
    empty = await project_list.invoke({})
    assert empty.result == {"projects": [], "current_project": None}
    create = next(binding for binding in empty_bindings if binding.definition.name == "project_create")

    created = await create.invoke({"name": "one", "root_dir": str(tmp_path)})

    assert "id" not in created.result["project"]
    bindings = provider.bindings(host.current_project)
    project_list = next(binding for binding in bindings if binding.definition.name == "project_list")
    listed = await project_list.invoke({})
    assert "id" not in listed.result["projects"][0]
    assert "current" not in listed.result["projects"][0]
    assert listed.result["current_project"] == "one"

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


@pytest.mark.asyncio
async def test_terminal_switch_exposes_exact_tfbash_tools_and_preserves_contracts(tmp_path) -> None:
    host, _ = _host(tmp_path)
    host.create_project(name="one", root_dir=tmp_path)
    runtimes: list[_FakeEmbeddedRuntime] = []

    async def factory(project, options):
        runtime = _FakeEmbeddedRuntime(project.name)
        runtimes.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    terminal_provider = TerminalToolProvider(host, manager)
    tfbash_provider = TFBashToolProvider(host, manager)
    catalog = DynamicToolCatalog((terminal_provider, tfbash_provider))
    resource_catalog = DynamicResourceCatalog((TFBashResourceProvider(host, manager),))

    assert [binding.definition.name for binding in catalog.bindings(host.current_project)] == ["terminal_start"]
    assert resource_catalog.bindings(host.current_project) == ()
    terminal = catalog.find(host.current_project, "terminal_start")
    assert terminal is not None
    assert set(terminal.definition.inputSchema["properties"]) == {
        "cwd",
        "startup_command",
        "shell",
        "environment",
        "command_timeout_ms",
        "shutdown_grace_ms",
        "close_timeout_ms",
    }
    assert "root_dir" not in terminal.definition.inputSchema["properties"]
    assert terminal.definition.inputSchema["properties"]["shutdown_grace_ms"]["maximum"] == 60_000
    assert terminal.definition.inputSchema["properties"]["close_timeout_ms"]["maximum"] == 60_000
    assert terminal.definition.description is not None
    assert "does not create a Shell" in terminal.definition.description
    enabled = await terminal.invoke({})
    assert enabled.changes.tools is True
    assert enabled.changes.resources is True
    assert enabled.result["terminal"] == {
        "enabled": True,
        "state": "open",
        "root_dir": str(tmp_path.resolve()),
        "configuration": {
            "cwd": str(tmp_path.resolve()),
            "shell": None,
            "startup_command_configured": False,
            "environment_override_count": 0,
            "command_timeout_ms": 120_000,
            "shutdown_grace_ms": 3_000,
            "close_timeout_ms": 5_000,
        },
    }

    bindings = catalog.bindings(host.current_project)
    assert [binding.definition.name for binding in bindings] == [
        "shell_close",
        "shell_exec",
        "shell_list",
        "shell_open",
        "shell_read",
        "shell_signal",
        "shell_write",
        "terminal_close",
    ]
    overview = resource_catalog.bindings(host.current_project)
    assert len(overview) == 1
    assert str(overview[0].definition.uri) == "window://io.github.a2c-smcp.tfbash/shell-overview"
    rendered = await overview[0].read(str(overview[0].definition.uri))
    assert rendered[0].content == "one"
    shell_list = catalog.find(host.current_project, "shell_list")
    assert shell_list is not None
    assert shell_list.definition.outputSchema == {"type": "object"}
    assert shell_list.definition.meta == {"a2c_tool_meta": {"tags": ["BuildIn"]}}
    called = await shell_list.invoke({})
    assert isinstance(called.result, CallToolResult)
    assert called.result.structuredContent == {"project": "one", "tool": "shell_list"}

    terminal = catalog.find(host.current_project, "terminal_close")
    assert terminal is not None
    assert terminal.definition.description is not None
    assert "Gracefully close" in terminal.definition.description
    disabled = await terminal.invoke({})
    assert disabled.changes.tools is True
    assert disabled.changes.resources is True
    assert runtimes[0].closed is True
    assert [binding.definition.name for binding in catalog.bindings(host.current_project)] == ["terminal_start"]
    assert resource_catalog.bindings(host.current_project) == ()


@pytest.mark.asyncio
async def test_terminal_catalog_exposes_close_during_opening_and_closing(tmp_path) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="one", root_dir=tmp_path)
    open_entered = anyio.Event()
    release_open = anyio.Event()
    close_entered = anyio.Event()
    release_close = anyio.Event()

    class BlockingRuntime(_FakeEmbeddedRuntime):
        async def aclose(self) -> None:
            close_entered.set()
            await release_close.wait()
            await super().aclose()

    async def factory(captured, options):
        assert captured == project
        open_entered.set()
        await release_open.wait()
        return BlockingRuntime(captured.name)

    manager = ProjectTerminalRuntimeManager(factory)
    catalog = DynamicToolCatalog((TerminalToolProvider(host, manager), TFBashToolProvider(host, manager)))
    start = catalog.find(project, "terminal_start")
    assert start is not None

    async def invoke_start() -> None:
        await start.invoke({})

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(invoke_start)
        await open_entered.wait()
        assert manager.state(project).value == "opening"
        assert [binding.definition.name for binding in catalog.bindings(project)] == ["terminal_close"]
        release_open.set()

    close = catalog.find(project, "terminal_close")
    assert close is not None

    async def invoke_close() -> None:
        await close.invoke({})

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(invoke_close)
        await close_entered.wait()
        assert manager.state(project).value == "closing"
        assert [binding.definition.name for binding in catalog.bindings(project)] == ["terminal_close"]
        assert catalog.find(project, "shell_list") is None
        release_close.set()

    assert [binding.definition.name for binding in catalog.bindings(project)] == ["terminal_start"]


@pytest.mark.asyncio
async def test_terminal_runtime_follows_project_selection_and_unload(tmp_path) -> None:
    host, _ = _host(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = host.create_project(name="first", root_dir=first_root)
    runtimes: dict[str, _FakeEmbeddedRuntime] = {}

    async def factory(project, options):
        runtime = _FakeEmbeddedRuntime(project.name)
        runtimes[project.name] = runtime
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    project_provider = ProjectToolProvider(host, manager)
    terminal_provider = TerminalToolProvider(host, manager)
    tfbash_provider = TFBashToolProvider(host, manager)
    catalog = DynamicToolCatalog((project_provider, terminal_provider, tfbash_provider))

    terminal = catalog.find(first, "terminal_start")
    assert terminal is not None
    await terminal.invoke({})
    assert catalog.find(first, "shell_list") is not None

    host.create_project(name="second", root_dir=second_root)
    second = host.switch_project("second")
    assert catalog.find(second, "shell_list") is None
    host.switch_project("first")
    assert catalog.find(first, "shell_list") is not None

    unload = catalog.find(first, "project_unload")
    assert unload is not None
    outcome = await unload.invoke({})
    assert outcome.changes.tools is True
    assert runtimes["first"].closed is True
    assert catalog.find(first, "shell_list") is None


@pytest.mark.asyncio
async def test_busy_project_unload_keeps_terminal_open_and_catalog_unchanged(tmp_path) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="one", root_dir=tmp_path)
    runtime = _FakeEmbeddedRuntime(project.name)

    async def factory(captured, options):
        assert captured == project
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    catalog = DynamicToolCatalog(
        (
            ProjectToolProvider(host, manager),
            TerminalToolProvider(host, manager),
            TFBashToolProvider(host, manager),
        )
    )
    terminal = catalog.find(project, "terminal_start")
    unload = catalog.find(project, "project_unload")
    assert terminal is not None
    assert unload is not None
    await terminal.invoke({})

    with host.lease_project(project):
        with pytest.raises(ProjectBusyError, match="active call"):
            await unload.invoke({})

    assert runtime.closed is False
    assert catalog.find(project, "shell_list") is not None
    await manager.aclose_all()


@pytest.mark.asyncio
async def test_terminal_close_failure_reports_error_and_invalidates_tools(tmp_path) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="one", root_dir=tmp_path)
    runtime = _FakeEmbeddedRuntime(project.name, close_failures=1)

    async def factory(captured, options):
        assert captured == project
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    catalog = DynamicToolCatalog((TerminalToolProvider(host, manager), TFBashToolProvider(host, manager)))
    terminal = catalog.find(project, "terminal_start")
    assert terminal is not None
    await terminal.invoke({})

    terminal = catalog.find(project, "terminal_close")
    assert terminal is not None
    failed = await terminal.invoke({})

    assert isinstance(failed.result, CallToolResult)
    assert failed.result.isError is True
    assert failed.result.structuredContent is not None
    assert failed.result.structuredContent["error"]["code"] == "TERMINAL_CLOSE_FAILED"
    assert failed.changes.tools is True
    assert failed.changes.resources is True
    assert catalog.find(project, "shell_list") is None
    terminal = catalog.find(project, "terminal_close")
    assert terminal is not None
    retried = await terminal.invoke({})
    assert isinstance(retried.result, dict)
    assert retried.result["terminal"]["state"] == "closed"


@pytest.mark.asyncio
async def test_unload_cleanup_failure_notifies_real_mcp_client(tmp_path) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="one", root_dir=tmp_path)
    runtime = _FakeEmbeddedRuntime(project.name, close_failures=1)

    async def factory(captured, options):
        assert captured == project
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    providers = (
        ProjectToolProvider(host, manager),
        TerminalToolProvider(host, manager),
        TFBashToolProvider(host, manager),
    )
    with MCPServerConfig.change_config_sources(
        DataSource(data={"transport": "stdio", "project_registry_path": str(tmp_path / "projects.json")})
    ):
        server = BaseMCPServer(MCPServerConfig(), "terminal-cleanup-test", host, providers, ())
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
                assert (await client.call_tool("terminal_start", {})).isError is False
                notifications.clear()

                failed = await client.call_tool("project_unload", {})

                assert failed.isError is True
                assert failed.structuredContent is not None
                assert failed.structuredContent["error"]["code"] == "PROJECT_TERMINAL_CLEANUP_FAILED"
                assert notifications == [
                    "notifications/tools/list_changed",
                    "notifications/resources/list_changed",
                ]
                assert [tool.name for tool in (await client.list_tools()).tools] == [
                    "project_create",
                    "project_delete",
                    "project_list",
                    "project_switch",
                    "project_unload",
                    "terminal_close",
                ]
            task_group.cancel_scope.cancel()
    await manager.close(project)
    server.close()


@pytest.mark.asyncio
async def test_project_delete_closes_and_forgets_terminal_runtime(tmp_path) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="one", root_dir=tmp_path)
    runtime = _FakeEmbeddedRuntime(project.name)

    async def factory(captured, options):
        assert captured == project
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    catalog = DynamicToolCatalog(
        (
            ProjectToolProvider(host, manager),
            TerminalToolProvider(host, manager),
            TFBashToolProvider(host, manager),
        )
    )
    terminal = catalog.find(project, "terminal_start")
    assert terminal is not None
    await terminal.invoke({})

    delete = catalog.find(project, "project_delete")
    assert delete is not None
    deleted = await delete.invoke({"name": project.name})

    assert deleted.changes.tools is True
    assert runtime.closed is True
    assert manager.has_live_runtimes is False
    assert host.current_project is None


@pytest.mark.asyncio
async def test_project_delete_cleanup_failure_keeps_project_retryable(tmp_path) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="one", root_dir=tmp_path)
    runtime = _FakeEmbeddedRuntime(project.name, close_failures=1)

    async def factory(captured, options):
        assert captured == project
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    catalog = DynamicToolCatalog(
        (
            ProjectToolProvider(host, manager),
            TerminalToolProvider(host, manager),
            TFBashToolProvider(host, manager),
        )
    )
    terminal = catalog.find(project, "terminal_start")
    delete = catalog.find(project, "project_delete")
    assert terminal is not None
    assert delete is not None
    await terminal.invoke({})

    failed = await delete.invoke({"name": project.name})

    assert isinstance(failed.result, CallToolResult)
    assert failed.result.isError is True
    assert failed.result.structuredContent is not None
    assert failed.result.structuredContent["error"] == {
        "code": "PROJECT_TERMINAL_CLEANUP_FAILED",
        "message": "cleanup failed",
        "operation": "delete",
        "project_name": "one",
        "project_deleted": False,
        "terminal_cleanup_pending": True,
    }
    assert host.registry.find(project.id) == project
    assert host.current_project == project
    assert manager.has_live_runtimes is True
    assert catalog.find(project, "shell_list") is None

    close = catalog.find(project, "terminal_close")
    assert close is not None
    closed = await close.invoke({})
    assert isinstance(closed.result, dict)

    start = catalog.find(project, "terminal_start")
    assert start is not None
    restarted = await start.invoke({})
    assert isinstance(restarted.result, dict)
    assert restarted.result["terminal"]["state"] == "open"

    retried = await delete.invoke({"name": project.name})

    assert isinstance(retried.result, dict)
    assert retried.result["project"]["name"] == project.name
    assert host.registry.list() == ()
    assert runtime.closed is True
    assert manager.has_live_runtimes is False


@pytest.mark.asyncio
async def test_project_delete_commit_failure_restores_terminal_start(tmp_path, monkeypatch) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="one", root_dir=tmp_path)
    runtimes: list[_FakeEmbeddedRuntime] = []

    async def factory(captured, options):
        assert captured == project
        runtime = _FakeEmbeddedRuntime(project.name)
        runtimes.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    catalog = DynamicToolCatalog(
        (
            ProjectToolProvider(host, manager),
            TerminalToolProvider(host, manager),
            TFBashToolProvider(host, manager),
        )
    )
    start = catalog.find(project, "terminal_start")
    delete = catalog.find(project, "project_delete")
    assert start is not None
    assert delete is not None
    await start.invoke({})

    original_commit = host.commit_delete

    def fail_commit(captured):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(host, "commit_delete", fail_commit)
    failed = await delete.invoke({"name": project.name})

    assert isinstance(failed.result, CallToolResult)
    assert failed.result.isError is True
    assert host.registry.find(project.id) == project
    restored_start = catalog.find(project, "terminal_start")
    assert restored_start is not None
    restarted = await restored_start.invoke({})
    assert isinstance(restarted.result, dict)
    assert restarted.result["terminal"]["state"] == "open"
    assert len(runtimes) == 2

    monkeypatch.setattr(host, "commit_delete", original_commit)
    delete = catalog.find(project, "project_delete")
    assert delete is not None
    deleted = await delete.invoke({"name": project.name})
    assert isinstance(deleted.result, dict)
    assert host.registry.list() == ()


def test_multiple_registered_projects_auto_select_first_project(tmp_path) -> None:
    host, _ = _host(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    host.create_project(name="first", root_dir=first_root)
    host.create_project(name="second", root_dir=second_root)
    restarted = ProjectHost(host.registry, lambda project: cast(IDE, _FakeIDE(project.name)))
    catalog = DynamicToolCatalog((ProjectToolProvider(restarted), IDEToolProvider(restarted, (_ProjectNameTool,))))

    assert restarted.current_project is not None
    assert restarted.current_project.name == "first"
    assert [binding.definition.name for binding in catalog.bindings(restarted.current_project)] == [
        "project_create",
        "project_delete",
        "project_list",
        "project_switch",
        "project_unload",
        "ProjectName",
    ]


@pytest.mark.asyncio
async def test_project_list_reports_single_collection_level_current_project(tmp_path) -> None:
    host, _ = _host(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    host.create_project(name="first", root_dir=first_root)
    host.create_project(name="second", root_dir=second_root)
    restarted = ProjectHost(host.registry, lambda project: cast(IDE, _FakeIDE(project.name)))
    provider = ProjectToolProvider(restarted)
    project_list = next(binding for binding in provider.bindings(None) if binding.definition.name == "project_list")

    initial = await project_list.invoke({})
    assert initial.result["current_project"] == "first"
    assert all("current" not in project for project in initial.result["projects"])

    restarted.switch_project("second")
    selected = await project_list.invoke({})
    assert selected.result["current_project"] == "second"
    assert all("current" not in project for project in selected.result["projects"])

    restored = ProjectHost(
        ProjectRegistry(host.registry.path),
        lambda project: cast(IDE, _FakeIDE(project.name)),
    )
    assert restored.current_project is not None
    assert restored.current_project.name == "second"


@pytest.mark.asyncio
async def test_project_list_uses_one_atomic_registry_view(tmp_path, monkeypatch) -> None:
    host, _ = _host(tmp_path)
    project = host.create_project(name="only", root_dir=tmp_path)
    provider = ProjectToolProvider(host)
    project_list = next(binding for binding in provider.bindings(project) if binding.definition.name == "project_list")
    calls = 0

    def view():
        nonlocal calls
        calls += 1
        return (project,), project

    monkeypatch.setattr(host, "project_view", view)
    result = await project_list.invoke({})

    assert calls == 1
    assert result.result["current_project"] == "only"
    assert [item["name"] for item in result.result["projects"]] == ["only"]


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
async def test_resource_update_hub_filters_old_projects_and_unsubscribed_sessions(tmp_path) -> None:
    host, _ = _host(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = host.create_project(name="first", root_dir=first_root)
    second = host.create_project(name="second", root_dir=second_root)
    host.switch_project(first.id)
    source_listeners = []
    valid_sources: set[object] = set()

    def subscribe_source(listener):
        source_listeners.append(listener)
        return lambda: source_listeners.remove(listener)

    hub = ResourceUpdateHub(host, subscribe_source, lambda update: update.source_id in valid_sources)
    uri = AnyUrl("window://io.github.a2c-smcp.tfbash/shell-overview")
    first_generation = object()
    second_generation = object()
    valid_sources.add(first_generation)

    class Session:
        def __init__(self) -> None:
            self.updated: list[str] = []
            self.received = anyio.Event()

        async def send_resource_updated(self, updated_uri: AnyUrl) -> None:
            self.updated.append(str(updated_uri))
            self.received.set()

    session = Session()
    hub.connect()
    hub.subscribe(session, uri)
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(hub.run)
        await anyio.to_thread.run_sync(source_listeners[0], ResourceUpdate(first, first_generation, uri))
        with anyio.fail_after(2):
            await session.received.wait()
        assert session.updated == [str(uri)]

        session.received = anyio.Event()
        await anyio.to_thread.run_sync(source_listeners[0], ResourceUpdate(first, first_generation, uri))
        valid_sources.remove(first_generation)
        valid_sources.add(second_generation)
        with anyio.move_on_after(0.2) as closed_generation_suppressed:
            await session.received.wait()
        assert closed_generation_suppressed.cancel_called is True

        await anyio.to_thread.run_sync(source_listeners[0], ResourceUpdate(first, second_generation, uri))
        with anyio.fail_after(2):
            await session.received.wait()
        assert session.updated == [str(uri), str(uri)]

        host.switch_project(second.id)
        session.received = anyio.Event()
        await anyio.to_thread.run_sync(source_listeners[0], ResourceUpdate(first, second_generation, uri))
        with anyio.move_on_after(0.2) as old_project_suppressed:
            await session.received.wait()
        assert old_project_suppressed.cancel_called is True

        host.switch_project(first.id)
        session.received = anyio.Event()
        await anyio.to_thread.run_sync(source_listeners[0], ResourceUpdate(first, second_generation, uri))
        host.switch_project(second.id)
        host.switch_project(first.id)
        with anyio.move_on_after(0.2) as switched_away_and_back:
            await session.received.wait()
        assert switched_away_and_back.cancel_called is True

        session.received = anyio.Event()
        await anyio.to_thread.run_sync(source_listeners[0], ResourceUpdate(first, second_generation, uri))
        with anyio.fail_after(2):
            await session.received.wait()
        assert session.updated == [str(uri), str(uri), str(uri)]

        hub.unsubscribe(session, uri)
        session.received = anyio.Event()
        await anyio.to_thread.run_sync(source_listeners[0], ResourceUpdate(first, second_generation, uri))
        with anyio.move_on_after(0.2) as unsubscribed:
            await session.received.wait()
        assert unsubscribed.cancel_called is True
        hub.stop()

    assert source_listeners == []


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
