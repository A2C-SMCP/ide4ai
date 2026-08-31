"""Language server process lifecycle on top of the async JSON-RPC transport."""

from __future__ import annotations

import asyncio
import inspect
import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Mapping, Sequence
from concurrent.futures import Future as ConcurrentFuture
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as ConcurrentTimeoutError
from pathlib import Path
from typing import Any, TypeVar, cast

from loguru import logger
from lsprotocol import converters, types

from ide4ai.lsp.errors import JsonRpcProtocolError, LspProcessExitedError, LspSessionClosedError
from ide4ai.lsp.position_codec import PositionCodec, PositionEncoding
from ide4ai.lsp.transport import JsonRpcMessage, JsonRpcTransport

ResponseT = TypeVar("ResponseT")
CoroutineResultT = TypeVar("CoroutineResultT")
ServerRequestHandler = Callable[[Any], Any]
SessionCloseCallback = Callable[[BaseException], None]
NotificationHandler = Callable[[JsonRpcMessage], None]
NotificationWaiter = tuple[str | None, asyncio.Future[JsonRpcMessage]]
NotificationKey = tuple[str, str | None]


class LspSession:
    """Own one language-server process and its JSON-RPC session.

    IDE4AI's public environment API is synchronous. This class keeps that API
    while running the subprocess streams and response dispatcher on one
    dedicated asyncio event loop. Synchronous callers block on Futures, never
    on sleep-based cache polling.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        request_timeout: float = 10.0,
        shutdown_timeout: float = 2.0,
    ) -> None:
        if not command:
            raise ValueError("Language server command cannot be empty")
        self.command = tuple(command)
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self.request_timeout = request_timeout
        self.shutdown_timeout = shutdown_timeout

        self._converter = converters.get_converter()
        self._id_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._close_callback_lock = threading.Lock()
        self._next_id = 1
        self._loop_ready = threading.Event()
        self._loop_stop_requested = threading.Event()
        self._cleanup_complete = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._transport: JsonRpcTransport | None = None
        self._process_watch_task: asyncio.Task[None] | None = None
        self._transport_watch_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._handler_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ide4ai-lsp-handler")
        self._notification_backlog: OrderedDict[NotificationKey, JsonRpcMessage] = OrderedDict()
        self._notification_waiters: dict[str, list[NotificationWaiter]] = {}
        self._server_request_handlers: dict[str, ServerRequestHandler] = {}
        self._notification_handlers: dict[str, list[NotificationHandler]] = {}
        self._close_callbacks: list[SessionCloseCallback] = []
        self._session_close_error: BaseException | None = None
        self._position_codec = PositionCodec()
        self._server_capabilities: types.ServerCapabilities | None = None
        self._initialized = False
        self._closing = False
        self._closed = False
        self._state_generation = 0

    @property
    def is_running(self) -> bool:
        process = self._process
        return process is not None and process.returncode is None and not self._closed

    @property
    def returncode(self) -> int | None:
        return self._process.returncode if self._process is not None else None

    @property
    def pending_request_count(self) -> int:
        if self._transport is None or self._transport.is_closed or self._loop is None:
            return 0
        return self._submit(self._get_pending_request_count())

    @property
    def position_codec(self) -> PositionCodec:
        """Codec for the position encoding negotiated during initialize."""
        return self._position_codec

    @property
    def server_capabilities(self) -> types.ServerCapabilities | None:
        """Capabilities returned by the successful initialize handshake."""
        return self._server_capabilities

    def start(self) -> None:
        """Start the event-loop thread and language-server subprocess."""
        with self._lifecycle_lock:
            self._start_locked()

    def _start_locked(self) -> None:
        if self._closed:
            raise LspSessionClosedError("Cannot restart a closed LSP session")
        if self._thread is not None:
            return

        self._loop_ready.clear()
        self._loop_stop_requested.clear()
        self._thread = threading.Thread(target=self._run_event_loop, name="ide4ai-lsp-session", daemon=True)
        self._thread.start()
        if not self._loop_ready.wait(timeout=self.request_timeout):
            self._stop_event_loop()
            with self._state_lock:
                self._closing = True
                self._closed = True
                self._state_generation += 1
            error = TimeoutError("Timed out while starting the LSP event loop")
            self._notify_session_closed(error)
            raise error
        try:
            self._submit(self._start_process(), timeout=self.request_timeout)
        except BaseException as error:
            with self._state_lock:
                self._closing = True
                self._state_generation += 1
            try:
                self._submit(self._close_process(), timeout=self.shutdown_timeout * 2 + 1)
            except BaseException:
                pass
            self._stop_event_loop()
            with self._state_lock:
                self._closed = True
            self._notify_session_closed(error)
            raise

    def initialize(self, params: types.InitializeParams, *, timeout: float | None = None) -> types.InitializeResult:
        """Perform the LSP initialize/initialized handshake."""
        with self._state_lock:
            if self._closed or self._closing:
                raise LspSessionClosedError("Cannot initialize a closed LSP session")
            generation = self._state_generation
        request = types.InitializeRequest(id=self.next_request_id(), params=params)
        response = self.request(request, types.InitializeResponse, timeout=timeout)
        if response.result is None:
            raise JsonRpcProtocolError("Initialize response did not contain a result")
        negotiated_encoding = response.result.capabilities.position_encoding or "utf-16"
        if isinstance(negotiated_encoding, types.PositionEncodingKind):
            negotiated_encoding = negotiated_encoding.value
        if negotiated_encoding not in ("utf-8", "utf-16"):
            raise JsonRpcProtocolError(f"Unsupported negotiated LSP position encoding: {negotiated_encoding}")
        position_codec = PositionCodec(cast(PositionEncoding, negotiated_encoding))
        self.notify(types.InitializedNotification(params=types.InitializedParams()))
        with self._state_lock:
            if self._closed or self._closing or self._state_generation != generation:
                raise LspSessionClosedError("LSP session closed while initialize was completing")
            self._position_codec = position_codec
            self._server_capabilities = response.result.capabilities
            self._initialized = True
        return response.result

    def request(
        self,
        message: object,
        response_type: type[ResponseT],
        *,
        timeout: float | None = None,
    ) -> ResponseT:
        """Send a typed lsprotocol request and return its typed response."""
        self._assert_started()
        return self._submit(self._request(message, response_type, timeout=timeout))

    def notify(self, message: object) -> None:
        """Send a typed lsprotocol notification."""
        self._assert_started()
        self._submit(self._notify(message))

    def wait_for_notification(
        self,
        method: str,
        *,
        uri: str | None = None,
        timeout: float | None = None,
    ) -> JsonRpcMessage:
        """Wait for one server notification without polling."""
        self._assert_started()
        return self._submit(self._wait_for_notification(method, uri=uri, timeout=timeout))

    def register_server_request_handler(self, method: str, handler: ServerRequestHandler) -> None:
        """Register a handler for a server-to-client JSON-RPC request."""
        if self._closed:
            raise LspSessionClosedError("Cannot register a handler on a closed LSP session")
        if not method:
            raise ValueError("Server request method cannot be empty")
        if not callable(handler):
            raise TypeError("LSP server request handler must be callable")
        handler_call = type(handler).__call__
        if inspect.iscoroutinefunction(handler) or inspect.iscoroutinefunction(handler_call):
            raise TypeError("LSP server request handlers must be synchronous callables")
        self._server_request_handlers[method] = handler

    def add_close_callback(self, callback: SessionCloseCallback) -> None:
        """Invoke ``callback`` once when this session reaches a terminal state."""
        with self._close_callback_lock:
            error = self._session_close_error
            if error is None:
                self._close_callbacks.append(callback)
                return
        callback(error)

    def add_notification_handler(self, method: str, handler: NotificationHandler) -> None:
        """Register a synchronous observer for server notifications."""
        if not method:
            raise ValueError("Notification method cannot be empty")
        if not callable(handler):
            raise TypeError("Notification handler must be callable")
        self._notification_handlers.setdefault(method, []).append(handler)

    def next_request_id(self) -> int:
        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
            return request_id

    def close(self) -> None:
        """Shut down the LSP session and release its event-loop thread."""
        with self._lifecycle_lock:
            self._close_locked()

    def _close_locked(self) -> None:
        with self._state_lock:
            if self._cleanup_complete.is_set():
                return
            owns_cleanup = not self._closing
            if owns_cleanup:
                self._closing = True
                self._closed = True
                self._state_generation += 1
        close_budget = max(1.0, self.shutdown_timeout * 6 + 1)
        if not owns_cleanup:
            self._wait_for_event_loop_shutdown(close_budget)
            return

        close_future: ConcurrentFuture[None] | None = None
        try:
            if self._loop is not None and self._thread is not None:
                loop = self._loop
                close_future = asyncio.run_coroutine_threadsafe(self._close_process(), loop)
                try:
                    close_future.result(timeout=close_budget)
                except ConcurrentTimeoutError as exc:
                    if close_future.done():
                        raise
                    close_future.add_done_callback(lambda _: loop.call_soon_threadsafe(loop.stop))
                    raise TimeoutError(
                        f"Timed out after {close_budget:.3f}s while closing the LSP session; cleanup continues"
                    ) from exc
        finally:
            if close_future is None or close_future.done():
                self._stop_event_loop()
            self._notify_session_closed(LspSessionClosedError("LSP session closed"))

    def __enter__(self) -> LspSession:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    async def _start_process(self) -> None:
        process_env = os.environ.copy()
        if self.env is not None:
            process_env.update(self.env)
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=process_env,
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("Language server subprocess did not expose stdin/stdout streams")

        self._transport = JsonRpcTransport(
            self._process.stdout,
            self._process.stdin,
            message_handler=self._handle_incoming_message,
            peer_closed_error_factory=self._process_exited_error,
            default_timeout=self.request_timeout,
            cleanup_timeout=self.shutdown_timeout,
        )
        self._transport.start()
        self._transport_watch_task = asyncio.create_task(
            self._watch_transport(),
            name="ide4ai-lsp-transport-watch",
        )
        self._process_watch_task = asyncio.create_task(self._watch_process(), name="ide4ai-lsp-process-watch")
        if self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._drain_stderr(), name="ide4ai-lsp-stderr")

    async def _request(
        self,
        message: object,
        response_type: type[ResponseT],
        *,
        timeout: float | None,
    ) -> ResponseT:
        transport = self._require_transport()
        payload = self._unstructure_message(message)
        raw_response = await transport.request(payload, timeout=timeout)
        return self._converter.structure(raw_response, response_type)

    async def _notify(self, message: object, *, timeout: float | None = None) -> None:
        await self._require_transport().notify(self._unstructure_message(message), timeout=timeout)

    async def _wait_for_notification(
        self,
        method: str,
        *,
        uri: str | None,
        timeout: float | None,
    ) -> JsonRpcMessage:
        transport = self._require_transport()
        queued = self._take_queued_notification(method, uri)
        if queued is not None:
            return queued

        loop = asyncio.get_running_loop()
        notification_future: asyncio.Future[JsonRpcMessage] = loop.create_future()
        waiter = (uri, notification_future)
        self._notification_waiters.setdefault(method, []).append(waiter)
        notification_timeout = self.request_timeout if timeout is None else timeout
        closed_task = asyncio.create_task(transport.wait_closed(), name="ide4ai-lsp-notification-close")
        waitables: set[asyncio.Future[Any]] = {notification_future, closed_task}
        try:
            done, _ = await asyncio.wait(
                waitables,
                timeout=notification_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if notification_future in done:
                return notification_future.result()
            if closed_task in done:
                await closed_task
            raise TimeoutError(f"LSP notification {method!r} did not arrive within {notification_timeout:.3f}s")
        finally:
            waiters = self._notification_waiters.get(method)
            if waiters is not None:
                try:
                    waiters.remove(waiter)
                except ValueError:
                    pass
                if not waiters:
                    self._notification_waiters.pop(method, None)
            if not notification_future.done():
                notification_future.cancel()
            if not closed_task.done():
                closed_task.cancel()
            await asyncio.gather(closed_task, return_exceptions=True)

    async def _handle_incoming_message(self, message: JsonRpcMessage) -> None:
        method = message.get("method")
        if not isinstance(method, str):
            raise JsonRpcProtocolError("Inbound JSON-RPC request/notification is missing a method")

        request_id = message.get("id")
        if isinstance(request_id, (int, str)) and not isinstance(request_id, bool):
            handler = self._server_request_handlers.get(method)
            if handler is None:
                await self._require_transport().send_error(
                    request_id,
                    code=-32601,
                    message=f"No client handler registered for {method}",
                )
                return
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(self._handler_executor, handler, message.get("params"))
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise TypeError("LSP server request handlers must not return awaitables")
                await self._require_transport().send_result(request_id, result)
            except Exception as exc:
                await self._require_transport().send_error(
                    request_id,
                    code=-32603,
                    message=str(exc),
                )
            return

        uri = self._notification_uri(message)
        for handler in tuple(self._notification_handlers.get(method, ())):
            try:
                handler(message)
            except Exception:
                logger.exception("LSP notification handler failed for {}", method)
        waiters = self._notification_waiters.get(method, [])
        for waiter in tuple(waiters):
            requested_uri, future = waiter
            if future.done() or not self._notification_matches_uri(uri, requested_uri):
                continue
            waiters.remove(waiter)
            future.set_result(message)
            return

        key = self._notification_key(method, uri)
        self._notification_backlog[key] = message
        self._notification_backlog.move_to_end(key)
        while len(self._notification_backlog) > 1000:
            self._notification_backlog.popitem(last=False)

    def _take_queued_notification(self, method: str, uri: str | None) -> JsonRpcMessage | None:
        key = self._notification_key(method, uri)
        message = self._notification_backlog.pop(key, None)
        if message is not None:
            return message
        if uri is not None:
            return self._notification_backlog.pop((method, None), None)
        for queued_key in reversed(self._notification_backlog):
            if queued_key[0] == method:
                return self._notification_backlog.pop(queued_key)
        return None

    @staticmethod
    def _notification_key(method: str, uri: str | None) -> NotificationKey:
        if method == "textDocument/publishDiagnostics":
            return method, uri
        return method, None

    @staticmethod
    def _notification_matches_uri(notification_uri: str | None, requested_uri: str | None) -> bool:
        return requested_uri is None or notification_uri is None or notification_uri == requested_uri

    @staticmethod
    def _notification_uri(message: JsonRpcMessage) -> str | None:
        params = message.get("params")
        if not isinstance(params, Mapping):
            return None
        uri = params.get("uri")
        if isinstance(uri, str):
            return uri
        text_document = params.get("textDocument")
        if isinstance(text_document, Mapping):
            nested_uri = text_document.get("uri")
            if isinstance(nested_uri, str):
                return nested_uri
        return None

    async def _watch_process(self) -> None:
        process = self._process
        if process is None:
            return
        returncode = await process.wait()
        transport = self._transport
        if not self._closing and transport is not None:
            await transport.close(LspProcessExitedError(returncode))

    async def _watch_transport(self) -> None:
        transport = self._transport
        if transport is None:
            return
        try:
            await transport.wait_closed()
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            with self._state_lock:
                if self._closing:
                    return
                self._closing = True
                self._closed = True
                self._initialized = False
                self._state_generation += 1
            self._fail_notification_waiters(error)
            self._notify_session_closed(error)
            process = self._process
            loop = asyncio.get_running_loop()
            try:
                if process is not None and process.returncode is None:
                    await self._wait_then_terminate(process)
            except TimeoutError:
                logger.exception("Timed out while reclaiming a terminal LSP process")
            finally:
                loop.call_later(0.05, loop.stop)

    async def _process_exited_error(self) -> BaseException:
        process = self._process
        if process is None:
            return LspProcessExitedError(None)
        try:
            returncode = await asyncio.wait_for(process.wait(), timeout=0.05)
        except asyncio.TimeoutError:
            return LspSessionClosedError("Language server closed stdout before exiting")
        return LspProcessExitedError(returncode)

    async def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while True:
            chunk = await process.stderr.read(4096)
            if not chunk:
                return
            logger.debug("LSP stderr: {}", chunk.decode("utf-8", errors="replace").rstrip())

    def _notify_session_closed(self, error: BaseException) -> None:
        with self._close_callback_lock:
            if self._session_close_error is not None:
                return
            self._session_close_error = error
            callbacks = tuple(self._close_callbacks)
            self._close_callbacks.clear()
        for callback in callbacks:
            try:
                callback(error)
            except Exception:
                logger.exception("LSP session close callback failed")

    def _fail_notification_waiters(self, error: BaseException) -> None:
        for waiters in self._notification_waiters.values():
            for _, future in waiters:
                if not future.done():
                    future.set_exception(error)
        self._notification_waiters.clear()

    async def _close_process(self) -> None:
        process = self._process
        transport = self._transport
        try:
            if process is not None and process.returncode is None and transport is not None and not transport.is_closed:
                if self._initialized:
                    try:
                        shutdown_request = types.ShutdownRequest(id=self.next_request_id())
                        await self._request(shutdown_request, types.ShutdownResponse, timeout=self.shutdown_timeout)
                    except Exception as exc:
                        logger.warning("LSP shutdown request failed: {}", exc)
                    if not transport.is_closed:
                        try:
                            await self._notify(types.ExitNotification(), timeout=self.shutdown_timeout)
                        except Exception as exc:
                            logger.warning("LSP exit notification failed: {}", exc)

                await transport.close()
        finally:
            if process is not None and process.returncode is None:
                await self._wait_then_terminate(process)

            current_task = asyncio.current_task()
            for task in (self._stderr_task, self._process_watch_task, self._transport_watch_task):
                if task is not None and task is not current_task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._initialized = False

    async def _wait_then_terminate(self, process: asyncio.subprocess.Process) -> None:
        try:
            await asyncio.wait_for(process.wait(), timeout=self.shutdown_timeout)
            return
        except asyncio.TimeoutError:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self.shutdown_timeout)
            return
        except asyncio.TimeoutError:
            process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=self.shutdown_timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timed out while reaping the killed LSP process") from exc

    async def _get_pending_request_count(self) -> int:
        transport = self._transport
        return transport.pending_request_count if transport is not None else 0

    def _run_event_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        loop.call_soon(self._loop_ready.set)
        if self._loop_stop_requested.is_set():
            loop.call_soon(loop.stop)
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            self._handler_executor.shutdown(wait=False, cancel_futures=True)
            loop.close()
            if self._loop is loop:
                self._loop = None
            if self._thread is threading.current_thread():
                self._thread = None
            self._cleanup_complete.set()

    def _stop_event_loop(self) -> None:
        self._loop_stop_requested.set()
        loop = self._loop
        thread = self._thread
        if loop is None and thread is None:
            self._handler_executor.shutdown(wait=False, cancel_futures=True)
            self._cleanup_complete.set()
            return
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self.shutdown_timeout + 1)
        if thread is not None and thread.is_alive():
            raise RuntimeError("LSP session event-loop thread did not stop")
        self._thread = None
        self._loop = None

    def _wait_for_event_loop_shutdown(self, timeout: float) -> None:
        thread = self._thread
        if thread is threading.current_thread():
            return
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                raise TimeoutError(f"Timed out after {timeout:.3f}s waiting for LSP cleanup to complete")
        elif not self._cleanup_complete.wait(timeout=timeout):
            raise TimeoutError(f"Timed out after {timeout:.3f}s waiting for LSP cleanup to complete")
        if not self._cleanup_complete.is_set():
            raise RuntimeError("LSP event-loop thread stopped before cleanup completed")

    def _submit(
        self,
        coroutine: Coroutine[Any, Any, CoroutineResultT],
        *,
        timeout: float | None = None,
    ) -> CoroutineResultT:
        loop = self._loop
        if loop is None or not loop.is_running():
            coroutine.close()
            raise LspSessionClosedError("LSP session event loop is not running")
        future: ConcurrentFuture[CoroutineResultT] = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=timeout)
        except ConcurrentTimeoutError:
            future.cancel()
            raise

    def _assert_started(self) -> None:
        if self._closed:
            raise LspSessionClosedError("LSP session is closed")
        if self._transport is None or self._thread is None:
            raise LspSessionClosedError("LSP session has not been started")

    def _require_transport(self) -> JsonRpcTransport:
        if self._transport is None:
            raise LspSessionClosedError("LSP session transport is unavailable")
        return self._transport

    def _unstructure_message(self, message: object) -> JsonRpcMessage:
        payload = self._converter.unstructure(message)
        if not isinstance(payload, dict):
            raise JsonRpcProtocolError("lsprotocol message did not serialize to a JSON object")
        return cast(JsonRpcMessage, payload)
