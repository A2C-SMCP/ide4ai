from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lsprotocol import types

from ide4ai.environment.workspace.schema import Position, Range, SingleEditOperation
from ide4ai.environment.workspace.workspace import Workspace
from ide4ai.lsp.manager import LspSettings, LspState
from ide4ai.lsp.position_codec import PositionCodec
from ide4ai.lsp.session import LspSession


def server_capabilities() -> types.ServerCapabilities:
    return types.ServerCapabilities(
        text_document_sync=types.TextDocumentSyncOptions(
            open_close=True,
            change=types.TextDocumentSyncKind.Incremental,
            will_save=True,
            save=types.SaveOptions(include_text=True),
        )
    )


@pytest.mark.parametrize(
    ("encoding", "expected_start", "expected_end"),
    [("utf-16", 12, 13), ("utf-8", 14, 17)],
)
def test_apply_edit_uses_negotiated_position_encoding(
    tmp_path: Path,
    encoding: str,
    expected_start: int,
    expected_end: int,
) -> None:
    source_path = tmp_path / "unicode.py"
    source_path.write_text('value = "a😀中z"\n', encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec(encoding)  # type: ignore[arg-type]
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)

    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(root_dir=str(tmp_path), project_name="unicode-workspace")
        workspace.launch_lsp()
    try:
        uri = source_path.resolve().as_uri()
        workspace.open_file(uri=uri)
        session.notify.reset_mock()
        workspace.pull_diagnostics = MagicMock(return_value=None)  # type: ignore[method-assign]

        workspace.apply_edit(
            uri=uri,
            edits=[
                SingleEditOperation(
                    range=Range(
                        start_position=Position(1, 12),
                        end_position=Position(1, 13),
                    ),
                    text="文",
                )
            ],
        )

        notification = session.notify.call_args.args[0]
        assert isinstance(notification, types.DidChangeTextDocumentNotification)
        change = notification.params.content_changes[0]
        assert isinstance(change, types.TextDocumentContentChangePartial)
        assert change.range.start.character == expected_start
        assert change.range.end.character == expected_end
    finally:
        workspace.close()


def test_pyworkspace_advertises_supported_position_encodings(tmp_path: Path) -> None:
    (tmp_path / "capability.py").write_text("", encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec()
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)

    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(root_dir=str(tmp_path), project_name="capability-workspace")
        workspace.launch_lsp()
    try:
        params = session.initialize.call_args.args[0]
        assert params.capabilities.general is not None
        assert params.capabilities.general.position_encodings == ("utf-8", "utf-16")
        assert params.capabilities.workspace is None
        assert params.capabilities.text_document is not None
        assert params.capabilities.text_document.code_action is None
    finally:
        workspace.close()


def test_apply_edit_orders_multiple_changes_like_text_model(tmp_path: Path) -> None:
    source_path = tmp_path / "multiple.py"
    source_path.write_text("aa = 1; bb = 2\n", encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec("utf-16")
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)

    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(root_dir=str(tmp_path), project_name="multiple-edit-workspace")
        workspace.launch_lsp()
    try:
        uri = source_path.resolve().as_uri()
        text_model = workspace.open_file(uri=uri)
        session.notify.reset_mock()
        workspace.pull_diagnostics = MagicMock(return_value=None)  # type: ignore[method-assign]

        workspace.apply_edit(
            uri=uri,
            edits=[
                SingleEditOperation(
                    range=Range(start_position=Position(1, 1), end_position=Position(1, 1)),
                    text="long_",
                ),
                SingleEditOperation(
                    range=Range(start_position=Position(1, 9), end_position=Position(1, 11)),
                    text="cc",
                ),
            ],
        )

        notification = session.notify.call_args.args[0]
        changes = notification.params.content_changes
        assert [change.range.start.character for change in changes] == [8, 0]
        assert text_model.get_value() == "long_aa = 1; cc = 2"
    finally:
        workspace.close()


def test_pyworkspace_starts_lsp_only_when_opening_the_primary_language(tmp_path: Path) -> None:
    python_path = tmp_path / "main.py"
    python_path.write_text("value = 1\n", encoding="utf-8")
    text_path = tmp_path / "notes.txt"
    text_path.write_text("notes\n", encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec()
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)

    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(root_dir=str(tmp_path), project_name="lazy-workspace")
        try:
            assert workspace._lsp_session is None
            assert workspace.lsp_status.state is LspState.READY
            workspace.open_file(uri=text_path.as_uri())
            session.start.assert_not_called()
            workspace.open_file(uri=python_path.as_uri())
            session.start.assert_called_once()
        finally:
            workspace.close()


def test_non_language_document_lifecycle_and_disabled_workspace_degrade_without_lsp(tmp_path: Path) -> None:
    text_path = tmp_path / "notes.txt"
    text_path.write_text("notes\n", encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec()
    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(
            root_dir=str(tmp_path),
            project_name="disabled-workspace",
            lsp_settings=LspSettings(mode="disabled"),
        )
        try:
            workspace.open_file(uri=text_path.as_uri())
            workspace.close_file(uri=text_path.as_uri())
            created, diagnostics = workspace.create_file(uri=(tmp_path / "created.txt").as_uri())
            assert created is not None
            assert diagnostics is None
            session.start.assert_not_called()
        finally:
            workspace.close()


def test_restart_lsp_action_reloads_language_without_eager_start(tmp_path: Path) -> None:
    source_path = tmp_path / "main.py"
    source_path.write_text("value = 1\n", encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec()
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)
    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(root_dir=str(tmp_path), project_name="reload-workspace")
        try:
            workspace.open_file(uri=source_path.as_uri())
            result, reward, _, success, _ = workspace.step(
                {"category": "workspace", "action_name": "restart_lsp", "action_args": {}}
            )
            assert success and reward == 100
            assert result["lsp_status"]["state"] == LspState.READY.value
            assert workspace._lsp_session is None
        finally:
            workspace.close()


def test_edit_after_lsp_reload_reopens_existing_document_before_did_change(tmp_path: Path) -> None:
    source_path = tmp_path / "replay.py"
    source_path.write_text("value = 1\n", encoding="utf-8")
    first, second = (MagicMock(spec=LspSession), MagicMock(spec=LspSession))
    for session in (first, second):
        session.is_running = True
        session.position_codec = PositionCodec()
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)

    with patch("ide4ai.lsp.manager.LspSession", side_effect=(first, second)):
        workspace = Workspace(root_dir=str(tmp_path), project_name="replay-workspace")
        try:
            uri = source_path.as_uri()
            workspace.open_file(uri=uri)
            workspace.reload_lsp()
            workspace.pull_diagnostics = MagicMock(return_value=None)  # type: ignore[method-assign]
            workspace.apply_edit(
                uri=uri,
                edits=[
                    SingleEditOperation(
                        range=Range(start_position=Position(1, 1), end_position=Position(1, 1)), text="new_"
                    )
                ],
            )
            notifications = [call.args[0] for call in second.notify.call_args_list]
            assert isinstance(notifications[0], types.DidOpenTextDocumentNotification)
            assert isinstance(notifications[1], types.DidChangeTextDocumentNotification)
        finally:
            workspace.close()


def test_edit_after_unexpected_exit_restarts_once_and_reopens_document(tmp_path: Path) -> None:
    source_path = tmp_path / "restart.py"
    source_path.write_text("value = 1\n", encoding="utf-8")
    first, second = (MagicMock(spec=LspSession), MagicMock(spec=LspSession))
    for session in (first, second):
        session.is_running = True
        session.position_codec = PositionCodec()
        session.server_capabilities = server_capabilities()
        session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)

    with patch("ide4ai.lsp.manager.LspSession", side_effect=(first, second)):
        workspace = Workspace(root_dir=str(tmp_path), project_name="restart-workspace")
        try:
            uri = source_path.as_uri()
            workspace.open_file(uri=uri)
            for callback_call in first.add_close_callback.call_args_list:
                callback_call.args[0](RuntimeError("server crashed"))
            workspace.pull_diagnostics = MagicMock(return_value=None)  # type: ignore[method-assign]
            workspace.apply_edit(
                uri=uri,
                edits=[
                    SingleEditOperation(
                        range=Range(start_position=Position(1, 1), end_position=Position(1, 1)), text="new_"
                    )
                ],
            )
            notifications = [call.args[0] for call in second.notify.call_args_list]
            assert isinstance(notifications[0], types.DidOpenTextDocumentNotification)
            assert isinstance(notifications[1], types.DidChangeTextDocumentNotification)
        finally:
            workspace.close()


def test_reset_closes_open_documents_and_forgets_diagnostics(tmp_path: Path) -> None:
    source_path = tmp_path / "reset.py"
    source_path.write_text("value = 1\n", encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec()
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)
    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(root_dir=str(tmp_path), project_name="reset-workspace")
        try:
            uri = source_path.as_uri()
            workspace.open_file(uri=uri)
            workspace._diagnostics.record_push({"uri": uri, "version": 1, "diagnostics": []})
            session.notify.reset_mock()
            workspace.reset()
            notifications = [call.args[0] for call in session.notify.call_args_list]
            assert len(notifications) == 1
            assert isinstance(notifications[0], types.DidCloseTextDocumentNotification)
            assert workspace.models == []
            assert workspace._diagnostics.get_push(uri) is None
        finally:
            workspace.close()


def test_pull_diagnostics_discards_response_when_model_version_changes(tmp_path: Path) -> None:
    source_path = tmp_path / "stale.py"
    source_path.write_text("value = 1\n", encoding="utf-8")
    session = MagicMock(spec=LspSession)
    session.is_running = True
    session.position_codec = PositionCodec()
    session.server_capabilities = server_capabilities()
    session.initialize.return_value = types.InitializeResult(capabilities=session.server_capabilities)
    request_started = threading.Event()
    release_response = threading.Event()

    with patch("ide4ai.lsp.manager.LspSession", return_value=session):
        workspace = Workspace(root_dir=str(tmp_path), project_name="stale-workspace")
        try:
            uri = source_path.as_uri()
            model = workspace.open_file(uri=uri)

            def delayed_request(*args: object, **kwargs: object) -> types.DocumentDiagnosticResponse:
                request_started.set()
                assert release_response.wait(timeout=1)
                return types.DocumentDiagnosticResponse(
                    id=1, result=types.RelatedFullDocumentDiagnosticReport(items=[], result_id="stale")
                )

            session.request.side_effect = delayed_request
            result: list[object] = []
            worker = threading.Thread(target=lambda: result.append(workspace.pull_diagnostics(uri=uri)))
            worker.start()
            assert request_started.wait(timeout=1)
            model.apply_edits(
                [
                    SingleEditOperation(
                        range=Range(start_position=Position(1, 1), end_position=Position(1, 1)), text="new_"
                    )
                ]
            )
            workspace._track_document_version(uri, model)
            release_response.set()
            worker.join(timeout=1)
            assert not worker.is_alive()
            assert result == [None]
            assert workspace._diagnostics.get(uri) is None
        finally:
            workspace.close()
