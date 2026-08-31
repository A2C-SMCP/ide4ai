from __future__ import annotations

from pathlib import Path

from lsprotocol import types

from ide4ai.environment.workspace.schema import Position, Range, SingleEditOperation
from ide4ai.environment.workspace.workspace import Workspace
from ide4ai.lsp.session import LspSession


def test_real_pyright_typed_session_lifecycle(tmp_path: Path) -> None:
    source_path = tmp_path / "example.py"
    source_text = "class Example:\n    value = 1\n"
    source_path.write_text(source_text, encoding="utf-8")

    session = LspSession(
        ["pyright-langserver", "--stdio"],
        cwd=tmp_path,
        request_timeout=10.0,
    )
    session.start()
    try:
        initialize_result = session.initialize(
            types.InitializeParams(
                process_id=None,
                capabilities=types.ClientCapabilities(),
                workspace_folders=[types.WorkspaceFolder(uri=tmp_path.as_uri(), name="pyright-session-test")],
            )
        )
        assert initialize_result.capabilities.document_symbol_provider is not None

        session.notify(
            types.DidOpenTextDocumentNotification(
                params=types.DidOpenTextDocumentParams(
                    text_document=types.TextDocumentItem(
                        uri=source_path.as_uri(),
                        language_id="python",
                        version=1,
                        text=source_text,
                    )
                )
            )
        )
        response = session.request(
            types.DocumentSymbolRequest(
                id=session.next_request_id(),
                params=types.DocumentSymbolParams(text_document=types.TextDocumentIdentifier(uri=source_path.as_uri())),
            ),
            types.DocumentSymbolResponse,
        )
        assert response.result is not None
        assert any(symbol.name == "Example" for symbol in response.result)
    finally:
        session.close()

    assert session.returncode == 0


def test_real_pyright_stays_in_sync_after_multiple_edits(tmp_path: Path) -> None:
    source_path = tmp_path / "multiple.py"
    source_path.write_text("aa = 1; bb = 2\n", encoding="utf-8")
    workspace = Workspace(root_dir=str(tmp_path), project_name="pyright-multiple-edit-test")
    try:
        uri = source_path.resolve().as_uri()
        text_model = workspace.open_file(uri=uri)
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

        session = workspace._require_lsp_session()
        response = session.request(
            types.DocumentSymbolRequest(
                id=session.next_request_id(),
                params=types.DocumentSymbolParams(text_document=types.TextDocumentIdentifier(uri=uri)),
            ),
            types.DocumentSymbolResponse,
        )
        assert text_model.get_value() == "long_aa = 1; cc = 2"
        assert response.result is not None
        symbol_names = {symbol.name for symbol in response.result}
        assert {"long_aa", "cc"} <= symbol_names
        assert "bb" not in symbol_names
    finally:
        workspace.close()
