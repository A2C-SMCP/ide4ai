from __future__ import annotations

import pytest

from ide4ai.lsp.errors import JsonRpcProtocolError
from ide4ai.lsp.position_codec import PositionCodec


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_ascii_offsets_are_unchanged(encoding: str) -> None:
    codec = PositionCodec(encoding)  # type: ignore[arg-type]
    assert codec.to_lsp_character("hello", 3) == 3
    assert codec.from_lsp_character("hello", 3) == 3


def test_utf8_counts_encoded_bytes() -> None:
    codec = PositionCodec("utf-8")
    line = "a😀中"
    assert codec.to_lsp_character(line, 2) == 5
    assert codec.to_lsp_character(line, 3) == 8
    assert codec.from_lsp_character(line, 5) == 2


def test_utf16_counts_surrogate_pairs() -> None:
    codec = PositionCodec("utf-16")
    line = "a😀中"
    assert codec.to_lsp_character(line, 2) == 3
    assert codec.to_lsp_character(line, 3) == 4
    assert codec.from_lsp_character(line, 3) == 2


@pytest.mark.parametrize(
    ("codec", "invalid_offset"),
    [(PositionCodec("utf-8"), 2), (PositionCodec("utf-16"), 2)],
)
def test_decode_rejects_offset_inside_character(codec: PositionCodec, invalid_offset: int) -> None:
    with pytest.raises(JsonRpcProtocolError, match="splits a character"):
        codec.from_lsp_character("a😀", invalid_offset)


def test_codec_rejects_out_of_bounds_offsets() -> None:
    codec = PositionCodec("utf-16")
    with pytest.raises(ValueError, match="outside line bounds"):
        codec.to_lsp_character("abc", 4)
    with pytest.raises(ValueError, match="outside line bounds"):
        codec.from_lsp_character("abc", 4)


def test_codec_rejects_unknown_encoding() -> None:
    with pytest.raises(ValueError, match="Unsupported LSP position encoding"):
        PositionCodec("utf-32")  # type: ignore[arg-type]
