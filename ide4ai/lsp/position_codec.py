"""Conversions between Python code-point offsets and LSP character units."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ide4ai.lsp.errors import JsonRpcProtocolError

PositionEncoding: TypeAlias = Literal["utf-8", "utf-16"]


@dataclass(frozen=True, slots=True)
class PositionCodec:
    """Encode and decode the character component of an LSP position.

    Python indexes strings by Unicode code point. LSP positions instead count
    UTF-16 code units by default, or UTF-8 bytes when that encoding is
    negotiated. The input ``line_text`` must not contain a line terminator.
    """

    encoding: PositionEncoding = "utf-16"

    def __post_init__(self) -> None:
        if self.encoding not in ("utf-8", "utf-16"):
            raise ValueError(f"Unsupported LSP position encoding: {self.encoding}")

    def to_lsp_character(self, line_text: str, code_point_offset: int) -> int:
        """Convert a Python string offset to an LSP character offset."""
        if not 0 <= code_point_offset <= len(line_text):
            raise ValueError(f"Code-point offset {code_point_offset} is outside line bounds 0..{len(line_text)}")
        encoded = line_text[:code_point_offset].encode(self._python_encoding)
        return len(encoded) // self._unit_width

    def from_lsp_character(self, line_text: str, lsp_character: int) -> int:
        """Convert an LSP character offset to a Python string offset.

        Offsets in the middle of a multi-byte sequence or UTF-16 surrogate pair
        are invalid and rejected rather than silently rounded.
        """
        if lsp_character < 0:
            raise ValueError("LSP character offset cannot be negative")

        if lsp_character == 0:
            return 0

        current = 0
        for code_point_offset, character in enumerate(line_text, start=1):
            current += len(character.encode(self._python_encoding)) // self._unit_width
            if current == lsp_character:
                return code_point_offset
            if current > lsp_character:
                raise JsonRpcProtocolError(
                    f"LSP character offset {lsp_character} splits a character in {self.encoding} encoding"
                )

        if lsp_character > current:
            raise ValueError(f"LSP character offset {lsp_character} is outside line bounds 0..{current}")
        raise JsonRpcProtocolError(
            f"LSP character offset {lsp_character} splits a character in {self.encoding} encoding"
        )

    @property
    def _python_encoding(self) -> str:
        return "utf-16-le" if self.encoding == "utf-16" else "utf-8"

    @property
    def _unit_width(self) -> int:
        return 2 if self.encoding == "utf-16" else 1
