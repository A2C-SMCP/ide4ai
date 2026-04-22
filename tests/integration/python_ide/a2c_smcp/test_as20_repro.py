"""
AS-20 端到端回归测试 | AS-20 end-to-end regression test

守住 Epic A 的底线——CommandFilter + PexpectTerminalEnv 完整链路能处理
`ls -la /home` 这类带参数命令，不再误拦截、退出码正确、info 字段齐全。

对应 Jira AS-34 (Epic A · A8)。
"""

from __future__ import annotations

import warnings
from collections.abc import Generator
from typing import Any

import pytest

from ide4ai.a2c_smcp.tools import BashTool
from ide4ai.environment.terminal.command_filter import CommandFilterConfig
from ide4ai.python_ide.ide import PythonIDE


@pytest.fixture
def ide_with_whitelist(tmp_path) -> Generator[PythonIDE, Any, None]:
    """
    AS-20 repro 场景：启动 IDE 时传入 `["ls", "pwd", "echo", "cat"]` 白名单。
    Before fix：带参数命令被拦截；After fix：放行。
    """
    ide = PythonIDE(
        root_dir=str(tmp_path),
        project_name="as20-repro",
        cmd_filter=CommandFilterConfig.from_white_list(
            ["ls", "pwd", "echo", "cat", "grep", "find", "head", "tail", "wc"]
        ),
        cmd_time_out=5,
    )
    yield ide
    ide.close()


@pytest.fixture
def bash_tool(ide_with_whitelist):
    return BashTool(ide_with_whitelist)


@pytest.mark.asyncio
async def test_ls_with_args_passes_whitelist(bash_tool, tmp_path) -> None:
    """AS-20 核心 repro：`ls -la` 带参数时不再被误拦截。"""
    # 在 tmp_path 下建几个文件以便 ls 有东西可列
    (tmp_path / "file_a.txt").write_text("a")
    (tmp_path / "file_b.txt").write_text("b")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = await bash_tool.execute(
            {
                "command": "ls",
                "args": "-la",
                "description": "AS-20 repro",
            }
        )

    # 核心断言：不再被拒
    assert result["success"] is True, f"AS-20 regression: got {result}"
    # 退出码必须非 None 且等于 0（原 Bug 中为 None 或 -1）
    assert result["exit_code"] == 0
    # 输出包含我们刚建的文件名
    assert "file_a.txt" in result["output"]
    assert "file_b.txt" in result["output"]
    # 不应再有 OSC-133 的数字泄漏到输出里
    assert "\x1b" not in result["output"]


@pytest.mark.asyncio
async def test_ls_full_command_as_single_string(bash_tool, tmp_path) -> None:
    """LLM 若把整条命令塞在 command 字段（不拆 args），也应放行。"""
    (tmp_path / "only.txt").write_text("x")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = await bash_tool.execute({"command": "ls -la", "description": "whole string"})

    assert result["success"] is True, f"AS-20 regression: got {result}"
    assert result["exit_code"] == 0
    assert "only.txt" in result["output"]


@pytest.mark.asyncio
async def test_info_fields_populated(bash_tool) -> None:
    """AS-32 A6：`metadata` 应包含 cwd / duration_ms；`exit_code` 非 None。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = await bash_tool.execute({"command": "pwd", "description": "check metadata"})

    assert result["exit_code"] is not None
    meta = result["metadata"]
    assert meta.get("cwd"), "cwd should be non-empty after AS-32 A6"
    assert isinstance(meta.get("duration_ms"), int)
    assert meta["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_non_whitelisted_still_rejected(bash_tool) -> None:
    """回归：不在白名单的命令（如 `rm`）仍然必须被拒。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = await bash_tool.execute({"command": "rm", "args": "-rf /", "description": "must reject"})

    # 拒绝路径：success=False，error 不为空
    assert result["success"] is False
    assert result.get("error") is not None
