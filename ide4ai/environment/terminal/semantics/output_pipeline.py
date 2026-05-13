"""
终端输出清洗管线 | Terminal output cleaning pipeline

分阶段清洗终端原始输出：
1. 剥离 CSI 序列（颜色/光标/样式）
2. 剥离 OSC 序列（窗口标题等；覆盖 BEL `\x07` 与 ST `\x1b\\` 两种终止符）
3. 剥离 OSC-133 shell integration markers（A/B/C/D）
4. 归一化回车/换行、裁切首尾空白

每个阶段独立可测，避免输出泄漏残留被下游（如退出码 regex）误匹配。
"""

from __future__ import annotations

import re

__all__ = [
    "clean_output",
    "strip_ansi_csi",
    "strip_ansi_osc",
    "strip_osc133",
]

# CSI: ESC [ ... letter / ESC @-_（老式单字符 C1）
# 覆盖 SGR 颜色、光标控制等。
_CSI_RE: re.Pattern[str] = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# OSC: ESC ] ... (BEL | ESC \)
# 宽松匹配；`.` 默认不匹配换行但 OSC 负载通常无换行，若存在 `re.DOTALL` 会吞掉后续输出。
_OSC_RE: re.Pattern[str] = re.compile(r"\x1B\].*?(?:\x07|\x1B\\)")

# OSC-133 shell integration markers 的子集：
# 正常情况下已被 _OSC_RE 命中；单独保留一条兜底，防止终止符缺失时的残留。
_OSC133_FALLBACK_RE: re.Pattern[str] = re.compile(r"\x1B\]133;[A-D](?:;[^\x07\x1B]*)?")

# CR 单独出现（非 CRLF）时，规范化成空串；CRLF 统一成 LF。
_CR_NOT_LF_RE: re.Pattern[str] = re.compile(r"\r(?!\n)")


def strip_ansi_csi(text: str) -> str:
    """
    剥离 CSI 序列（SGR 颜色、光标控制等）。

    Args:
        text: 原始文本 | Raw text

    Returns:
        已剥离 CSI 的文本 | Text with CSI sequences removed
    """
    return _CSI_RE.sub("", text)


def strip_ansi_osc(text: str) -> str:
    r"""
    剥离 OSC 序列，覆盖 BEL (`\x07`) 与 ST (`\x1B\\`) 两种终止符。

    AS-20 同源 Bug #1：当前实现只覆盖 CSI，OSC 残留（如 shell integration 发出的
    `\x1B]133;B\x07`）会污染输出，进而被下游退出码 regex `\d+` 误匹配成 133。

    Args:
        text: 原始文本 | Raw text

    Returns:
        已剥离 OSC 的文本 | Text with OSC sequences removed
    """
    return _OSC_RE.sub("", text)


def strip_osc133(text: str) -> str:
    r"""
    兜底剥离可能缺失终止符的 OSC-133 残留（`\x1B]133;A|B|C|D[;...]`）。

    正常情况下 `strip_ansi_osc` 已处理；此函数只在终止符异常丢失时兜底。

    Args:
        text: 原始文本 | Raw text

    Returns:
        已剥离 OSC-133 的文本 | Text with OSC-133 markers removed
    """
    return _OSC133_FALLBACK_RE.sub("", text)


def _normalize_newlines(text: str) -> str:
    """
    归一化换行：CRLF → LF；孤立 CR → 空。

    Args:
        text: 原始文本 | Raw text

    Returns:
        归一化后的文本 | Normalized text
    """
    text = text.replace("\r\n", "\n")
    return _CR_NOT_LF_RE.sub("", text)


def clean_output(raw: str) -> str:
    """
    分阶段清洗终端原始输出，返回可供 LLM / 断言消费的干净字符串。

    顺序：**OSC 先于 CSI**（OSC 以 `]` 开头，CSI 单字符 C1 类与 `]` 有范围重叠，
    先吃掉 OSC 整段避免残留）→ OSC-133 兜底 → 换行归一 → 首尾裁切。

    Args:
        raw: pexpect 抓到的原始输出 | Raw output captured by pexpect

    Returns:
        清洗后的输出 | Cleaned output
    """
    if not raw:
        return ""
    text = strip_ansi_osc(raw)
    text = strip_ansi_csi(text)
    text = strip_osc133(text)
    text = _normalize_newlines(text)
    return text.strip()
