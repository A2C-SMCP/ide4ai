"""Transport-scope and dynamic server initialization tests."""

from __future__ import annotations

import pytest
from confz import DataSource

from ide4ai.a2c_smcp.cli import IDEMCPServer
from ide4ai.a2c_smcp.config import MCPServerConfig


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
            assert {"Bash", "Glob", "Lsp", "project_unload"} <= names
        finally:
            server.close()


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_network_transports_are_explicitly_rejected(tmp_path, transport: str) -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(data={"transport": transport, "project_registry_path": str(tmp_path / "projects.json")})
    ):
        with pytest.raises(ValueError, match="legacy stdio only"):
            IDEMCPServer(MCPServerConfig())
