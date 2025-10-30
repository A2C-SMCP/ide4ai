# filename: server.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Server 主入口 | MCP Server Main Entry Point

实现 MCP 协议的服务器，封装 PythonIDE 的能力
Implements MCP protocol server, wrapping PythonIDE capabilities
"""

import asyncio
from typing import Any

from loguru import logger
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from ide4ai.ides import PyIDESingleton
from ide4ai.python_ide.mcp.config import MCPServerConfig
from ide4ai.python_ide.mcp.tools import BashTool
from ide4ai.python_ide.mcp.tools.base import BaseTool


class PythonIDEMCPServer:
    """
    Python IDE MCP Server

    封装 PythonIDE 为 MCP Server，提供工具和资源
    Wraps PythonIDE as MCP Server, providing tools and resources
    """

    def __init__(self, config: MCPServerConfig) -> None:
        """
        初始化 MCP Server | Initialize MCP Server

        Args:
            config: MCP Server 配置 | MCP Server configuration
        """
        self.config = config
        self.server = Server("python-ide-mcp")

        # 使用 PyIDESingleton 获取 IDE 实例 | Get IDE instance using PyIDESingleton
        ide_singleton = PyIDESingleton(**config.to_ide_kwargs())
        self.ide = ide_singleton.ide

        # 初始化工具列表 | Initialize tools list
        self.tools: dict[str, BaseTool] = {}

        # 注册工具 | Register tools
        self._register_tools()

        # 设置 MCP 处理器 | Setup MCP handlers
        self._setup_handlers()

        logger.info(
            f"Python IDE MCP Server 初始化完成 | Python IDE MCP Server initialized: project={config.project_name}, root={config.root_dir}",
        )

    def _register_tools(self) -> None:
        """
        注册所有工具 | Register all tools
        """
        # 注册 Bash 工具 | Register Bash tool
        bash_tool = BashTool(self.ide)
        self.tools[bash_tool.name] = bash_tool

        logger.info(f"已注册工具 | Registered tools: {list(self.tools.keys())}")

        # TODO: 注册其他工具 | Register other tools
        # - GlobTool
        # - GrepTool
        # - ReadTool
        # - EditTool
        # - WriteTool

    def _setup_handlers(self) -> None:
        """
        设置 MCP 协议处理器 | Setup MCP protocol handlers
        """

        @self.server.list_tools()  # type: ignore[no-untyped-call]
        async def list_tools() -> list[Tool]:
            """
            列出所有可用工具 | List all available tools

            Returns:
                list[Tool]: 工具列表 | List of tools
            """
            tools = []
            for tool in self.tools.values():
                tools.append(
                    Tool(
                        name=tool.name,
                        description=tool.description,
                        inputSchema=tool.input_schema,
                    ),
                )

            logger.debug(f"列出工具 | Listed tools: {[t.name for t in tools]}")
            return tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
            """
            调用工具 | Call tool

            Args:
                name: 工具名称 | Tool name
                arguments: 工具参数 | Tool arguments

            Returns:
                list[dict]: 工具执行结果 | Tool execution result
            """
            logger.info(f"调用工具 | Calling tool: {name}")

            # 查找工具 | Find tool
            tool = self.tools.get(name)
            if not tool:
                error_msg = f"未找到工具 | Tool not found: {name}"
                logger.error(error_msg)
                return [{"type": "text", "text": error_msg}]

            try:
                # 执行工具 | Execute tool
                result = await tool.execute(arguments)

                # 格式化返回结果 | Format return result
                return [
                    {
                        "type": "text",
                        "text": str(result),
                    },
                ]

            except Exception as e:
                error_msg = f"工具执行失败 | Tool execution failed: {e}"
                logger.exception(error_msg)
                return [{"type": "text", "text": error_msg}]

    async def run(self) -> None:
        """
        运行 MCP Server | Run MCP Server

        使用 stdio 传输协议
        Uses stdio transport protocol
        """
        logger.info("启动 MCP Server | Starting MCP Server...")

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


async def main() -> None:
    """
    主函数 | Main function

    示例：如何启动 MCP Server
    Example: How to start MCP Server
    """
    # 创建配置 | Create configuration
    config = MCPServerConfig(
        cmd_white_list=["ls", "pwd", "echo", "cat", "grep"],  # 示例白名单 | Example whitelist
        root_dir=".",
        project_name="example-project",
    )

    # 创建并运行 server | Create and run server
    server = PythonIDEMCPServer(config)
    await server.run()


if __name__ == "__main__":
    # 运行 server | Run server
    asyncio.run(main())
