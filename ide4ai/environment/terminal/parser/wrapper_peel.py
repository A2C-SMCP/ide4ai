"""
包装器剥离 | Wrapper peeling

剥离 `sudo/env/nice/timeout/stdbuf/nohup/time/bash -c/sh -c` 等包装器，
露出真实命令以供 policy 判定。

Epic A 范围：**只放 stub**。`peel_wrappers` 原样返回、wrappers 列表为空。
真正的 peel 逻辑（含 `bash -c "..."` 的递归解析）在 Epic B (AS-22 B4) 落地。
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "BARE_SHELL_PREFIXES",
    "peel_wrappers",
]


# 这些裸 shell / 包装器 / 提权命令：**绝不允许生成 `cmd:*` 前缀规则**，否则等于全放行。
# Epic A 先定义常量；Epic B 的 classifier 使用。
BARE_SHELL_PREFIXES: Final[frozenset[str]] = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "fish",
        "csh",
        "tcsh",
        "ksh",
        "dash",
        "cmd",
        "powershell",
        "pwsh",
        "env",
        "xargs",
        "nice",
        "stdbuf",
        "nohup",
        "timeout",
        "time",
        "sudo",
        "doas",
        "pkexec",
        "runuser",
    }
)


def peel_wrappers(tokens: list[str]) -> tuple[list[str], list[str]]:
    """
    剥离已知包装器，返回 (剥离掉的 wrappers, 剩余 tokens)。

    Epic A **只做 stub**：原样返回，wrappers=[]。真实剥离在 Epic B 实现。

    Args:
        tokens: 已剥离 env prefix 的 token 序列

    Returns:
        (wrappers, remaining_tokens)

    Examples:
        >>> peel_wrappers(["ls", "-la"])
        ([], ['ls', '-la'])
        >>> peel_wrappers(["sudo", "ls"])  # Epic A 仍原样返回
        ([], ['sudo', 'ls'])
    """
    return [], list(tokens)
