"""Language Server Protocol transport and session primitives."""

from ide4ai.lsp.diagnostics import DiagnosticsRegistry
from ide4ai.lsp.errors import (
    JsonRpcProtocolError,
    JsonRpcRequestError,
    JsonRpcTimeoutError,
    JsonRpcWriteTimeoutError,
    LspProcessExitedError,
    LspSessionClosedError,
)
from ide4ai.lsp.manager import (
    LanguageProfile,
    LanguageRegistry,
    LspManager,
    LspServerSpec,
    LspSettings,
    LspState,
    LspStatus,
)
from ide4ai.lsp.position_codec import PositionCodec, PositionEncoding
from ide4ai.lsp.session import LspSession
from ide4ai.lsp.transport import JsonRpcTransport

__all__ = [
    "DiagnosticsRegistry",
    "JsonRpcProtocolError",
    "JsonRpcRequestError",
    "JsonRpcTimeoutError",
    "JsonRpcWriteTimeoutError",
    "JsonRpcTransport",
    "LspProcessExitedError",
    "LanguageProfile",
    "LanguageRegistry",
    "LspManager",
    "LspServerSpec",
    "LspSettings",
    "LspState",
    "LspStatus",
    "LspSession",
    "LspSessionClosedError",
    "PositionCodec",
    "PositionEncoding",
]
