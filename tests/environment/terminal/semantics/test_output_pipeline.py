"""
semantics/output_pipeline.py 单元测试 | Unit tests for semantics/output_pipeline.py

对应 Jira AS-30 (Epic A · A4)；守住 AS-20 同源 Bug #1 的回归底线。
"""

from __future__ import annotations

import pytest

from ide4ai.environment.terminal.semantics.output_pipeline import (
    clean_output,
    strip_ansi_csi,
    strip_ansi_osc,
    strip_osc133,
)


class TestStripAnsiCsi:
    """CSI 序列（颜色、光标控制）剥离 | Strip CSI (colors, cursor)"""

    def test_plain_text_unchanged(self) -> None:
        assert strip_ansi_csi("hello world") == "hello world"

    def test_sgr_color_stripped(self) -> None:
        assert strip_ansi_csi("\x1b[31mRED\x1b[0m") == "RED"

    def test_cursor_movement_stripped(self) -> None:
        assert strip_ansi_csi("a\x1b[2Ab") == "ab"

    def test_empty_string(self) -> None:
        assert strip_ansi_csi("") == ""


class TestStripAnsiOsc:
    """OSC 序列剥离 | Strip OSC sequences

    覆盖 BEL (`\\x07`) 与 ST (`\\x1B\\`) 两种终止符；
    这是 AS-20 同源 Bug #1 的核心。
    """

    def test_osc_with_bel_terminator(self) -> None:
        """`\\x1B]0;title\\x07rest` → `rest`"""
        assert strip_ansi_osc("\x1b]0;window title\x07visible") == "visible"

    def test_osc_with_st_terminator(self) -> None:
        """`\\x1B]0;title\\x1B\\rest` → `rest`"""
        assert strip_ansi_osc("\x1b]0;window title\x1b\\visible") == "visible"

    def test_osc133_shell_integration_bel(self) -> None:
        """AS-20 的关键用例：`\\x1B]133;B\\x07` 必须被移除。"""
        raw = "\x1b]133;A\x07\x1b]133;B\x07output\x1b]133;D;0\x07"
        assert strip_ansi_osc(raw) == "output"

    def test_multiple_osc_sequences(self) -> None:
        raw = "\x1b]0;t1\x07a\x1b]0;t2\x07b"
        assert strip_ansi_osc(raw) == "ab"

    def test_plain_text_unchanged(self) -> None:
        assert strip_ansi_osc("hello") == "hello"

    def test_empty_string(self) -> None:
        assert strip_ansi_osc("") == ""


class TestStripOsc133Fallback:
    """OSC-133 兜底剥离：当终止符丢失时仍能清理 | Fallback strip when terminator missing"""

    def test_osc133_no_terminator(self) -> None:
        """`\\x1B]133;B` 无终止符时兜底移除。"""
        assert strip_osc133("\x1b]133;B") == ""

    def test_osc133_a_with_extra(self) -> None:
        assert strip_osc133("\x1b]133;A;path=/tmp") == ""

    def test_non_133_osc_unchanged(self) -> None:
        """非 133 的 OSC 不碰（交给 strip_ansi_osc）。"""
        assert "\x1b]0;t" in strip_osc133("\x1b]0;t")

    def test_plain_text_unchanged(self) -> None:
        assert strip_osc133("hello") == "hello"


class TestCleanOutput:
    """完整清洗管线 | Full cleaning pipeline"""

    def test_empty_input(self) -> None:
        assert clean_output("") == ""

    def test_plain_text(self) -> None:
        assert clean_output("total 8\nfile1\nfile2") == "total 8\nfile1\nfile2"

    def test_as20_regression_full_pipeline(self) -> None:
        """AS-20 场景的完整回归测试。

        pexpect 捕获到的原始输出同时包含 CSI（颜色）和 OSC-133（shell integration）。
        清洗后应只留下 `ls -la /home` 的真实目录列表输出。
        """
        raw = (
            "\x1b]133;C\x07"
            "\x1b[0;34mtotal 0\x1b[0m\r\n"
            "drwxr-xr-x  2 root root  40 Apr 22 10:00 \x1b[1;34m.\x1b[0m\r\n"
            "drwxr-xr-x 18 root root 420 Apr 22 09:59 \x1b[1;34m..\x1b[0m\r\n"
            "\x1b]133;D;0\x07"
        )
        out = clean_output(raw)
        assert "\x1b" not in out
        assert "\r" not in out
        assert "133" not in out  # 关键：不能把 OSC-133 的数字 133 泄露出来
        assert "total 0" in out
        assert "drwxr-xr-x" in out

    def test_cr_only_normalized(self) -> None:
        """孤立 CR 去除；CRLF 转 LF。"""
        assert clean_output("a\r\nb\rc") == "a\nbc"

    def test_preserves_inner_whitespace(self) -> None:
        assert clean_output("  leading\ninner  space\ntrailing  ") == "leading\ninner  space\ntrailing"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\x1b[31mhello\x1b[0m", "hello"),
        ("\x1b]0;title\x07real output", "real output"),
        ("prefix\x1b]133;A\x07\x1b]133;B\x07body\x1b]133;D;0\x07suffix", "prefixbodysuffix"),
        ("", ""),
        ("no escapes at all", "no escapes at all"),
    ],
)
def test_clean_output_parametric(raw: str, expected: str) -> None:
    assert clean_output(raw) == expected
