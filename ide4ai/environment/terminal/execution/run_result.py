"""
StepResult —— 终端单次 step 的结构化结果 | Structured single-step result

解决 AS-20 同源 Bug #3：`step()` 返回 `info={}` 缺字段，导致 MCP 层拿不到
`exit_code`。本类定义标准化字段，`PexpectTerminalEnv.step()` 在返回时把实例
`asdict()` 后填入 `info`。

Epic A 字段：`exit_code / success / output / truncated / cwd / duration_ms`；
Epic B 会加 `decision: PolicyDecision`；Epic C 加 `is_error`；Epic E 加 `task_id`。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = ["StepResult"]


@dataclass(slots=True)
class StepResult:
    """
    终端命令执行的结构化结果。

    Attributes:
        exit_code: 真实退出码 | Real exit code（来自 pexpect 定界符协议，不再 regex）
        success: `exit_code == 0`（Epic C 会与 `is_error` 分离）
        output: 清洗后的命令输出 | Cleaned command output
        truncated: 输出是否在返回前被截断 | Whether output was truncated before return
        cwd: 执行后的工作目录 | Working directory after execution
        duration_ms: 执行耗时（毫秒）| Execution duration in ms
        original_length: 原始输出长度（truncated=True 时有意义）
    """

    exit_code: int
    success: bool
    output: str
    truncated: bool = False
    cwd: str = ""
    duration_ms: int = 0
    original_length: int | None = None
    # 预留字段（Epic B/C/E 使用）
    extra: dict[str, Any] = field(default_factory=dict)

    def to_info(self) -> dict[str, Any]:
        """
        转换为 gym `step()` 的 `info` 字典（扁平化；`extra` 并入顶层）。

        Returns:
            info 字典 | info dict
        """
        d = asdict(self)
        extra = d.pop("extra") or {}
        # `extra` 的 key 不与 StepResult 顶层字段冲突
        for k, v in extra.items():
            d.setdefault(k, v)
        return d
