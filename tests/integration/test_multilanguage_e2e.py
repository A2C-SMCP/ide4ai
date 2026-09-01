"""Cross-boundary acceptance tests for the language-neutral IDE/LSP stack."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest
from confz import DataSource
from lsprotocol import types

from ide4ai.a2c_smcp import IDEMCPServer
from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.environment.workspace.workspace import Workspace
from ide4ai.ides import IDESingleton
from ide4ai.lsp.errors import LspError
from ide4ai.lsp.manager import LanguageProfile, LspServerSpec, LspSettings, LspState

FAKE_SERVER = Path(__file__).parents[1] / "lsp" / "fake_lsp_server.py"


def _profile(
    language_id: str,
    extension: str,
    marker: str,
    *,
    command: tuple[str, ...],
) -> LanguageProfile:
    return LanguageProfile(
        language_id=language_id,
        file_extensions=(extension,),
        root_markers=(marker,),
        server=LspServerSpec(command),
    )


def _fake_profile(tmp_path: Path, *, marker_name: str = "fake-server-exit") -> LanguageProfile:
    return _profile(
        "fake",
        ".fake",
        "fake.toml",
        command=(sys.executable, str(FAKE_SERVER), str(tmp_path / marker_name)),
    )


def _wait_until(predicate, *, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert predicate()


def _server_config(tmp_path: Path, project_name: str, **overrides: object) -> MCPServerConfig:
    data: dict[str, object] = {
        "root_dir": str(tmp_path),
        "project_name": project_name,
        "project_registry_path": str(tmp_path / "projects.json"),
        **overrides,
    }
    with MCPServerConfig.change_config_sources(DataSource(data=data)):
        return MCPServerConfig()


def _close_server(server: IDEMCPServer, project_name: str) -> None:
    server.close()
    IDESingleton._instances.pop(f"IDEInstance{project_name}", None)


def test_real_pyright_public_workspace_auto_start_and_close(tmp_path: Path) -> None:
    python_file = tmp_path / "main.py"
    text_file = tmp_path / "notes.txt"
    python_file.write_text("class Example:\n    value = 1\n", encoding="utf-8")
    text_file.write_text("plain notes\n", encoding="utf-8")

    workspace = Workspace(root_dir=str(tmp_path), project_name="real-pyright-e2e")
    session = None
    try:
        assert workspace.lsp_status.state is LspState.READY
        assert workspace.lsp_status.language_id == "python"
        assert workspace._lsp_manager.session is None

        workspace.open_file(uri=text_file.as_uri())
        assert workspace._lsp_manager.session is None

        workspace.open_file(uri=python_file.as_uri())
        session = workspace._lsp_manager.session
        assert session is not None and session.is_running
        response = session.request(
            types.DocumentSymbolRequest(
                id=session.next_request_id(),
                params=types.DocumentSymbolParams(text_document=types.TextDocumentIdentifier(uri=python_file.as_uri())),
            ),
            types.DocumentSymbolResponse,
        )
        assert response.result is not None
        assert any(symbol.name == "Example" for symbol in response.result)
    finally:
        workspace.close()

    assert session is not None
    assert session.returncode == 0


def test_fake_second_language_auto_lazy_start_and_graceful_close(tmp_path: Path) -> None:
    fake_file = tmp_path / "main.fake"
    notes = tmp_path / "notes.txt"
    fake_file.write_text("fake declaration\n", encoding="utf-8")
    notes.write_text("searchable note\n", encoding="utf-8")
    exit_marker = tmp_path / "fake-server-exit"

    workspace = Workspace(
        root_dir=str(tmp_path),
        project_name="fake-language-e2e",
        language_profiles=(_fake_profile(tmp_path),),
    )
    try:
        assert workspace.lsp_status == workspace.lsp_status.__class__(LspState.READY, "fake")
        assert workspace.glob_files(pattern="**/*.fake")
        assert workspace.grep_files(pattern="searchable")["matched"] is True
        workspace.open_file(uri=notes.as_uri())
        assert workspace._lsp_manager.session is None

        model = workspace.open_file(uri=fake_file.as_uri())
        assert model.get_language_id() == "fake"
        assert workspace.lsp_status.state is LspState.RUNNING
        assert workspace._lsp_manager.session is not None
    finally:
        workspace.close()

    assert exit_marker.read_text(encoding="utf-8") == "exit"


def test_workspace_selection_modes_ties_no_match_and_reload(tmp_path: Path) -> None:
    command = (sys.executable, str(FAKE_SERVER), str(tmp_path / "unused-exit"))
    alpha = _profile("alpha", ".alpha", "alpha.toml", command=command)
    beta = _profile("beta", ".beta", "beta.toml", command=command)

    tie_root = tmp_path / "tie"
    tie_root.mkdir()
    (tie_root / "one.alpha").write_text("", encoding="utf-8")
    (tie_root / "one.beta").write_text("", encoding="utf-8")
    tie = Workspace(str(tie_root), "tie", language_profiles=(alpha, beta))

    no_match_root = tmp_path / "no-match"
    no_match_root.mkdir()
    (no_match_root / "notes.txt").write_text("", encoding="utf-8")
    no_match = Workspace(str(no_match_root), "no-match", language_profiles=(alpha, beta))

    explicit_root = tmp_path / "explicit"
    explicit_root.mkdir()
    explicit = Workspace(
        str(explicit_root),
        "explicit",
        language_profiles=(alpha, beta),
        lsp_settings=LspSettings(mode="explicit", language_id="beta"),
    )

    disabled_root = tmp_path / "disabled"
    disabled_root.mkdir()
    (disabled_root / "main.alpha").write_text("", encoding="utf-8")
    disabled = Workspace(
        str(disabled_root),
        "disabled",
        language_profiles=(alpha, beta),
        lsp_settings=LspSettings(mode="disabled"),
    )

    fixed_root = tmp_path / "fixed"
    fixed_root.mkdir()
    (fixed_root / "one.alpha").write_text("", encoding="utf-8")
    (fixed_root / "two.alpha").write_text("", encoding="utf-8")
    fixed = Workspace(str(fixed_root), "fixed", language_profiles=(alpha, beta))
    try:
        assert tie.lsp_status.state is LspState.UNDETECTED
        assert no_match.lsp_status.state is LspState.UNDETECTED
        assert explicit.lsp_status.language_id == "beta"
        assert explicit.lsp_status.state is LspState.READY
        assert disabled.lsp_status.state is LspState.DISABLED

        assert fixed.lsp_status.language_id == "alpha"
        (fixed_root / "beta.toml").write_text("", encoding="utf-8")
        for index in range(3):
            (fixed_root / f"new-{index}.beta").write_text("", encoding="utf-8")
        assert fixed.lsp_status.language_id == "alpha"
        assert fixed.reload_lsp().language_id == "beta"
        assert fixed._lsp_manager.session is None
    finally:
        for workspace in (tie, no_match, explicit, disabled, fixed):
            workspace.close()


def test_fake_language_crash_restarts_once_and_reload_resets_state(tmp_path: Path) -> None:
    fake_file = tmp_path / "crash.fake"
    fake_file.write_text("fake declaration\n", encoding="utf-8")
    workspace = Workspace(
        root_dir=str(tmp_path),
        project_name="fake-crash-e2e",
        language_profiles=(_fake_profile(tmp_path, marker_name="unused-crash-exit"),),
        lsp_settings=LspSettings(mode="explicit", language_id="fake"),
        diagnostics_timeout=2.0,
    )
    try:
        workspace.open_file(uri=fake_file.as_uri())
        first = workspace._lsp_manager.session
        assert first is not None
        with pytest.raises(LspError):
            first.request(
                {"jsonrpc": "2.0", "id": first.next_request_id(), "method": "test/crash", "params": {}},
                dict,
                timeout=2.0,
            )
        _wait_until(lambda: workspace.lsp_status.state is LspState.UNAVAILABLE)

        second = workspace._ensure_lsp_for_uri(fake_file.as_uri(), semantic=True)
        assert second is not None and second is not first
        with pytest.raises(LspError):
            second.request(
                {"jsonrpc": "2.0", "id": second.next_request_id(), "method": "test/crash", "params": {}},
                dict,
                timeout=2.0,
            )
        _wait_until(lambda: workspace.lsp_status.state is LspState.UNAVAILABLE)
        assert workspace._ensure_lsp_for_uri(fake_file.as_uri(), semantic=True) is None

        status = workspace.reload_lsp()
        assert status.state is LspState.READY
        assert status.language_id == "fake"
        assert workspace._lsp_manager.session is None
    finally:
        workspace.close()


def test_generic_mcp_fake_language_starts_and_closes(tmp_path: Path) -> None:
    fake_file = tmp_path / "main.fake"
    fake_file.write_text("fake through mcp\n", encoding="utf-8")
    exit_marker = tmp_path / "mcp-fake-exit"
    project_name = f"mcp-fake-{tmp_path.name}"
    config = _server_config(
        tmp_path,
        project_name,
        lsp_mode="auto",
        lsp_profile_language_id="fake",
        lsp_server_command=(sys.executable, str(FAKE_SERVER), str(exit_marker)),
        lsp_file_extensions=(".fake",),
        lsp_root_markers=("fake.toml",),
    )
    server = IDEMCPServer(config)
    try:
        assert asyncio.run(server.tools["Lsp"].execute({"action": "status"}))["state"] == "ready"
        result = asyncio.run(server.tools["Read"].execute({"file_path": str(fake_file)}))
        assert result["success"] is True
        assert "fake through mcp" in result["content"]
        assert asyncio.run(server.tools["Lsp"].execute({"action": "status"})) == {
            "state": "running",
            "language_id": "fake",
            "reason": None,
        }
    finally:
        _close_server(server, project_name)

    assert exit_marker.read_text(encoding="utf-8") == "exit"


def test_generic_mcp_missing_lsp_keeps_file_search_and_terminal_working(tmp_path: Path) -> None:
    source = tmp_path / "fallback.missing"
    source.write_text("fallback needle\n", encoding="utf-8")
    project_name = f"mcp-missing-{tmp_path.name}"
    config = _server_config(
        tmp_path,
        project_name,
        lsp_mode="explicit",
        lsp_language_id="missing",
        lsp_profile_language_id="missing",
        lsp_server_command=("missing-language-server-for-ide4ai-e2e",),
        lsp_file_extensions=(".missing",),
    )
    server = IDEMCPServer(config)
    try:

        def assert_lsp_not_started() -> None:
            status = asyncio.run(server.tools["Lsp"].execute({"action": "status"}))
            assert status == {"state": "ready", "language_id": "missing", "reason": None}
            assert server.ide.workspace._lsp_manager.session is None

        glob_result = asyncio.run(server.tools["Glob"].execute({"pattern": "**/*.missing"}))
        assert_lsp_not_started()
        grep_result = asyncio.run(server.tools["Grep"].execute({"pattern": "needle"}))
        assert_lsp_not_started()
        bash_result = asyncio.run(server.tools["Bash"].execute({"command": "pwd"}))
        assert_lsp_not_started()
        assert glob_result["success"] is True and glob_result["files"]
        assert grep_result["success"] is True and grep_result["matched"] is True
        assert bash_result["success"] is True and str(tmp_path) in bash_result["output"]

        read_result = asyncio.run(server.tools["Read"].execute({"file_path": str(source)}))
        assert read_result["success"] is True
        assert "fallback needle" in read_result["content"]
        status = asyncio.run(server.tools["Lsp"].execute({"action": "status"}))
        assert status["state"] == "unavailable"
        assert status["language_id"] == "missing"

        reload_status = asyncio.run(server.tools["Lsp"].execute({"action": "reload"}))
        assert reload_status == {"state": "ready", "language_id": "missing", "reason": None}
        assert server.ide.workspace._lsp_manager.session is None
    finally:
        _close_server(server, project_name)
