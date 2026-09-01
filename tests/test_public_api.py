from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path
from unittest.mock import MagicMock

from confz import DataSource

import ide4ai
from ide4ai import IDE, IDEInstance, IDESingleton, LanguageId, Workspace
from ide4ai.a2c_smcp import IDEMCPServer
from ide4ai.a2c_smcp.cli import main as mcp_cli_main
from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.tools.lsp import LspTool
from ide4ai.lsp.manager import LanguageProfile, LspServerSpec, LspSettings, LspState, LspStatus


def test_public_api_exposes_only_language_neutral_types() -> None:
    assert IDE.__name__ == "IDE"
    assert Workspace.__name__ == "Workspace"
    assert IDEInstance.__name__ == "IDEInstance"
    assert IDEMCPServer.__name__ == "IDEMCPServer"
    assert LanguageId("rust") == "rust"
    for removed_name in ("PythonIDE", "PyWorkspace", "PyIDESingleton", "PythonIDEMCPServer"):
        assert not hasattr(ide4ai, removed_name)


def test_distribution_exposes_only_generic_mcp_cli() -> None:
    scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}
    assert scripts["ide4ai-mcp"] == "ide4ai.a2c_smcp.cli:main"
    assert "py-ide4ai-mcp" not in scripts


def test_distribution_pins_compatible_mcp_major() -> None:
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert '"mcp>=1.19.0,<2.0.0"' in pyproject


def test_generic_mcp_cli_help_does_not_start_server(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["ide4ai-mcp", "--help"])
    mcp_cli_main()
    output = capsys.readouterr().out
    assert "usage: ide4ai-mcp" in output
    assert "--lsp-profile-language-id" in output
    assert "--project-registry-path" in output


def test_generic_mcp_module_entrypoint_displays_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ide4ai.a2c_smcp.cli", "--help"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "usage: ide4ai-mcp" in result.stdout


def test_public_docs_use_executable_distribution_commands_and_paths() -> None:
    repository = Path(__file__).parents[1]
    mcp_readme = (repository / "ide4ai/a2c_smcp/README.md").read_text(encoding="utf-8")
    transport_docs = (repository / "tests/integration/python_ide/TEST_TRANSPORTS.md").read_text(encoding="utf-8")
    pexpect_docs = (repository / "docs/environment/terminal/PEXPECT_USAGE.md").read_text(encoding="utf-8")
    assert '"args": ["ide4ai", "ide4ai-mcp"' not in mcp_readme
    assert mcp_readme.count('"--from", "ide4ai"') >= 3
    assert "tests/integration/python_ide/test_mcp_server_" not in transport_docs
    assert "from ide4ai.base import IDE" not in pexpect_docs
    assert "white_list=" not in pexpect_docs
    assert "init_venv=" not in pexpect_docs


def test_mcp_config_registers_custom_lsp_profile(tmp_path: Path) -> None:
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "root_dir": str(tmp_path),
                "project_name": "custom-rust-config",
                "lsp_mode": "explicit",
                "lsp_language_id": "rust",
                "lsp_server_command": "rust-analyzer",
                "lsp_file_extensions": ".rs,.rlib",
                "lsp_root_markers": "Cargo.toml,.git",
            }
        )
    ):
        config = MCPServerConfig()
    kwargs = config.to_ide_kwargs()
    assert kwargs["lsp_settings"].mode == "explicit"
    assert kwargs["lsp_settings"].language_id == "rust"
    rust = next(profile for profile in kwargs["language_profiles"] if profile.language_id == "rust")
    assert rust.server.command == ("rust-analyzer",)
    assert rust.file_extensions == (".rs", ".rlib")
    assert rust.root_markers == ("Cargo.toml", ".git")


def test_mcp_lsp_tool_reports_status_and_reloads() -> None:
    workspace = MagicMock()
    workspace.lsp_status = LspStatus(LspState.READY, "python")
    workspace.reload_lsp.return_value = LspStatus(LspState.UNDETECTED, reason="reloaded")
    ide = MagicMock()
    ide.workspace = workspace
    tool = LspTool(ide)

    assert asyncio.run(tool.execute({"action": "status"}))["state"] == "ready"
    assert asyncio.run(tool.execute({"action": "reload"})) == {
        "state": "undetected",
        "language_id": None,
        "reason": "reloaded",
    }
    workspace.reload_lsp.assert_called_once()


def test_public_ide_uses_injected_extensible_profile(tmp_path: Path) -> None:
    source = tmp_path / "main.rs"
    source.write_text("fn main() {}\n", encoding="utf-8")
    rust = LanguageProfile(
        language_id="rust",
        file_extensions=(".rs",),
        root_markers=("Cargo.toml",),
        server=LspServerSpec(("rust-analyzer",)),
    )
    ide = IDE(
        root_dir=str(tmp_path),
        project_name="rust-workspace",
        language_profiles=(rust,),
        lsp_settings=LspSettings(mode="disabled"),
    )
    try:
        model = ide.workspace.open_file(uri=source.as_uri())
        assert model.get_language_id() == "rust"
    finally:
        ide.close()


def test_public_ide_render_degrades_without_lsp(tmp_path: Path) -> None:
    first = tmp_path / "first.rs"
    second = tmp_path / "second.rs"
    first.write_text("fn first() {}\n", encoding="utf-8")
    second.write_text("fn second() {}\n", encoding="utf-8")
    rust = LanguageProfile(
        language_id="rust",
        file_extensions=(".rs",),
        root_markers=("Cargo.toml",),
        server=LspServerSpec(("missing-rust-language-server",)),
    )
    cases = (
        ("disabled", True, LspSettings(mode="disabled")),
        ("symbols-off", False, LspSettings(mode="explicit", language_id="rust")),
        ("unavailable", True, LspSettings(mode="explicit", language_id="rust")),
    )
    for project_name, render_with_symbols, settings in cases:
        ide = IDE(
            root_dir=str(tmp_path),
            project_name=project_name,
            render_with_symbols=render_with_symbols,
            language_profiles=(rust,),
            lsp_settings=settings,
        )
        try:
            ide.workspace.open_file(uri=first.as_uri())
            ide.workspace.open_file(uri=second.as_uri())
            rendered = ide.workspace.render(verbose=True)
            assert "fn second()" in rendered
            assert str(first.as_uri()) in rendered
        finally:
            ide.close()


def test_generic_mcp_server_constructs_custom_language_ide(tmp_path: Path) -> None:
    (tmp_path / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    project_name = "custom-rust-mcp-profile"
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "root_dir": str(tmp_path),
                "project_name": project_name,
                "project_registry_path": str(tmp_path / "projects.json"),
                "lsp_mode": "auto",
                "lsp_profile_language_id": "rust",
                "lsp_server_command": "rust-analyzer",
                "lsp_file_extensions": ".rs",
                "lsp_root_markers": "Cargo.toml",
            }
        )
    ):
        config = MCPServerConfig()
    server = IDEMCPServer(config)
    try:
        assert server.ide.workspace.lsp_status == LspStatus(LspState.READY, "rust")
        assert server.ide.workspace._lsp_manager.profile is not None
        assert server.ide.workspace._lsp_manager.profile.server.command == ("rust-analyzer",)
    finally:
        server.close()
        IDESingleton._instances.pop(f"IDEInstance{project_name}", None)


def test_mcp_examples_import_the_generic_server() -> None:
    for module_name in (
        "examples.mcp_server_example",
        "examples.mcp_server_sse_example",
        "examples.mcp_server_streamable_http_example",
    ):
        importlib.import_module(module_name)
