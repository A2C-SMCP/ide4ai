"""Small stdio JSON-RPC peer used by LspSession process tests."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line == b"\r\n":
            break
        name, value = line.decode("ascii").split(":", 1)
        headers[name.lower()] = value.strip()
    body = sys.stdin.buffer.read(int(headers["content-length"]))
    return cast(dict[str, Any], json.loads(body.decode("utf-8")))


def write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()


def main() -> int:
    marker_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    position_encoding = sys.argv[2] if len(sys.argv) > 2 else "utf-16"
    while message := read_message():
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"capabilities": {"positionEncoding": position_encoding}},
                }
            )
        elif method == "initialized":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": "server-request",
                    "method": "workspace/configuration",
                    "params": {"items": []},
                }
            )
        elif method == "test/echo":
            write_message({"jsonrpc": "2.0", "id": request_id, "result": message.get("params")})
        elif method == "test/never":
            continue
        elif method == "test/crash":
            return 7
        elif method == "test/notifications":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/publishDiagnostics",
                    "params": {"uri": "file:///b.py", "diagnostics": []},
                }
            )
            write_message(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/publishDiagnostics",
                    "params": {"uri": "file:///a.py", "diagnostics": []},
                }
            )
            write_message({"jsonrpc": "2.0", "id": request_id, "result": None})
        elif method == "test/notification-updates":
            for version in (1, 2):
                write_message(
                    {
                        "jsonrpc": "2.0",
                        "method": "textDocument/publishDiagnostics",
                        "params": {"uri": "file:///latest.py", "version": version, "diagnostics": []},
                    }
                )
            write_message({"jsonrpc": "2.0", "id": request_id, "result": None})
        elif method == "test/uri-less-notification":
            write_message(
                {
                    "jsonrpc": "2.0",
                    "method": "window/logMessage",
                    "params": {"type": 3, "message": "ready"},
                }
            )
            write_message({"jsonrpc": "2.0", "id": request_id, "result": None})
        elif method == "test/large-stderr":
            sys.stderr.buffer.write(b"x" * (256 * 1024))
            sys.stderr.buffer.flush()
            write_message({"jsonrpc": "2.0", "id": request_id, "result": "drained"})
        elif method == "test/close-stdout":
            os.close(sys.stdout.fileno())
            time.sleep(1.0)
            return 9
        elif method == "shutdown":
            write_message({"jsonrpc": "2.0", "id": request_id, "result": None})
        elif method == "exit":
            if marker_path is not None:
                marker_path.write_text("exit", encoding="utf-8")
            return 0
        elif request_id == "server-request":
            if "result" in message:
                write_message(
                    {
                        "jsonrpc": "2.0",
                        "method": "test/nested-complete",
                        "params": message["result"],
                    }
                )
            elif "error" not in message or message["error"].get("code") != -32601:
                return 8
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
