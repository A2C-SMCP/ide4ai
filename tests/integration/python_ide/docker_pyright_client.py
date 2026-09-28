"""Bounded TCP acceptance probe using the production JSON-RPC transport."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from ide4ai.lsp.errors import JsonRpcProtocolError, LspError
from ide4ai.lsp.transport import JsonRpcTransport


class PyrightUnavailable(RuntimeError):
    """The optional endpoint did not complete a Pyright handshake."""


async def check_pyright_endpoint(host: str, port: int, *, timeout: float = 3.0) -> dict[str, Any]:
    """Identify and shut down Pyright within four timeout periods.

    Unavailable/mismatched endpoints can be skipped by optional Docker tests.
    Once identified as Pyright, shutdown failures remain test failures.
    Connect, initialize, shutdown, and cleanup each have a bounded deadline.
    """
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, asyncio.TimeoutError) as exc:
        raise PyrightUnavailable(f"Cannot connect to {host}:{port}: {exc}") from exc
    identified = asyncio.Event()

    async def handle_message(message: dict[str, Any]) -> None:
        params = message.get("params")
        if message.get("method") == "window/logMessage" and isinstance(params, dict):
            if re.fullmatch(r"Pyright language server [0-9.]+ starting", str(params.get("message", ""))):
                identified.set()

    transport = JsonRpcTransport(
        reader, writer, message_handler=handle_message, default_timeout=timeout, cleanup_timeout=timeout
    )
    transport.start()
    try:
        try:
            deadline = asyncio.get_running_loop().time() + timeout
            response = await transport.request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"processId": None, "rootUri": "file:///app", "capabilities": {}},
                }
            )
            result = response.get("result")
            if isinstance(result, dict) and isinstance(result.get("serverInfo"), dict):
                if str(result["serverInfo"].get("name", "")).lower() == "pyright":
                    identified.set()
            if not isinstance(result, dict) or not isinstance(result.get("capabilities"), dict):
                raise JsonRpcProtocolError("Endpoint did not return LSP initialize capabilities")
            info = result.get("serverInfo", {})
            provider = result["capabilities"].get("executeCommandProvider", {})
            commands = provider.get("commands", []) if isinstance(provider, dict) else []
            name = info.get("name", "") if isinstance(info, dict) else ""
            if not isinstance(commands, list):
                commands = []
            if str(name).lower() != "pyright" and not any(
                isinstance(command, str) and command.startswith("pyright.") for command in commands
            ):
                # Released Pyright versions can omit serverInfo and expose no
                # commands. Their startup notification provides the identity.
                await asyncio.wait_for(identified.wait(), max(0.0, deadline - asyncio.get_running_loop().time()))
        except (LspError, OSError, asyncio.TimeoutError) as exc:
            if identified.is_set():
                raise
            raise PyrightUnavailable(f"Pyright handshake failed at {host}:{port}: {exc}") from exc

        async def shutdown() -> None:
            await transport.notify({"jsonrpc": "2.0", "method": "initialized", "params": {}})
            response = await transport.request({"jsonrpc": "2.0", "id": 2, "method": "shutdown"})
            assert response["result"] is None
            await transport.notify({"jsonrpc": "2.0", "method": "exit"})

        await asyncio.wait_for(shutdown(), timeout)
        return result
    finally:
        await transport.close()
