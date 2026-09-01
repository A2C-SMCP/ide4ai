"""MCP Server configuration tests without project bootstrap compatibility."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

from confz import CLArgSource, DataSource, EnvSource

from ide4ai.a2c_smcp.config import MCPServerConfig


def test_default_config_contains_registry_but_no_project_bootstrap_fields() -> None:
    with MCPServerConfig.change_config_sources(DataSource(data={})):
        config = MCPServerConfig()

    assert config.transport == "stdio"
    assert config.project_registry_path.endswith("projects.json")
    assert config.cmd_time_out == 10
    assert config.render_with_symbols is True
    assert config.max_active_models == 3
    assert config.enable_simple_view_mode is True
    assert {"root_dir", "project_name", "lsp_mode"}.isdisjoint(MCPServerConfig.model_fields)


def test_project_ide_defaults_do_not_contain_project_metadata() -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "cmd_white_list": ["pwd"],
                "cmd_time_out": 30,
                "render_with_symbols": False,
                "max_active_models": 7,
                "enable_simple_view_mode": False,
            }
        )
    ):
        defaults = MCPServerConfig().to_project_ide_defaults()

    assert {"root_dir", "project_name", "lsp_settings", "language_profiles"}.isdisjoint(defaults)
    assert defaults["cmd_time_out"] == 30
    assert defaults["render_with_symbols"] is False
    assert defaults["max_active_models"] == 7
    assert defaults["enable_simple_view_mode"] is False


def test_custom_project_registry_path() -> None:
    with MCPServerConfig.change_config_sources(DataSource(data={"project_registry_path": "/tmp/custom.json"})):
        assert MCPServerConfig().project_registry_path == "/tmp/custom.json"


def test_environment_configuration_ignores_removed_project_bootstrap_variables() -> None:
    source = EnvSource(
        allow_all=True,
        prefix="",
        remap={
            "TRANSPORT": "transport",
            "PROJECT_REGISTRY_PATH": "project_registry_path",
            "CMD_TIMEOUT": "cmd_time_out",
        },
    )
    environment = {
        "TRANSPORT": "stdio",
        "PROJECT_REGISTRY_PATH": "/tmp/env-projects.json",
        "CMD_TIMEOUT": "42",
        "PROJECT_ROOT": "/removed/root",
        "PROJECT_NAME": "removed-name",
    }
    with patch.dict(os.environ, environment, clear=True), MCPServerConfig.change_config_sources(source):
        config = MCPServerConfig()

    assert config.project_registry_path == "/tmp/env-projects.json"
    assert config.cmd_time_out == 42
    assert not hasattr(config, "root_dir")
    assert not hasattr(config, "project_name")


def test_command_line_configuration_and_priority() -> None:
    env_source = EnvSource(
        allow_all=True,
        prefix="",
        remap={"PROJECT_REGISTRY_PATH": "project_registry_path", "CMD_TIMEOUT": "cmd_time_out"},
    )
    cli_source = CLArgSource(
        prefix="",
        remap={"project-registry-path": "project_registry_path", "cmd-timeout": "cmd_time_out"},
    )
    with (
        patch.dict(
            os.environ,
            {"PROJECT_REGISTRY_PATH": "/tmp/env.json", "CMD_TIMEOUT": "11"},
            clear=True,
        ),
        patch.object(
            sys,
            "argv",
            ["ide4ai-mcp", "--project-registry-path", "/tmp/cli.json", "--cmd-timeout", "24"],
        ),
        MCPServerConfig.change_config_sources([env_source, cli_source]),
    ):
        config = MCPServerConfig()

    assert config.project_registry_path == "/tmp/cli.json"
    assert config.cmd_time_out == 24
