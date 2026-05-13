"""
终端执行层 | Terminal execution layer

`StepResult` 值对象 + 未来的 `BackgroundTaskManager`（Epic E）。

Epic A 只引入 `StepResult`；`PexpectTerminalEnv` 仍在原位置。
"""

from ide4ai.environment.terminal.execution.run_result import StepResult

__all__ = ["StepResult"]
