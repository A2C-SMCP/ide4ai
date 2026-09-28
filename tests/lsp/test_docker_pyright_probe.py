"""Real TCP regressions for optional Docker readiness and bounded cleanup."""

import asyncio
import json

import pytest

from ide4ai.lsp.errors import LspError
from tests.integration.python_ide.docker_pyright_client import PyrightUnavailable, check_pyright_endpoint


async def read_frame(reader):
    header = await reader.readuntil(b"\r\n\r\n")
    length = int(header.split(b":", 1)[1].strip())
    return json.loads(await reader.readexactly(length))


async def send_frame(writer, message):
    body = json.dumps(message).encode()
    writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    await writer.drain()


@pytest.mark.parametrize(
    "mode",
    [
        "eof",
        "http",
        "silent",
        "other-lsp",
        "pyright",
        "shutdown-silent",
        "identified-eof",
        "identified-silent",
        "identified-error",
        "identified-malformed",
    ],
)
@pytest.mark.timeout(5)
async def test_probe_uses_protocol_identity_and_releases_connection(mode):
    disconnected = asyncio.Event()
    received = []

    async def peer(reader, writer):
        try:
            received.append(await read_frame(reader))
            if mode.startswith("identified-"):
                await send_frame(
                    writer,
                    {
                        "jsonrpc": "2.0",
                        "method": "window/logMessage",
                        "params": {"message": "Pyright language server 1.1.400 starting"},
                    },
                )
                if mode == "identified-eof":
                    return
                if mode == "identified-error":
                    await send_frame(
                        writer, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "initialize failed"}}
                    )
                if mode == "identified-malformed":
                    await send_frame(writer, {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": None}})
                assert await reader.read() == b""
                return
            if mode == "eof":
                return
            if mode == "http":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
            elif mode != "silent":
                await send_frame(
                    writer,
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "capabilities": {},
                            "serverInfo": {"name": "other" if mode == "other-lsp" else "Pyright"},
                        },
                    },
                )
                if mode in {"pyright", "shutdown-silent"}:
                    received.append(await read_frame(reader))
                    received.append(await read_frame(reader))
                    if mode == "pyright":
                        await send_frame(writer, {"jsonrpc": "2.0", "id": 2, "result": None})
                        received.append(await read_frame(reader))
            assert await reader.read() == b""
        finally:
            writer.close()
            await writer.wait_closed()
            disconnected.set()

    server = await asyncio.start_server(peer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        if mode == "pyright":
            result = await check_pyright_endpoint("127.0.0.1", port, timeout=0.2)
            assert result["serverInfo"]["name"] == "Pyright"
            assert [message["method"] for message in received] == ["initialize", "initialized", "shutdown", "exit"]
        elif mode.startswith("identified-"):
            with pytest.raises(LspError):
                await check_pyright_endpoint("127.0.0.1", port, timeout=0.2)
        elif mode == "shutdown-silent":
            with pytest.raises(TimeoutError):
                await check_pyright_endpoint("127.0.0.1", port, timeout=0.2)
        else:
            with pytest.raises(PyrightUnavailable):
                await check_pyright_endpoint("127.0.0.1", port, timeout=0.2)
        await asyncio.wait_for(disconnected.wait(), 1)
        assert not [task for task in asyncio.all_tasks() if task.get_name().startswith("ide4ai-jsonrpc")]
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.timeout(20)
async def test_probe_accepts_real_pyright_over_tcp(tmp_path):
    """A real stdio Pyright behind a TCP bridge validates the identification contract."""
    closed = asyncio.Event()
    errors = []

    async def peer(reader, writer):
        process = await asyncio.create_subprocess_exec(
            "pyright-langserver",
            "--stdio",
            cwd=tmp_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async def copy(source, target):
            while data := await source.read(65536):
                target.write(data)
                await target.drain()

        upstream = asyncio.create_task(copy(reader, process.stdin))
        downstream = asyncio.create_task(copy(process.stdout, writer))
        try:
            await asyncio.wait_for(process.wait(), 10)
            assert process.returncode == 0
        except BaseException as exc:
            errors.append(exc)
        finally:
            upstream.cancel()
            downstream.cancel()
            await asyncio.gather(upstream, downstream, return_exceptions=True)
            if process.returncode is None:
                process.kill()
                await process.wait()
            writer.close()
            await writer.wait_closed()
            closed.set()

    server = await asyncio.start_server(peer, "127.0.0.1", 0)
    try:
        result = await check_pyright_endpoint("127.0.0.1", server.sockets[0].getsockname()[1], timeout=5)
        assert result["capabilities"]["documentSymbolProvider"]
        await asyncio.wait_for(closed.wait(), 10)
        assert not errors
    finally:
        server.close()
        await server.wait_closed()
