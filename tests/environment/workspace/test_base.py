from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from collections.abc import Generator, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from lsprotocol import types
from pydantic import AnyUrl

from ide4ai.dtos.diagnostics import DocumentDiagnosticReport
from ide4ai.dtos.workspace_edit import LSPWorkspaceEdit
from ide4ai.environment.workspace.base import BaseWorkspace
from ide4ai.environment.workspace.model import TextModel
from ide4ai.environment.workspace.schema import Range, SearchResult, SingleEditOperation, TextEdit
from ide4ai.lsp.manager import LanguageProfile, LspServerSpec
from ide4ai.lsp.session import LspSession
from ide4ai.schema import IDEAction


class MockWorkspace(BaseWorkspace):
    def apply_workspace_edit(self, *, workspace_edit: LSPWorkspaceEdit) -> Any:
        return None

    def _initial_lsp(self) -> None:
        return None

    def _lsp_command(self) -> Sequence[str]:
        return ("fake-lsp", "--stdio")

    def _lsp_profiles(self) -> Sequence[LanguageProfile]:
        return (
            LanguageProfile(
                language_id="fake",
                file_extensions=(".fake",),
                root_markers=(),
                server=LspServerSpec(self._lsp_command()),
            ),
        )

    def find_in_path(
        self,
        *,
        uri: str,
        query: str,
        search_scope: Range | list[Range] | None = None,
        is_regex: bool = False,
        match_case: bool = False,
        word_separator: str | None = None,
        capture_matches: bool = True,
        limit_result_count: int | None = None,
    ) -> list[SearchResult]:
        return []

    def apply_edit(
        self,
        *,
        uri: str,
        edits: Sequence[SingleEditOperation | dict],
        compute_undo_edits: bool = False,
    ) -> tuple[list[TextEdit] | None, DocumentDiagnosticReport | None]:
        return None, None

    def rename_file(
        self,
        *,
        old_uri: str,
        new_uri: str,
        overwrite: bool | None = None,
        ignore_if_exists: bool | None = None,
    ) -> bool:
        return False

    def delete_file(
        self,
        *,
        uri: str,
        recursive: bool | None = None,
        ignore_if_not_exists: bool | None = None,
    ) -> bool:
        return False

    def create_file(
        self,
        *,
        uri: str,
        overwrite: bool | None = None,
        ignore_if_exists: bool | None = None,
    ) -> tuple[TextModel | None, DocumentDiagnosticReport | None]:
        return None, None

    def open_file(self, *, uri: str) -> TextModel:
        raise NotImplementedError

    def construct_action(self, action: dict) -> IDEAction:
        return IDEAction.model_validate(action)

    def step(self, action: dict) -> tuple[dict, float, bool, bool, dict[str, Any]]:
        return {}, 0.0, False, False, {}

    def render(self, *, verbose: bool = False) -> str:
        return "Render output"


def new_mock_session() -> MagicMock:
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.server_capabilities = types.ServerCapabilities(
        text_document_sync=types.TextDocumentSyncOptions(open_close=True, change=types.TextDocumentSyncKind.Incremental)
    )
    session.request.return_value = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    return session


def test_base_workspace_syncs_registered_non_python_profile_without_python_override(tmp_path: Path) -> None:
    (tmp_path / "document.fake").write_text("content", encoding="utf-8")
    session = new_mock_session()
    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = MockWorkspace(root_dir=str(tmp_path), project_name="generic-sync")
        try:
            model = TextModel(language_id="python", uri=AnyUrl((tmp_path / "document.fake").as_uri()))
            workspace.models.append(model)
            workspace._track_document_version(str(model.uri), model)
            started = workspace._ensure_lsp_for_uri(str(model.uri))
            assert started is session
            workspace._sync_open_document(session, model)
            notification = session.notify.call_args.args[0]
            assert isinstance(notification, types.DidOpenTextDocumentNotification)
            assert notification.params.text_document.language_id == "fake"
        finally:
            workspace.close()


@pytest.fixture
def workspace() -> Generator[MockWorkspace, Any, None]:
    def session_factory(*args: Any, **kwargs: Any) -> MagicMock:
        return new_mock_session()

    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        patch("ide4ai.lsp.manager.LspSession", side_effect=session_factory),
    ):
        Path(tmp_dir, "workspace.fake").write_text("", encoding="utf-8")
        ws = MockWorkspace(root_dir=tmp_dir, project_name="fake-project")
        yield ws
        ws.close()


def test_workspace_initialization(workspace: MockWorkspace) -> None:
    assert workspace._render_with_symbols is True
    assert workspace._lsp_session is None
    workspace.launch_lsp()
    session = workspace._require_lsp_session()
    session.start.assert_called_once()  # type: ignore[attr-defined]


def test_legacy_launch_lsp_subclass_remains_instantiable() -> None:
    legacy_process = MagicMock(spec=subprocess.Popen)
    legacy_process.args = ("legacy-lsp", "--stdio")

    class LegacyHookWorkspace(MockWorkspace):
        _lsp_command = BaseWorkspace._lsp_command
        _lsp_profiles = BaseWorkspace._lsp_profiles

        def _launch_lsp(self) -> subprocess.Popen[bytes]:
            return legacy_process

    with (
        tempfile.TemporaryDirectory() as tmp_dir,
    ):
        legacy_workspace = LegacyHookWorkspace(root_dir=tmp_dir, project_name="legacy-project")
        try:
            assert legacy_workspace._lsp_command() == ("legacy-lsp", "--stdio")
            legacy_process.terminate.assert_called_once()
            legacy_process.wait.assert_called_once_with(timeout=10.0)
        finally:
            legacy_workspace.close()


def test_kill_lsp_closes_session(workspace: MockWorkspace) -> None:
    workspace.launch_lsp()
    session = workspace._lsp_session
    workspace.kill_lsp()
    assert workspace._lsp_session is None
    assert session is not None
    session.close.assert_called_once()  # type: ignore[attr-defined]


def test_close_is_idempotent(workspace: MockWorkspace) -> None:
    workspace.launch_lsp()
    session = workspace._lsp_session
    workspace.close()
    workspace.close()
    assert workspace._lsp_session is None
    assert session is not None
    session.close.assert_called_once()  # type: ignore[attr-defined]


def test_send_lsp_msg_without_server_running(workspace: MockWorkspace) -> None:
    workspace.kill_lsp()
    with pytest.raises(ValueError, match="LSP server is not running"):
        workspace.send_lsp_msg("initialize", {})


def test_send_lsp_request_delegates_to_session(workspace: MockWorkspace) -> None:
    session = workspace._require_lsp_session()
    response = workspace.send_lsp_msg("test/request", {"key": "value"}, message_id=1)
    assert response is not None
    assert json.loads(response)["result"] == {"ok": True}
    session.request.assert_called_once()  # type: ignore[attr-defined]


def test_read_response_preserves_event_driven_compatibility(workspace: MockWorkspace) -> None:
    response = workspace.send_lsp_msg("test/request", {"key": "value"}, message_id=7)
    assert workspace.read_response(7) == response
    assert workspace.read_response(7, timeout=0.01) is None


def test_reused_request_id_failure_cannot_expose_previous_response(workspace: MockWorkspace) -> None:
    session = workspace._require_lsp_session()
    workspace.send_lsp_msg("test/request", {}, message_id=7)
    session.request.side_effect = RuntimeError("replacement failed")  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="replacement failed"):
        workspace.send_lsp_msg("test/request", {}, message_id=7)

    assert workspace.read_response(7, timeout=0.01) is None
    assert 7 not in workspace._lsp_response_cache


def test_read_response_waiter_is_released_when_lsp_is_killed(workspace: MockWorkspace) -> None:
    with ThreadPoolExecutor(max_workers=1) as executor:
        waiter = executor.submit(workspace.read_response, 404, None)
        with workspace._lsp_response_condition:
            assert workspace._lsp_response_condition.wait_for(
                lambda: workspace._lsp_response_waiter_count == 1,
                timeout=0.5,
            )
        workspace.kill_lsp()
        assert waiter.result(timeout=0.5) is None


@pytest.mark.parametrize("request_fails", [False, True])
def test_stale_request_cannot_write_across_lsp_generation(
    workspace: MockWorkspace,
    request_fails: bool,
) -> None:
    old_session = workspace._require_lsp_session()
    request_entered = threading.Event()
    release_request = threading.Event()

    def complete_old_request(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        request_entered.set()
        assert release_request.wait(timeout=1.0)
        if request_fails:
            raise RuntimeError("old session failed")
        return {"jsonrpc": "2.0", "id": 1, "result": "old"}

    old_session.request.side_effect = complete_old_request  # type: ignore[attr-defined]
    with ThreadPoolExecutor(max_workers=1) as executor:
        request = executor.submit(workspace.send_lsp_msg, "test/request", {}, 1)
        assert request_entered.wait(timeout=0.5)
        workspace.kill_lsp()
        release_request.set()
        if request_fails:
            with pytest.raises(RuntimeError, match="old session failed"):
                request.result(timeout=0.5)
        else:
            assert request.result(timeout=0.5) is not None

    assert workspace._lsp_response_cache == {}
    assert workspace._lsp_response_failures == set()
    workspace.launch_lsp()
    current_response = workspace.send_lsp_msg("test/request", {}, 1)
    assert workspace.read_response(1) == current_response


def test_closed_workspace_rejects_lsp_relaunch(workspace: MockWorkspace) -> None:
    workspace.close()
    with pytest.raises(ValueError, match="closed Workspace"):
        workspace.launch_lsp()
    assert workspace._lsp_session is None


def test_send_lsp_notification_delegates_to_session(workspace: MockWorkspace) -> None:
    session = workspace._require_lsp_session()
    assert workspace.send_lsp_msg("test/notification", {"key": "value"}) is None
    session.notify.assert_called_once()  # type: ignore[attr-defined]


def test_read_notification_returns_none_on_timeout(workspace: MockWorkspace) -> None:
    session = workspace._require_lsp_session()
    session.wait_for_notification.side_effect = TimeoutError  # type: ignore[attr-defined]
    assert workspace.read_notification("test/notification", "file:///tmp/test", timeout=0.01) is None


def test_read_notification_serializes_message(workspace: MockWorkspace) -> None:
    session = workspace._require_lsp_session()
    session.wait_for_notification.return_value = {  # type: ignore[attr-defined]
        "jsonrpc": "2.0",
        "method": "test/notification",
    }
    result = workspace.read_notification("test/notification", "file:///tmp/test")
    assert result is not None
    assert json.loads(result)["method"] == "test/notification"
    session.wait_for_notification.assert_called_once_with(  # type: ignore[attr-defined]
        "test/notification",
        uri="file:///tmp/test",
        timeout=0.05,
    )


def test_restart_lsp_closes_old_session_and_starts_new_one(workspace: MockWorkspace) -> None:
    workspace.launch_lsp()
    old_session = workspace._lsp_session
    workspace.launch_lsp()
    assert old_session is not None
    old_session.close.assert_called_once()  # type: ignore[attr-defined]
    assert workspace._lsp_session is not old_session
    workspace._require_lsp_session().start.assert_called_once()  # type: ignore[attr-defined]


def test_concurrent_lsp_launches_are_serialized(workspace: MockWorkspace) -> None:
    workspace.launch_lsp()
    initial_session = workspace._require_lsp_session()
    first_start_entered = threading.Event()
    release_first_start = threading.Event()
    second_factory_entered = threading.Event()
    created: list[MagicMock] = []

    def session_factory(*args: Any, **kwargs: Any) -> MagicMock:
        del args, kwargs
        session = new_mock_session()
        if not created:
            session.start.side_effect = lambda: (first_start_entered.set(), release_first_start.wait(timeout=1.0))
        else:
            second_factory_entered.set()
        created.append(session)
        return session

    with (
        patch("ide4ai.lsp.manager.LspSession", side_effect=session_factory),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first = executor.submit(workspace.launch_lsp)
        assert first_start_entered.wait(timeout=0.5)
        second = executor.submit(workspace.launch_lsp)
        assert second_factory_entered.wait(timeout=0.05) is False
        release_first_start.set()
        first.result(timeout=1.0)
        second.result(timeout=1.0)

    initial_session.close.assert_called_once()  # type: ignore[attr-defined]
    assert len(created) == 2
    created[0].close.assert_called_once()
    assert workspace._lsp_session is created[1]
