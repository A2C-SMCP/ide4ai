"""Integration coverage for project-scoped MCP resources."""

from __future__ import annotations

import pytest
from confz import DataSource

from ide4ai.a2c_smcp.cli import IDEMCPServer
from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.projects import ProjectRegistry


@pytest.fixture
def server(tmp_path):
    registry_path = tmp_path / "projects.json"
    project = ProjectRegistry(registry_path).create(name="resource-project", root_dir=tmp_path)
    with MCPServerConfig.change_config_sources(
        DataSource(data={"transport": "stdio", "project_registry_path": str(registry_path)})
    ):
        instance = IDEMCPServer(MCPServerConfig())
    try:
        yield instance, project
    finally:
        instance.close()


def test_selected_project_exposes_one_window_resource_without_loading_ide(server) -> None:
    instance, project = server

    bindings = instance.resource_catalog.bindings(instance.project_host.current_project)

    assert len(bindings) == 1
    definition = bindings[0].definition
    assert str(definition.uri) == f"window://{project.id}?priority=0&fullscreen=true"
    assert definition.name == "IDE Window - resource-project"
    assert definition.description == "IDE window content for the current project."
    assert definition.mimeType == "text/plain"


@pytest.mark.asyncio
async def test_resource_binding_reads_bare_and_parameterized_uri(server) -> None:
    instance, project = server
    binding = instance.resource_catalog.bindings(instance.project_host.current_project)[0]

    bare = await binding.read(f"window://{project.id}")
    parameterized = await binding.read(f"window://{project.id}?priority=75&fullscreen=false")

    assert "IDE Content:" in bare
    assert "IDE Content:" in parameterized


def test_unloaded_server_has_no_resources(tmp_path) -> None:
    registry_path = tmp_path / "projects.json"
    with MCPServerConfig.change_config_sources(
        DataSource(data={"transport": "stdio", "project_registry_path": str(registry_path)})
    ):
        instance = IDEMCPServer(MCPServerConfig())
    try:
        assert instance.project_host.current_project is None
        assert instance.resource_catalog.bindings(None) == ()
    finally:
        instance.close()
