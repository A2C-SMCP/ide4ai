from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from lsprotocol import types

from ide4ai.lsp.manager import (
    LanguageProfile,
    LspManager,
    LspServerSpec,
    LspSettings,
    LspState,
)
from ide4ai.lsp.session import LspSession


def profile(language_id: str, extension: str, marker: str) -> LanguageProfile:
    return LanguageProfile(
        language_id=language_id,
        file_extensions=(extension,),
        root_markers=(marker,),
        server=LspServerSpec((sys.executable, "fake-language-server")),
    )


def test_auto_detection_prioritizes_root_markers_then_source_count(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "extra.fake").write_text("", encoding="utf-8")
    manager = LspManager(tmp_path, [profile("python", ".py", "pyproject.toml"), profile("fake", ".fake", "fake.toml")])

    assert manager.primary_language_id == "python"
    assert manager.status.state is LspState.READY


def test_auto_detection_tie_or_no_candidate_does_not_select_a_language(tmp_path: Path) -> None:
    (tmp_path / "one.py").write_text("", encoding="utf-8")
    (tmp_path / "one.fake").write_text("", encoding="utf-8")
    manager = LspManager(tmp_path, [profile("python", ".py", "pyproject.toml"), profile("fake", ".fake", "fake.toml")])

    assert manager.primary_language_id is None
    assert manager.status.state is LspState.UNDETECTED


def test_auto_detection_shared_extension_tie_does_not_select_first_registered_profile(tmp_path: Path) -> None:
    (tmp_path / "common.h").write_text("", encoding="utf-8")
    manager = LspManager(tmp_path, [profile("c", ".h", "CMakeLists.txt"), profile("cpp", ".h", "meson.build")])

    assert manager.primary_language_id is None
    assert manager.status.state is LspState.UNDETECTED


def test_shared_extension_uses_selected_profile_when_marker_breaks_the_tie(tmp_path: Path) -> None:
    (tmp_path / "compile_commands.json").write_text("", encoding="utf-8")
    header = tmp_path / "shared.h"
    header.write_text("", encoding="utf-8")
    session = MagicMock()
    session.is_running = True
    profiles = [profile("c", ".h", "CMakeLists.txt"), profile("cpp", ".h", "compile_commands.json")]

    with patch("ide4ai.lsp.manager.LspSession", return_value=session) as session_type:
        manager = LspManager(tmp_path, profiles)
        assert manager.primary_language_id == "cpp"
        assert manager.language_for_path(header) == "cpp"
        assert manager.ensure_started(language_id=manager.language_for_path(header)) is session
        session_type.assert_called_once()


def test_detection_ignores_dependencies_and_outside_symlinks(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "many.fake").write_text("", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.fake"
    outside.write_text("", encoding="utf-8")
    try:
        (tmp_path / "outside.fake").symlink_to(outside)
        manager = LspManager(
            tmp_path,
            [profile("python", ".py", "pyproject.toml"), profile("fake", ".fake", "fake.toml")],
        )
        assert manager.primary_language_id == "python"
    finally:
        outside.unlink(missing_ok=True)


def test_detection_ignores_outside_root_marker_symlinks_and_deps(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-marker"
    outside.mkdir()
    marker = outside / "pyproject.toml"
    marker.write_text("", encoding="utf-8")
    deps = tmp_path / "deps"
    deps.mkdir()
    for index in range(3):
        (deps / f"dependency-{index}.fake").write_text("", encoding="utf-8")
    try:
        (tmp_path / "pyproject.toml").symlink_to(marker)
        manager = LspManager(
            tmp_path,
            [profile("python", ".py", "pyproject.toml"), profile("fake", ".fake", "fake.toml")],
        )
        assert manager.primary_language_id is None
    finally:
        marker.unlink(missing_ok=True)
        outside.rmdir()


def test_explicit_and_disabled_modes_have_structured_status(tmp_path: Path) -> None:
    profiles = [profile("python", ".py", "pyproject.toml")]
    explicit = LspManager(tmp_path, profiles, settings=LspSettings(mode="explicit", language_id="python"))
    disabled = LspManager(tmp_path, profiles, settings=LspSettings(mode="disabled"))

    assert explicit.primary_language_id == "python"
    assert disabled.status.state is LspState.DISABLED
    assert disabled.ensure_started(semantic=True) is None

    missing = LspManager(tmp_path, profiles, settings=LspSettings(mode="explicit", language_id="unknown"))
    assert missing.status.state is LspState.UNAVAILABLE


def test_manager_lazily_starts_only_for_primary_language_or_semantic_request(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    profiles = [profile("python", ".py", "pyproject.toml"), profile("fake", ".fake", "fake.toml")]
    session = MagicMock()
    session.is_running = True
    with patch("ide4ai.lsp.manager.LspSession", return_value=session) as session_type:
        manager = LspManager(tmp_path, profiles)
        assert manager.ensure_started(language_id="fake") is None
        session_type.assert_not_called()
        assert manager.ensure_started(language_id="python") is session
        session.start.assert_called_once()
        assert manager.status.state is LspState.RUNNING
        assert manager.ensure_started(semantic=True) is session
        session_type.assert_called_once()


def test_unavailable_server_degrades_without_a_session(tmp_path: Path) -> None:
    language = LanguageProfile(
        language_id="missing",
        file_extensions=(".missing",),
        root_markers=(),
        server=LspServerSpec(("missing-language-server-for-ide4ai-tests",)),
    )
    (tmp_path / "main.missing").write_text("", encoding="utf-8")
    manager = LspManager(tmp_path, [language])

    assert manager.ensure_started(language_id="missing") is None
    assert manager.status.state is LspState.UNAVAILABLE
    assert "missing-language-server" in (manager.status.reason or "")


def test_reload_reselects_but_does_not_eagerly_start(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    manager = LspManager(tmp_path, [profile("python", ".py", "pyproject.toml")])

    assert manager.reload().state is LspState.READY
    assert manager.session is None


def test_reload_does_not_start_a_second_session_before_old_session_closes(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    old_session, new_session = MagicMock(), MagicMock()
    old_session.is_running = True
    new_session.is_running = True
    closing = threading.Event()
    permit_close = threading.Event()

    def close_old_session() -> None:
        closing.set()
        assert permit_close.wait(timeout=2)

    old_session.close.side_effect = close_old_session
    with patch("ide4ai.lsp.manager.LspSession", side_effect=(old_session, new_session)):
        manager = LspManager(tmp_path, [profile("python", ".py", "pyproject.toml")])
        assert manager.ensure_started(language_id="python") is old_session
        reloader = threading.Thread(target=manager.reload)
        reloader.start()
        assert closing.wait(timeout=1)
        starter = threading.Thread(target=lambda: manager.ensure_started(language_id="python"))
        starter.start()
        starter.join(timeout=0.05)
        assert starter.is_alive()
        new_session.start.assert_not_called()
        permit_close.set()
        reloader.join(timeout=1)
        starter.join(timeout=1)
        assert not reloader.is_alive()
        assert not starter.is_alive()
        new_session.start.assert_called_once()


def test_unexpected_exit_restarts_at_most_once_until_reload(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    first, second = MagicMock(), MagicMock()
    for session in (first, second):
        session.is_running = True
    with patch("ide4ai.lsp.manager.LspSession", side_effect=(first, second)) as session_type:
        manager = LspManager(tmp_path, [profile("python", ".py", "pyproject.toml")])
        assert manager.ensure_started(language_id="python") is first
        first.add_close_callback.call_args.args[0](RuntimeError("first crash"))
        assert manager.ensure_started(language_id="python") is second
        second.add_close_callback.call_args.args[0](RuntimeError("second crash"))
        assert manager.ensure_started(language_id="python") is None
        assert manager.status.state is LspState.UNAVAILABLE
        assert session_type.call_count == 2


def test_document_notifications_follow_negotiated_sync_options(tmp_path: Path) -> None:
    manager = LspManager(tmp_path, [], settings=LspSettings(mode="disabled"))
    session = MagicMock(spec=LspSession)
    session.server_capabilities = types.ServerCapabilities(
        text_document_sync=types.TextDocumentSyncOptions(
            open_close=False,
            change=types.TextDocumentSyncKind.Full,
            will_save=False,
            save=types.SaveOptions(include_text=False),
        )
    )

    manager.did_open(session, uri="file:///main.py", language_id="python", version=1, text="old")
    manager.will_save(session, uri="file:///main.py")
    manager.did_change(
        session,
        uri="file:///main.py",
        version=2,
        changes=(types.TextDocumentContentChangeWholeDocument(text="x"),),
        full_text="new",
    )
    manager.did_save(session, uri="file:///main.py", text="new")
    manager.did_close(session, uri="file:///main.py")

    notifications = [call.args[0] for call in session.notify.call_args_list]
    assert len(notifications) == 2
    change = notifications[0]
    assert isinstance(change, types.DidChangeTextDocumentNotification)
    assert change.params.content_changes == [types.TextDocumentContentChangeWholeDocument(text="new")]
    save = notifications[1]
    assert isinstance(save, types.DidSaveTextDocumentNotification)
    assert save.params.text is None


def test_absent_or_disabled_sync_capability_sends_no_document_notifications(tmp_path: Path) -> None:
    manager = LspManager(tmp_path, [], settings=LspSettings(mode="disabled"))
    for sync in (None, types.TextDocumentSyncKind.None_):
        session = MagicMock(spec=LspSession)
        session.server_capabilities = types.ServerCapabilities(text_document_sync=sync)
        manager.did_open(session, uri="file:///main.py", language_id="python", version=1, text="secret")
        manager.did_change(
            session,
            uri="file:///main.py",
            version=2,
            changes=(types.TextDocumentContentChangeWholeDocument(text="secret"),),
            full_text="secret",
        )
        manager.will_save(session, uri="file:///main.py")
        manager.did_save(session, uri="file:///main.py", text="secret")
        manager.did_close(session, uri="file:///main.py")
        session.notify.assert_not_called()


def test_save_includes_text_only_when_server_explicitly_requests_it(tmp_path: Path) -> None:
    manager = LspManager(tmp_path, [], settings=LspSettings(mode="disabled"))
    for save_option in (True, types.SaveOptions(), types.SaveOptions(include_text=False)):
        session = MagicMock(spec=LspSession)
        session.server_capabilities = types.ServerCapabilities(
            text_document_sync=types.TextDocumentSyncOptions(save=save_option)
        )
        manager.did_save(session, uri="file:///main.py", text="secret")
        notification = session.notify.call_args.args[0]
        assert isinstance(notification, types.DidSaveTextDocumentNotification)
        assert notification.params.text is None
