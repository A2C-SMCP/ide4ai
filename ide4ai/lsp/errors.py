"""Structured errors raised by the LSP transport and session layers."""

from __future__ import annotations

from typing import Any


class LspError(RuntimeError):
    """Base class for LSP client failures."""


class JsonRpcProtocolError(LspError):
    """Raised when a peer sends malformed JSON-RPC framing or payloads."""


class JsonRpcTimeoutError(LspError, TimeoutError):
    """Raised when a JSON-RPC request does not complete before its deadline."""

    def __init__(self, request_id: int | str, timeout: float) -> None:
        self.request_id = request_id
        self.timeout = timeout
        super().__init__(f"JSON-RPC request {request_id!r} timed out after {timeout:.3f}s")


class JsonRpcWriteTimeoutError(LspError, TimeoutError):
    """Raised when a JSON-RPC frame cannot be written before its deadline."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        super().__init__(f"JSON-RPC write timed out after {timeout:.3f}s")


class JsonRpcRequestError(LspError):
    """Raised when a JSON-RPC response contains an error object."""

    def __init__(self, request_id: int | str | None, code: int, message: str, data: Any = None) -> None:
        self.request_id = request_id
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"JSON-RPC request {request_id!r} failed ({code}): {message}")


class LspProcessExitedError(LspError):
    """Raised when the language server exits while requests are pending."""

    def __init__(self, returncode: int | None) -> None:
        self.returncode = returncode
        super().__init__(f"Language server process exited unexpectedly with code {returncode}")


class LspSessionClosedError(LspError):
    """Raised when an operation is attempted on a closed session."""
