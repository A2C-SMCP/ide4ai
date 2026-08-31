from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

import pytest

from ide4ai.lsp.errors import (
    JsonRpcProtocolError,
    JsonRpcTimeoutError,
    JsonRpcWriteTimeoutError,
    LspSessionClosedError,
)
from ide4ai.lsp.transport import JsonRpcMessage, JsonRpcTransport


class MemoryStreamWriter:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FailingStreamWriter(MemoryStreamWriter):
    def __init__(self) -> None:
        super().__init__()
        self.fail_writes = False
        self.write_error: Exception = BrokenPipeError()

    async def drain(self) -> None:
        if self.fail_writes:
            raise self.write_error
        await super().drain()


class BlockingStreamWriter(MemoryStreamWriter):
    async def drain(self) -> None:
        await asyncio.Event().wait()


class BlockingCloseStreamWriter(BlockingStreamWriter):
    async def wait_closed(self) -> None:
        await asyncio.Event().wait()


def frame(message: Mapping[str, Any]) -> bytes:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def make_transport(
    *,
    default_timeout: float = 1.0,
    message_handler: Callable[[JsonRpcMessage], Awaitable[None]] | None = None,
    writer: MemoryStreamWriter | None = None,
    max_queued_messages: int = 256,
    message_worker_count: int = 8,
) -> tuple[asyncio.StreamReader, MemoryStreamWriter, JsonRpcTransport]:
    reader = asyncio.StreamReader()
    writer = writer or MemoryStreamWriter()
    transport = JsonRpcTransport(
        reader,
        cast(asyncio.StreamWriter, writer),
        default_timeout=default_timeout,
        message_handler=message_handler,
        max_queued_messages=max_queued_messages,
        message_worker_count=message_worker_count,
    )
    transport.start()
    return reader, writer, transport


async def test_incremental_and_sticky_frames_route_out_of_order_responses() -> None:
    reader, _, transport = make_transport()
    first = asyncio.create_task(transport.request({"jsonrpc": "2.0", "id": 1, "method": "first"}))
    second = asyncio.create_task(transport.request({"jsonrpc": "2.0", "id": 2, "method": "second"}))
    await asyncio.sleep(0)

    payload = frame({"jsonrpc": "2.0", "id": 2, "result": "second"}) + frame(
        {"jsonrpc": "2.0", "id": 1, "result": "first"}
    )
    reader.feed_data(payload[:7])
    await asyncio.sleep(0)
    reader.feed_data(payload[7:31])
    await asyncio.sleep(0)
    reader.feed_data(payload[31:])

    assert (await first)["result"] == "first"
    assert (await second)["result"] == "second"
    assert transport.pending_request_count == 0
    await transport.close()


async def test_outgoing_content_length_uses_utf8_bytes() -> None:
    _, writer, transport = make_transport()
    await transport.notify({"jsonrpc": "2.0", "method": "note", "params": {"text": "😀中文"}})
    header, body = bytes(writer.buffer).split(b"\r\n\r\n", 1)
    assert int(header.split(b":", 1)[1]) == len(body)
    assert json.loads(body.decode("utf-8"))["params"]["text"] == "😀中文"
    await transport.close()


async def test_timeout_removes_pending_future() -> None:
    _, _, transport = make_transport(default_timeout=0.01)
    with pytest.raises(JsonRpcTimeoutError):
        await transport.request({"jsonrpc": "2.0", "id": 7, "method": "never"})
    assert transport.pending_request_count == 0
    await transport.close()


async def test_request_timeout_covers_blocked_write() -> None:
    writer = BlockingCloseStreamWriter()
    _, _, transport = make_transport(default_timeout=0.25, writer=writer)
    loop = asyncio.get_running_loop()
    started_at = loop.time()

    with pytest.raises(JsonRpcTimeoutError):
        await transport.request({"jsonrpc": "2.0", "id": 8, "method": "blocked/write"}, timeout=0.01)

    assert loop.time() - started_at < 0.1
    assert transport.is_closed
    assert transport.pending_request_count == 0
    assert writer.closed
    await transport.close()


async def test_notification_write_has_a_deadline() -> None:
    writer = BlockingStreamWriter()
    _, _, transport = make_transport(default_timeout=0.01, writer=writer)

    with pytest.raises(JsonRpcWriteTimeoutError):
        await transport.notify({"jsonrpc": "2.0", "method": "blocked/notification"})

    assert transport.is_closed
    assert writer.closed


async def test_outgoing_non_finite_json_number_is_rejected() -> None:
    _, _, transport = make_transport()
    with pytest.raises(JsonRpcProtocolError, match="not JSON serializable"):
        await transport.notify({"jsonrpc": "2.0", "method": "invalid", "params": {"value": math.nan}})
    await transport.close()


async def test_incoming_non_finite_json_number_is_rejected() -> None:
    reader, _, transport = make_transport()
    request = asyncio.create_task(transport.request({"jsonrpc": "2.0", "id": 11, "method": "invalid"}))
    await asyncio.sleep(0)
    raw_body = b'{"jsonrpc":"2.0","id":11,"result":NaN}'
    reader.feed_data(f"Content-Length: {len(raw_body)}\r\n\r\n".encode("ascii") + raw_body)
    with pytest.raises(JsonRpcProtocolError, match="valid UTF-8 JSON"):
        await request
    assert transport.is_closed


async def test_malformed_content_length_fails_pending_request() -> None:
    reader, writer, transport = make_transport()
    request = asyncio.create_task(transport.request({"jsonrpc": "2.0", "id": 3, "method": "bad"}))
    await asyncio.sleep(0)
    reader.feed_data(b"Content-Length: nope\r\n\r\n")
    with pytest.raises(JsonRpcProtocolError, match="Invalid Content-Length"):
        await request
    assert transport.pending_request_count == 0
    await transport.close()
    assert writer.closed is True


async def test_nested_request_from_message_handler_does_not_block_reader() -> None:
    handler_started = asyncio.Event()
    handler_finished = asyncio.Event()
    transport: JsonRpcTransport

    async def handle_message(message: JsonRpcMessage) -> None:
        handler_started.set()
        response = await transport.request(
            {"jsonrpc": "2.0", "id": 2, "method": "client/nested"},
            timeout=0.2,
        )
        await transport.send_result(cast(int, message["id"]), response["result"])
        handler_finished.set()

    reader, writer, transport = make_transport(message_handler=handle_message)
    reader.feed_data(frame({"jsonrpc": "2.0", "id": 90, "method": "server/request"}))
    await asyncio.wait_for(handler_started.wait(), timeout=0.2)
    await asyncio.sleep(0)

    assert b'"method":"client/nested"' in writer.buffer
    reader.feed_data(frame({"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}))
    await asyncio.wait_for(handler_finished.wait(), timeout=0.2)
    assert b'"id":90,"result":{"ok":true}' in bytes(writer.buffer).lower()
    await transport.close()


async def test_inbound_message_handlers_have_bounded_concurrency_and_queue() -> None:
    handler_started = asyncio.Event()
    release_handler = asyncio.Event()

    async def blocked_handler(message: JsonRpcMessage) -> None:
        del message
        handler_started.set()
        await release_handler.wait()

    reader, _, transport = make_transport(
        message_handler=blocked_handler,
        max_queued_messages=2,
        message_worker_count=1,
    )
    reader.feed_data(frame({"jsonrpc": "2.0", "method": "test/flood", "params": {"index": 0}}))
    await asyncio.wait_for(handler_started.wait(), timeout=0.2)
    reader.feed_data(
        b"".join(
            frame({"jsonrpc": "2.0", "method": "test/flood", "params": {"index": index}}) for index in range(1, 20)
        )
    )

    with pytest.raises(JsonRpcProtocolError, match="queue is full"):
        await asyncio.wait_for(transport.wait_closed(), timeout=0.2)
    assert transport.message_handler_load <= 3
    release_handler.set()
    await transport.close()


async def test_close_finishes_when_handler_consumes_worker_cancellation() -> None:
    handler_started = asyncio.Event()

    async def cancellation_consuming_handler(message: JsonRpcMessage) -> None:
        del message
        handler_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return

    reader, _, transport = make_transport(
        default_timeout=0.1,
        message_handler=cancellation_consuming_handler,
        message_worker_count=1,
    )
    reader.feed_data(frame({"jsonrpc": "2.0", "method": "test/consume-cancellation"}))
    await asyncio.wait_for(handler_started.wait(), timeout=0.2)

    await asyncio.wait_for(transport.close(), timeout=0.2)
    assert all(worker.done() for worker in transport._message_workers)


@pytest.mark.parametrize(
    ("max_queued_messages", "message_worker_count"),
    [(0, 1), (1, 0)],
)
async def test_inbound_handler_bounds_must_be_positive(
    max_queued_messages: int,
    message_worker_count: int,
) -> None:
    reader = asyncio.StreamReader()
    with pytest.raises(ValueError, match="must be positive"):
        JsonRpcTransport(
            reader,
            cast(asyncio.StreamWriter, MemoryStreamWriter()),
            max_queued_messages=max_queued_messages,
            message_worker_count=message_worker_count,
        )


@pytest.mark.parametrize(
    "message",
    [
        {"id": 1, "result": None},
        {"jsonrpc": "1.0", "id": 1, "result": None},
        {"jsonrpc": "2.0", "id": 1, "result": None, "error": {"code": -1, "message": "bad"}},
        {"jsonrpc": "2.0", "id": 1, "error": {"code": "bad", "message": "bad"}},
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -1}},
    ],
)
async def test_invalid_jsonrpc_response_terminates_transport(message: dict[str, Any]) -> None:
    reader, writer, transport = make_transport()
    request = asyncio.create_task(transport.request({"jsonrpc": "2.0", "id": 1, "method": "test"}))
    await asyncio.sleep(0)
    reader.feed_data(frame(message))

    with pytest.raises(JsonRpcProtocolError):
        await request
    assert transport.is_closed
    assert transport.pending_request_count == 0
    assert writer.closed


@pytest.mark.parametrize("write_error", [BrokenPipeError(), OSError(5, "I/O error")])
async def test_write_failure_closes_transport_and_fails_all_pending_requests(write_error: Exception) -> None:
    writer = FailingStreamWriter()
    writer.write_error = write_error
    _, _, transport = make_transport(writer=writer)
    first = asyncio.create_task(transport.request({"jsonrpc": "2.0", "id": 1, "method": "first"}))
    await asyncio.sleep(0)
    assert transport.pending_request_count == 1

    writer.fail_writes = True
    with pytest.raises(LspSessionClosedError, match="closed while writing"):
        await transport.request({"jsonrpc": "2.0", "id": 2, "method": "second"})
    with pytest.raises(LspSessionClosedError, match="closed while writing"):
        await first

    assert transport.is_closed
    assert transport.pending_request_count == 0
    assert writer.closed
