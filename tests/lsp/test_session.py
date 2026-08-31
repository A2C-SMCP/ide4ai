from __future__ import annotations

import asyncio
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from lsprotocol import types

from ide4ai.lsp.errors import JsonRpcTimeoutError, LspProcessExitedError, LspSessionClosedError
from ide4ai.lsp.session import LspSession

FAKE_SERVER = Path(__file__).with_name("fake_lsp_server.py")


def make_session(
    tmp_path: Path,
    *,
    request_timeout: float = 1.0,
    shutdown_timeout: float = 0.5,
    position_encoding: str = "utf-16",
) -> tuple[LspSession, Path]:
    exit_marker = tmp_path / "exit-marker"
    session = LspSession(
        [sys.executable, str(FAKE_SERVER), str(exit_marker), position_encoding],
        request_timeout=request_timeout,
        shutdown_timeout=shutdown_timeout,
    )
    session.start()
    return session, exit_marker


def test_typed_initialize_and_graceful_shutdown(tmp_path: Path) -> None:
    session, exit_marker = make_session(tmp_path)
    result = session.initialize(types.InitializeParams(capabilities=types.ClientCapabilities()))
    assert result.capabilities.position_encoding == "utf-16"
    assert session.position_codec.encoding == "utf-16"

    response = session.request(
        {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/echo", "params": {"ok": True}},
        dict[str, Any],
    )
    assert response["result"] == {"ok": True}

    session.close()
    assert session.returncode == 0
    assert exit_marker.read_text(encoding="utf-8") == "exit"


def test_sync_server_handler_can_make_nested_session_request(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    try:
        session.register_server_request_handler(
            "workspace/configuration",
            lambda params: session.request(
                {
                    "jsonrpc": "2.0",
                    "id": session.next_request_id(),
                    "method": "test/echo",
                    "params": {"nested": True},
                },
                dict[str, Any],
            )["result"],
        )
        session.initialize(types.InitializeParams(capabilities=types.ClientCapabilities()))

        notification = session.wait_for_notification("test/nested-complete", timeout=0.5)
        assert notification["params"] == {"nested": True}
    finally:
        session.close()


def test_initialize_records_negotiated_utf8_position_encoding(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path, position_encoding="utf-8")
    try:
        session.initialize(types.InitializeParams(capabilities=types.ClientCapabilities()))
        assert session.position_codec.encoding == "utf-8"
    finally:
        session.close()


def test_request_timeout_cleans_pending_future(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path, request_timeout=0.05)
    try:
        with pytest.raises(JsonRpcTimeoutError):
            session.request(
                {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/never"},
                dict[str, Any],
            )
        assert session.pending_request_count == 0
    finally:
        session.close()


def test_process_exit_fails_pending_request(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    loop_thread = session._thread
    try:
        with pytest.raises(LspProcessExitedError) as exc_info:
            session.request(
                {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/crash"},
                dict[str, Any],
            )
        assert exc_info.value.returncode == 7
        assert session.returncode == 7
        assert session.pending_request_count == 0
    finally:
        session.close()
    assert loop_thread is not None
    loop_thread.join(timeout=0.5)
    assert loop_thread.is_alive() is False
    assert session._thread is None


def test_stdout_eof_closes_transport_before_process_exit(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path, request_timeout=0.5)
    loop_thread = session._thread
    session_closed = threading.Event()
    session.add_close_callback(lambda error: session_closed.set())
    started_at = time.monotonic()
    try:
        with pytest.raises(LspSessionClosedError, match="stdout"):
            session.request(
                {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/close-stdout"},
                dict[str, Any],
            )
        assert time.monotonic() - started_at < 0.25
        assert session._transport is not None
        assert session._transport.is_closed
        assert session_closed.wait(timeout=0.25)
        assert loop_thread is not None
        session.close()
        assert loop_thread.is_alive() is False
        assert session.is_running is False
        assert session.returncode is not None
        assert isinstance(session._session_close_error, LspSessionClosedError)
    finally:
        session.close()


def test_process_exit_wakes_notification_waiter(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiter = executor.submit(session.wait_for_notification, "test/never", timeout=5.0)
            with pytest.raises(LspProcessExitedError):
                session.request(
                    {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/crash"},
                    dict[str, Any],
                )
            with pytest.raises(LspProcessExitedError):
                waiter.result(timeout=0.5)
    finally:
        session.close()


def test_notifications_are_isolated_by_uri(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    try:
        session.request(
            {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/notifications"},
            dict[str, Any],
        )
        first = session.wait_for_notification(
            "textDocument/publishDiagnostics",
            uri="file:///a.py",
        )
        second = session.wait_for_notification(
            "textDocument/publishDiagnostics",
            uri="file:///b.py",
        )
        assert first["params"]["uri"] == "file:///a.py"
        assert second["params"]["uri"] == "file:///b.py"
    finally:
        session.close()


def test_notification_handlers_observe_push_messages_without_consuming_waiters(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    observed: list[dict[str, Any]] = []
    try:
        session.add_notification_handler("textDocument/publishDiagnostics", observed.append)
        session.request(
            {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/notifications"},
            dict[str, Any],
        )
        queued = session.wait_for_notification("textDocument/publishDiagnostics", uri="file:///a.py")
        assert queued["params"]["uri"] == "file:///a.py"
        assert {message["params"]["uri"] for message in observed} == {"file:///a.py", "file:///b.py"}
    finally:
        session.close()


def test_notification_backlog_without_uri_returns_latest_matching_method(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    try:
        session.request(
            {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/notifications"},
            dict[str, Any],
        )
        notification = session.wait_for_notification("textDocument/publishDiagnostics")
        assert notification["params"]["uri"] == "file:///a.py"
    finally:
        session.close()


def test_notification_backlog_keeps_latest_value_per_compatibility_key(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    try:
        session.request(
            {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/notification-updates"},
            dict[str, Any],
        )
        notification = session.wait_for_notification(
            "textDocument/publishDiagnostics",
            uri="file:///latest.py",
        )
        assert notification["params"]["version"] == 2
    finally:
        session.close()


def test_uri_less_notification_matches_workspace_compatibility_uri(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    try:
        session.request(
            {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/uri-less-notification"},
            dict[str, Any],
        )
        notification = session.wait_for_notification(
            "window/logMessage",
            uri="file:///workspace-placeholder",
        )
        assert notification["params"]["message"] == "ready"
    finally:
        session.close()


def test_async_server_request_handler_is_rejected(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)

    async def async_handler(params: Any) -> Any:
        return params

    try:
        with pytest.raises(TypeError, match="must be synchronous"):
            session.register_server_request_handler("workspace/configuration", async_handler)
    finally:
        session.close()


def test_async_callable_server_request_handler_is_rejected(tmp_path: Path) -> None:
    class AsyncHandler:
        async def __call__(self, params: Any) -> Any:
            return params

    session, _ = make_session(tmp_path)
    try:
        with pytest.raises(TypeError, match="must be synchronous"):
            session.register_server_request_handler("workspace/configuration", AsyncHandler())
        with pytest.raises(TypeError, match="must be callable"):
            session.register_server_request_handler("workspace/configuration", 42)  # type: ignore[arg-type]
    finally:
        session.close()


def test_start_failure_releases_event_loop_thread(tmp_path: Path) -> None:
    session = LspSession(
        [str(tmp_path / "missing-language-server")],
        request_timeout=0.5,
        shutdown_timeout=0.1,
    )
    with pytest.raises(FileNotFoundError):
        session.start()
    assert session.is_running is False
    assert session._thread is None
    session.close()


def test_close_before_start_is_immediate_and_idempotent() -> None:
    session = LspSession(["unused"], shutdown_timeout=0.01)
    started_at = time.monotonic()
    session.close()
    session.close()

    assert time.monotonic() - started_at < 0.1
    assert session._cleanup_complete.is_set()
    with pytest.raises(LspSessionClosedError, match="closed"):
        session.start()


def test_loop_ready_is_signaled_only_while_loop_is_running(tmp_path: Path) -> None:
    class LoopRunningEvent(threading.Event):
        def __init__(self, session: LspSession) -> None:
            super().__init__()
            self._session = session

        def set(self) -> None:
            assert self._session._loop is not None
            assert self._session._loop.is_running()
            super().set()

    replacement = LspSession(
        [sys.executable, str(FAKE_SERVER), str(tmp_path / "replacement-marker")],
        request_timeout=0.5,
        shutdown_timeout=0.1,
    )
    replacement._loop_ready = LoopRunningEvent(replacement)
    try:
        replacement.start()
        assert replacement.is_running
    finally:
        replacement.close()


def test_concurrent_start_owns_only_one_event_loop_thread(tmp_path: Path) -> None:
    session = LspSession(
        [sys.executable, str(FAKE_SERVER), str(tmp_path / "concurrent-marker")],
        request_timeout=1.0,
        shutdown_timeout=0.1,
    )
    barrier = threading.Barrier(3)

    def start_session() -> None:
        barrier.wait()
        session.start()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(start_session) for _ in range(2)]
            barrier.wait()
            for future in futures:
                future.result(timeout=1.0)
        assert session._thread is not None
        assert session._thread.is_alive()
    finally:
        session.close()


def test_close_owns_process_exit_race(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    close_entered = threading.Event()
    release_close = threading.Event()
    original_close_process = session._close_process

    async def delayed_close_process() -> None:
        close_entered.set()
        await asyncio.to_thread(release_close.wait, 1.0)
        await original_close_process()

    async def kill_process() -> None:
        assert session._process is not None
        session._process.kill()
        await session._process.wait()

    session._close_process = delayed_close_process  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=1) as executor:
        close_result = executor.submit(session.close)
        assert close_entered.wait(timeout=0.5)
        session._submit(kill_process(), timeout=0.5)
        release_close.set()
        close_result.result(timeout=1.0)

    assert session._thread is None
    assert isinstance(session._session_close_error, LspSessionClosedError)


@pytest.mark.parametrize("_iteration", range(10))
def test_close_during_initialize_cannot_commit_initialized_state(tmp_path: Path, _iteration: int) -> None:
    del _iteration
    session, _ = make_session(tmp_path)
    initialized_notification_sent = threading.Event()
    release_initialize = threading.Event()
    original_notify = session.notify

    def delayed_notify(message: object) -> None:
        original_notify(message)
        if isinstance(message, types.InitializedNotification):
            initialized_notification_sent.set()
            assert release_initialize.wait(timeout=1.0)

    session.notify = delayed_notify  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=1) as executor:
        initialize = executor.submit(
            session.initialize,
            types.InitializeParams(capabilities=types.ClientCapabilities()),
        )
        assert initialized_notification_sent.wait(timeout=0.5)
        session.close()
        release_initialize.set()
        with pytest.raises(LspSessionClosedError, match="initialize was completing"):
            initialize.result(timeout=0.5)

    assert session._initialized is False


def test_close_has_outer_deadline_and_background_cleanup_continues(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path, shutdown_timeout=0.01)
    cleanup_started = threading.Event()
    release_cleanup = asyncio.Event()
    original_close_process = session._close_process

    async def delayed_close_process() -> None:
        cleanup_started.set()
        await release_cleanup.wait()
        await original_close_process()

    session._close_process = delayed_close_process  # type: ignore[method-assign]
    started_at = time.monotonic()
    with pytest.raises(TimeoutError, match="cleanup continues"):
        session.close()
    assert cleanup_started.is_set()
    assert time.monotonic() - started_at < 1.5

    loop = session._loop
    assert loop is not None
    loop.call_soon_threadsafe(release_cleanup.set)
    assert session._cleanup_complete.wait(timeout=2.0)
    assert session.returncode is not None


async def test_killed_process_reap_has_a_deadline() -> None:
    class NeverReapedProcess:
        returncode: int | None = None
        terminated = False
        killed = False

        async def wait(self) -> int:
            await asyncio.Event().wait()
            return 0

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

    session = LspSession(["unused"], shutdown_timeout=0.01)
    process = NeverReapedProcess()
    try:
        with pytest.raises(TimeoutError, match="reaping"):
            await session._wait_then_terminate(process)  # type: ignore[arg-type]
        assert process.terminated
        assert process.killed
    finally:
        session._handler_executor.shutdown(wait=False, cancel_futures=True)


def test_large_stderr_without_newline_is_fully_drained(tmp_path: Path) -> None:
    session, _ = make_session(tmp_path)
    try:
        response = session.request(
            {"jsonrpc": "2.0", "id": session.next_request_id(), "method": "test/large-stderr"},
            dict[str, Any],
        )
        assert response["result"] == "drained"
    finally:
        session.close()


def test_event_loop_start_timeout_does_not_leak_thread(tmp_path: Path) -> None:
    class DelayedLoopSession(LspSession):
        def _run_event_loop(self) -> None:
            self._loop_stop_requested.wait(timeout=1.0)
            super()._run_event_loop()

    threads_before = {thread.ident for thread in threading.enumerate() if thread.name == "ide4ai-lsp-session"}
    session = DelayedLoopSession(
        [sys.executable, str(FAKE_SERVER), str(tmp_path / "unused-marker")],
        request_timeout=0.01,
        shutdown_timeout=0.1,
    )

    with pytest.raises(TimeoutError, match="event loop"):
        session.start()

    threads_after = {thread.ident for thread in threading.enumerate() if thread.name == "ide4ai-lsp-session"}
    assert threads_after == threads_before
    assert session._thread is None
    with pytest.raises(LspSessionClosedError, match="closed"):
        session.start()
