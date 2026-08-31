"""Event-driven JSON-RPC transport for Language Server Protocol streams."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal, TypeAlias, cast

from ide4ai.lsp.errors import (
    JsonRpcProtocolError,
    JsonRpcRequestError,
    JsonRpcTimeoutError,
    JsonRpcWriteTimeoutError,
    LspSessionClosedError,
)

JsonRpcId: TypeAlias = int | str
JsonRpcMessage: TypeAlias = dict[str, Any]
MessageHandler: TypeAlias = Callable[[JsonRpcMessage], Awaitable[None]]
PeerClosedErrorFactory: TypeAlias = Callable[[], BaseException | Awaitable[BaseException]]
MessageKind: TypeAlias = Literal["request", "notification", "response"]


class JsonRpcTransport:
    """Read and write Content-Length framed JSON-RPC messages.

    A single reader task dispatches responses directly to Futures keyed by
    request ID. Notifications and server-to-client requests are delivered to
    ``message_handler`` without polling.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        message_handler: MessageHandler | None = None,
        peer_closed_error_factory: PeerClosedErrorFactory | None = None,
        default_timeout: float = 10.0,
        cleanup_timeout: float | None = None,
        max_content_length: int = 16 * 1024 * 1024,
        max_queued_messages: int = 256,
        message_worker_count: int = 8,
    ) -> None:
        if max_queued_messages <= 0:
            raise ValueError("max_queued_messages must be positive")
        if message_worker_count <= 0:
            raise ValueError("message_worker_count must be positive")
        self._reader = reader
        self._writer = writer
        self._message_handler = message_handler
        self._peer_closed_error_factory = peer_closed_error_factory
        self._default_timeout = default_timeout
        self._cleanup_timeout = default_timeout if cleanup_timeout is None else cleanup_timeout
        self._max_content_length = max_content_length
        self._pending: dict[JsonRpcId, asyncio.Future[JsonRpcMessage]] = {}
        self._write_lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None
        self._message_queue: asyncio.Queue[JsonRpcMessage] = asyncio.Queue(maxsize=max_queued_messages)
        self._message_worker_count = message_worker_count
        self._message_workers: list[asyncio.Task[None]] = []
        self._active_message_handlers = 0
        self._closed = False
        self._resources_closed = False
        self._closed_event = asyncio.Event()
        self._close_error: BaseException | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    @property
    def pending_request_count(self) -> int:
        return len(self._pending)

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def message_handler_load(self) -> int:
        return self._message_queue.qsize() + self._active_message_handlers

    def start(self) -> None:
        if self._closed:
            raise LspSessionClosedError("Cannot start a closed JSON-RPC transport")
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._reader_loop(), name="ide4ai-jsonrpc-reader")
            if self._message_handler is not None:
                self._message_workers = [
                    asyncio.create_task(self._message_worker(), name=f"ide4ai-jsonrpc-handler-{index}")
                    for index in range(self._message_worker_count)
                ]

    async def request(
        self,
        message: Mapping[str, Any],
        *,
        timeout: float | None = None,
    ) -> JsonRpcMessage:
        """Send a request and await its matching response Future."""
        self._assert_open()
        if self._validate_message(message) != "request":
            raise JsonRpcProtocolError("JsonRpcTransport.request requires a JSON-RPC request message")
        request_id = self._request_id(message)
        if request_id in self._pending:
            raise JsonRpcProtocolError(f"Duplicate JSON-RPC request id: {request_id!r}")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[JsonRpcMessage] = loop.create_future()
        self._pending[request_id] = future
        request_timeout = self._default_timeout if timeout is None else timeout
        deadline = loop.time() + request_timeout
        try:
            try:
                await asyncio.wait_for(self._write_message(message), timeout=request_timeout)
            except asyncio.TimeoutError as exc:
                timeout_error = JsonRpcTimeoutError(request_id, request_timeout)
                if self._pending.get(request_id) is future:
                    self._pending.pop(request_id)
                future.cancel()
                self._begin_close(timeout_error)
                raise timeout_error from exc
            except BaseException:
                if future.done() and not future.cancelled():
                    future.exception()
                raise
            remaining = max(0.0, deadline - loop.time())
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=remaining)
            except asyncio.TimeoutError as exc:
                future.cancel()
                raise JsonRpcTimeoutError(request_id, request_timeout) from exc
        finally:
            if self._pending.get(request_id) is future:
                self._pending.pop(request_id, None)

    async def notify(self, message: Mapping[str, Any], *, timeout: float | None = None) -> None:
        """Send a notification or response without awaiting a reply."""
        self._assert_open()
        if self._validate_message(message) == "request":
            raise JsonRpcProtocolError("JsonRpcTransport.notify cannot send a JSON-RPC request message")
        write_timeout = self._default_timeout if timeout is None else timeout
        try:
            await asyncio.wait_for(self._write_message(message), timeout=write_timeout)
        except asyncio.TimeoutError as exc:
            timeout_error = JsonRpcWriteTimeoutError(write_timeout)
            self._begin_close(timeout_error)
            raise timeout_error from exc

    async def send_result(self, request_id: JsonRpcId, result: Any) -> None:
        await self.notify({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def send_error(
        self,
        request_id: JsonRpcId,
        *,
        code: int,
        message: str,
        data: Any = None,
    ) -> None:
        error: JsonRpcMessage = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        await self.notify({"jsonrpc": "2.0", "id": request_id, "error": error})

    async def close(self, error: BaseException | None = None) -> None:
        self._begin_close(error or LspSessionClosedError("JSON-RPC transport closed"))
        if self._cleanup_task is not None:
            await self._cleanup_task

    def _begin_close(self, error: BaseException) -> None:
        if self._resources_closed:
            return
        self._resources_closed = True
        self._closed = True
        self._close_error = error
        self._closed_event.set()
        self._fail_pending(self._close_error)
        self._writer.close()
        self._cleanup_task = asyncio.create_task(self._cleanup_resources(), name="ide4ai-jsonrpc-cleanup")

    async def _cleanup_resources(self) -> None:
        current_task = asyncio.current_task()
        if self._reader_task is not None and self._reader_task is not current_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        handler_tasks = [task for task in self._message_workers if task is not current_task]
        for task in handler_tasks:
            task.cancel()
        if handler_tasks:
            done, pending = await asyncio.wait(handler_tasks, timeout=self._cleanup_timeout)
            for task in pending:
                task.cancel()
            if done:
                await asyncio.gather(*done, return_exceptions=True)

        try:
            await asyncio.wait_for(self._writer.wait_closed(), timeout=self._cleanup_timeout)
        except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError):
            pass

    async def wait_closed(self) -> None:
        """Wait until the transport closes and propagate the closing reason."""
        await self._closed_event.wait()
        if self._close_error is not None:
            raise self._close_error

    async def _reader_loop(self) -> None:
        failure: BaseException | None = None
        try:
            while not self._closed:
                message = await self._read_message()
                await self._dispatch_message(message)
        except asyncio.CancelledError:
            raise
        except asyncio.IncompleteReadError as exc:
            if self._peer_closed_error_factory is None:
                failure = LspSessionClosedError("JSON-RPC peer closed the stream")
            else:
                peer_error = self._peer_closed_error_factory()
                failure = await peer_error if inspect.isawaitable(peer_error) else peer_error
            failure.__cause__ = exc
        except Exception as exc:
            failure = exc
        finally:
            if failure is not None:
                self._begin_close(failure)

    async def _read_message(self) -> JsonRpcMessage:
        try:
            raw_header = await self._reader.readuntil(b"\r\n\r\n")
        except asyncio.LimitOverrunError as exc:
            raise JsonRpcProtocolError("JSON-RPC header exceeds the stream reader limit") from exc

        content_length: int | None = None
        for raw_line in raw_header[:-4].split(b"\r\n"):
            try:
                name, value = raw_line.decode("ascii").split(":", 1)
            except (UnicodeDecodeError, ValueError) as exc:
                raise JsonRpcProtocolError(f"Malformed JSON-RPC header line: {raw_line!r}") from exc
            if name.strip().lower() == "content-length":
                if content_length is not None:
                    raise JsonRpcProtocolError("Duplicate Content-Length header")
                try:
                    content_length = int(value.strip())
                except ValueError as exc:
                    raise JsonRpcProtocolError(f"Invalid Content-Length value: {value!r}") from exc

        if content_length is None:
            raise JsonRpcProtocolError("Missing Content-Length header")
        if not 0 <= content_length <= self._max_content_length:
            raise JsonRpcProtocolError(
                f"Content-Length {content_length} is outside allowed range 0..{self._max_content_length}"
            )

        raw_body = await self._reader.readexactly(content_length)
        try:
            decoded = json.loads(
                raw_body.decode("utf-8"),
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {value}")),
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise JsonRpcProtocolError("JSON-RPC body is not valid UTF-8 JSON") from exc
        if not isinstance(decoded, dict):
            raise JsonRpcProtocolError("JSON-RPC message body must be an object")
        message = cast(JsonRpcMessage, decoded)
        self._validate_message(message)
        return message

    async def _dispatch_message(self, message: JsonRpcMessage) -> None:
        if "method" not in message:
            request_id = self._response_id(message)
            if request_id is None:
                return
            future = self._pending.get(request_id)
            if future is None or future.done():
                return
            error = message.get("error")
            if isinstance(error, dict):
                future.set_exception(
                    JsonRpcRequestError(
                        request_id,
                        int(error.get("code", -32603)),
                        str(error.get("message", "Unknown JSON-RPC error")),
                        error.get("data"),
                    )
                )
            else:
                future.set_result(message)
            return

        if self._message_handler is not None:
            try:
                self._message_queue.put_nowait(message)
            except asyncio.QueueFull as exc:
                raise JsonRpcProtocolError("Inbound JSON-RPC message queue is full") from exc

    async def _message_worker(self) -> None:
        while not self._closed:
            message = await self._message_queue.get()
            self._active_message_handlers += 1
            try:
                await self._run_message_handler(message)
            finally:
                self._active_message_handlers -= 1
                self._message_queue.task_done()

    async def _run_message_handler(self, message: JsonRpcMessage) -> None:
        try:
            if self._message_handler is not None:
                await self._message_handler(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._begin_close(exc)

    async def _write_message(self, message: Mapping[str, Any]) -> None:
        try:
            body = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise JsonRpcProtocolError("JSON-RPC message is not JSON serializable") from exc
        frame = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        write_failure: LspSessionClosedError | None = None
        async with self._write_lock:
            try:
                self._writer.write(frame)
                await self._writer.drain()
            except Exception as exc:
                write_failure = LspSessionClosedError("JSON-RPC peer closed while writing")
                write_failure.__cause__ = exc
        if write_failure is not None:
            self._begin_close(write_failure)
            raise write_failure

    def _fail_pending(self, error: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    def _assert_open(self) -> None:
        if self._closed:
            raise LspSessionClosedError("JSON-RPC transport is closed")
        if self._reader_task is None:
            raise LspSessionClosedError("JSON-RPC transport has not been started")

    @staticmethod
    def _request_id(message: Mapping[str, Any]) -> JsonRpcId:
        request_id = message.get("id")
        if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
            raise JsonRpcProtocolError("JSON-RPC request/response requires an integer or string id")
        return request_id

    @staticmethod
    def _response_id(message: Mapping[str, Any]) -> JsonRpcId | None:
        request_id = message.get("id")
        if request_id is None:
            return None
        if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
            raise JsonRpcProtocolError("JSON-RPC response id must be an integer, string, or null")
        return cast(JsonRpcId, request_id)

    @classmethod
    def _validate_message(cls, message: Mapping[str, Any]) -> MessageKind:
        if message.get("jsonrpc") != "2.0":
            raise JsonRpcProtocolError("JSON-RPC message must declare jsonrpc version '2.0'")

        has_method = "method" in message
        has_result = "result" in message
        has_error = "error" in message

        if has_method:
            method = message.get("method")
            if not isinstance(method, str) or not method:
                raise JsonRpcProtocolError("JSON-RPC request/notification method must be a non-empty string")
            if has_result or has_error:
                raise JsonRpcProtocolError("JSON-RPC request/notification cannot contain result or error")
            if "params" in message and not isinstance(message["params"], (list, Mapping)):
                raise JsonRpcProtocolError("JSON-RPC params must be an array or object")
            if "id" in message:
                cls._request_id(message)
                return "request"
            return "notification"

        if "id" not in message:
            raise JsonRpcProtocolError("JSON-RPC response requires an id")
        cls._response_id(message)
        if has_result == has_error:
            raise JsonRpcProtocolError("JSON-RPC response must contain exactly one of result or error")
        if has_error:
            error = message.get("error")
            if not isinstance(error, Mapping):
                raise JsonRpcProtocolError("JSON-RPC error must be an object")
            code = error.get("code")
            if isinstance(code, bool) or not isinstance(code, int):
                raise JsonRpcProtocolError("JSON-RPC error code must be an integer")
            if not isinstance(error.get("message"), str):
                raise JsonRpcProtocolError("JSON-RPC error message must be a string")
        return "response"
