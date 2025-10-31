# filename: bash.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
Bash 工具实现 | Bash Tool Implementation

提供在 IDE 环境中执行 Bash 命令的能力
Provides the ability to execute Bash commands in the IDE environment
"""

from typing import Any

from loguru import logger

from ide4ai.python_ide.mcp.schemas.tools import BashInput, BashOutput
from ide4ai.python_ide.mcp.tools.base import BaseTool


class BashTool(BaseTool):
    """
    Bash 命令执行工具 | Bash Command Execution Tool

    通过 PythonIDE 的终端环境执行 Bash 命令
    Executes Bash commands through PythonIDE's terminal environment
    """

    @property
    def name(self) -> str:
        return "Bash"

    @property
    def description(self) -> str:
        return (
            "在 IDE 环境中执行 Bash 命令 | Execute Bash commands in the IDE environment\n\n"
            "功能特性 | Features:\n"
            "- 支持命令白名单控制 | Supports command whitelist control\n"
            "- 可配置超时时间 | Configurable timeout\n"
            "- 支持后台运行 | Supports background execution\n"
            "- 自动捕获输出和错误 | Automatically captures output and errors\n\n"
            "使用场景 | Use Cases:\n"
            "- 运行测试命令 | Run test commands\n"
            "- 执行构建脚本 | Execute build scripts\n"
            "- 查看文件系统 | View file system\n"
            "- 管理进程 | Manage processes"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        """返回 JSON Schema 格式的输入定义 | Return input definition in JSON Schema format"""
        return BashInput.model_json_schema()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        执行 Bash 命令 | Execute Bash command

        Args:
            arguments: 包含命令和选项的参数字典 | Arguments dict containing command and options

        Returns:
            dict: 执行结果，包含输出、错误信息等 | Execution result with output, errors, etc.
        """
        # 验证输入参数 | Validate input arguments
        try:
            bash_input = self.validate_input(arguments, BashInput)
        except ValueError as e:
            err_info = f"参数验证失败 | Argument validation failed: {e}"
            logger.error(err_info)
            return BashOutput(
                success=False,
                output="",
                error=err_info,
                exit_code=1,
            ).model_dump()

        logger.info(f"执行 Bash 命令 | Executing Bash command: {bash_input.command}")

        try:
            # 构造 IDE action
            # action_args 必须是 str 或 list[str]，不能是 dict
            # action_args must be str or list[str], not dict
            action = {
                "category": "terminal",
                "action_name": bash_input.command,
                "action_args": bash_input.args
                if bash_input.args is not None
                else "",  # 使用传入的 args 或空字符串 | Use provided args or empty string
            }

            # 如果设置了超时，转换为秒 | Convert timeout to seconds if set
            if bash_input.timeout:
                # IDE 的 timeout 是秒，MCP 的是毫秒 | IDE timeout is in seconds, MCP is in milliseconds
                timeout_seconds = bash_input.timeout / 1000
                # 注意：这里可能需要根据实际的 IDE 实现来调整超时设置
                # Note: May need to adjust timeout setting based on actual IDE implementation
                logger.debug(f"设置超时 | Setting timeout: {timeout_seconds}s")

            # 执行命令 | Execute command
            obs, reward, done, success, info = self.ide.step(action)

            # 构造输出 | Construct output
            output = BashOutput(
                success=bool(success),
                output=str(obs.get("obs", "")),
                error=str(obs.get("error", "")) if "error" in obs else None,
                exit_code=info.get("exit_code"),
                metadata={
                    "reward": float(reward),
                    "done": done,
                    "description": bash_input.description,
                    "run_in_background": bash_input.run_in_background,
                },
            )

            logger.info(
                f"命令执行完成 | Command execution completed: success={output.success}, exit_code={output.exit_code}",
            )

            return output.model_dump()

        except Exception as e:
            logger.exception(f"执行命令时发生错误 | Error executing command: {e}")

            # 返回错误结果 | Return error result
            error_output = BashOutput(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                metadata={"exception_type": type(e).__name__},
            )

            return error_output.model_dump()
