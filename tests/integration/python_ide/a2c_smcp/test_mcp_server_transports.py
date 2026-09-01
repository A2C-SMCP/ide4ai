"""Transport-scope and dynamic server initialization tests."""

from __future__ import annotations

import anyio
import pytest
from confz import DataSource
from mcp.types import CallToolResult

from ide4ai.a2c_smcp.cli import IDEMCPServer
from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.projects import ProjectError


@pytest.mark.parametrize("transport", ["stdio", "sse", "streamable-http"])
def test_transport_values_remain_parseable(transport: str) -> None:
    with MCPServerConfig.change_config_sources(DataSource(data={"transport": transport})):
        assert MCPServerConfig().transport == transport


def test_default_server_starts_without_loading_an_ide(tmp_path) -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(data={"transport": "stdio", "project_registry_path": str(tmp_path / "projects.json")})
    ):
        server = IDEMCPServer(MCPServerConfig())
        try:
            assert server.project_host.current_project is None
            assert [binding.definition.name for binding in server.tool_catalog.bindings(None)] == [
                "project_create",
                "project_delete",
                "project_list",
                "project_switch",
            ]
            assert server.resource_catalog.bindings(None) == ()
        finally:
            server.close()


def test_legacy_bootstrap_selects_project_without_loading_ide(tmp_path) -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "transport": "stdio",
                "root_dir": str(tmp_path),
                "project_name": "bootstrap",
                "project_registry_path": str(tmp_path / "projects.json"),
            }
        )
    ):
        server = IDEMCPServer(MCPServerConfig())
        try:
            assert server.project_host.current_project is not None
            names = {
                binding.definition.name for binding in server.tool_catalog.bindings(server.project_host.current_project)
            }
            assert {"Terminal", "Glob", "Lsp", "project_unload"} <= names
            assert "Bash" not in names
        finally:
            server.close()


@pytest.mark.asyncio
async def test_async_server_close_releases_enabled_terminal_runtime(tmp_path) -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "transport": "stdio",
                "root_dir": str(tmp_path),
                "project_name": "bootstrap",
                "project_registry_path": str(tmp_path / "projects.json"),
            }
        )
    ):
        server = IDEMCPServer(MCPServerConfig())
        project = server.project_host.current_project
        assert project is not None
        terminal = server.tool_catalog.find(project, "Terminal")
        assert terminal is not None
        await terminal.invoke({})
        shell_open = server.tool_catalog.find(project, "shell_open")
        assert shell_open is not None
        opened = await shell_open.invoke({})
        assert isinstance(opened.result, CallToolResult)
        assert opened.result.isError is False
        with pytest.raises(ProjectError, match="await server.aclose"):
            server.close()

        with anyio.CancelScope() as scope:
            scope.cancel()
            await server.aclose()

        assert server.project_terminal_manager.has_live_runtimes is False
        with pytest.raises(ProjectError, match="closed"):
            _ = server.project_host.current_project


@pytest.mark.asyncio
async def test_sync_close_rejects_terminal_factory_in_progress(tmp_path, monkeypatch) -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "transport": "stdio",
                "root_dir": str(tmp_path),
                "project_name": "bootstrap",
                "project_registry_path": str(tmp_path / "projects.json"),
            }
        )
    ):
        server = IDEMCPServer(MCPServerConfig())
        project = server.project_host.current_project
        assert project is not None
        factory_entered = anyio.Event()
        release_factory = anyio.Event()

        class BlockingRuntime:
            def __init__(self) -> None:
                self.closed = False

            async def aclose(self) -> None:
                self.closed = True

        runtime = BlockingRuntime()

        async def factory(captured):
            assert captured == project
            factory_entered.set()
            await release_factory.wait()
            return runtime

        monkeypatch.setattr(server.project_terminal_manager, "_runtime_factory", factory)
        terminal = server.tool_catalog.find(project, "Terminal")
        assert terminal is not None
        enable_results = []

        async def enable() -> None:
            enable_results.append(await terminal.invoke({}))

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(enable)
            await factory_entered.wait()
            with pytest.raises(ProjectError, match="await server.aclose"):
                server.close()
            assert server.project_host.current_project == project
            release_factory.set()

        assert len(enable_results) == 1
        assert isinstance(enable_results[0].result, CallToolResult)
        assert enable_results[0].result.isError is True
        assert runtime.closed is True
        assert server.project_terminal_manager.has_live_runtimes is False
        await server.aclose()


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_network_transports_are_explicitly_rejected(tmp_path, transport: str) -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(data={"transport": transport, "project_registry_path": str(tmp_path / "projects.json")})
    ):
        with pytest.raises(ValueError, match="legacy stdio only"):
            IDEMCPServer(MCPServerConfig())
