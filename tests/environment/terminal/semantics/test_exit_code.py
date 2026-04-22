"""
semantics/exit_code 占位测试 | Placeholder tests for semantics/exit_code

Epic A 范围不实现 per-command is_error 映射——那是 Epic C (AS-23) 的工作。
本文件保留，确保后续加入 exit_code.py 时目录已经 ready。
"""

from __future__ import annotations


def test_semantics_package_importable() -> None:
    """Epic A 只保证 semantics 包可 import，具体模块逐步填充。"""
    import ide4ai.environment.terminal.semantics as pkg  # noqa: F401
