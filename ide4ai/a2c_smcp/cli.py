# filename: server.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""Concrete project-aware IDE MCP server."""

import argparse
import sys

from loguru import logger

from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.projects import (
    ProjectHost,
    ProjectRegistry,
    ProjectTerminalRuntimeManager,
    create_ide_factory,
)
from ide4ai.a2c_smcp.providers import (
    IDEToolProvider,
    ProjectToolProvider,
    TerminalToolProvider,
    TFBashResourceProvider,
    TFBashToolProvider,
    WindowResourceProvider,
)
from ide4ai.a2c_smcp.server import BaseMCPServer
from ide4ai.a2c_smcp.tools import EditTool, GlobTool, GrepTool, LspTool, ReadTool, WriteTool


def _build_argument_parser() -> argparse.ArgumentParser:
    """Define the complete supported CLI surface in one fail-fast parser."""
    parser = argparse.ArgumentParser(
        prog="ide4ai-mcp",
        description="Expose an ide4ai workspace through the Model Context Protocol.",
    )
    parser.add_argument("--transport", choices=("stdio",), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--project-registry-path")
    parser.add_argument("--cmd-white-list")
    parser.add_argument("--cmd-timeout", type=int, default=10)
    parser.add_argument("--render-with-symbols")
    parser.add_argument("--max-active-models", type=int, default=3)
    parser.add_argument("--enable-simple-view-mode")
    return parser


def _validate_cli_arguments() -> bool:
    """Reject removed or unknown arguments before config or server initialization."""
    parser = _build_argument_parser()
    if any(argument in {"-h", "--help"} for argument in sys.argv[1:]):
        parser.print_help()
        return True
    parser.parse_args()
    return False


class IDEMCPServer(BaseMCPServer):
    """Compose project management, generic IDE, and window providers."""

    _IDE_TOOL_TYPES = (GlobTool, GrepTool, ReadTool, EditTool, WriteTool, LspTool)

    def __init__(self, config: MCPServerConfig) -> None:
        """
        初始化 IDE MCP Server | Initialize IDE MCP Server

        Args:
            config: MCP Server 配置 | MCP Server configuration
        """
        if config.transport != "stdio":
            raise ValueError(
                f"Multi-project MCP currently supports stdio transport only; unsupported transport: {config.transport}"
            )
        registry = ProjectRegistry(config.project_registry_path)
        host = ProjectHost(registry, create_ide_factory(config.to_project_ide_defaults()))
        self.project_terminal_manager = ProjectTerminalRuntimeManager()
        super().__init__(
            config,
            server_name="ide4ai-mcp",
            host=host,
            tool_providers=(
                ProjectToolProvider(host, self.project_terminal_manager),
                TerminalToolProvider(host, self.project_terminal_manager),
                TFBashToolProvider(host, self.project_terminal_manager),
                IDEToolProvider(host, self._IDE_TOOL_TYPES),
            ),
            resource_providers=(
                WindowResourceProvider(host),
                TFBashResourceProvider(host, self.project_terminal_manager),
            ),
        )

    async def _close_async_resources(self) -> None:
        await self.project_terminal_manager.aclose_all()

    def close(self) -> None:
        if hasattr(self, "project_terminal_manager"):
            self.project_terminal_manager.prepare_sync_close()
        super().close()


async def async_main() -> None:
    """
    异步主函数 | Async main function

    使用 confz 从环境变量和命令行参数读取配置并启动 MCP Server
    Use confz to read configuration from environment variables and command-line arguments, then start MCP Server

    配置优先级 | Configuration Priority:
        命令行参数 > 环境变量 > 默认值
        Command-line arguments > Environment variables > Default values

    环境变量 | Environment Variables:
        - TRANSPORT: 传输模式 | Transport mode (default: "stdio")
        - HOST: 服务器主机地址 | Server host (default: "127.0.0.1")
        - PORT: 服务器端口 | Server port (default: 8000)
        - PROJECT_REGISTRY_PATH: 项目元数据文件 | Project metadata file
        - CMD_WHITE_LIST: 命令白名单，逗号分隔 | Command whitelist, comma separated
        - CMD_TIMEOUT: 命令超时时间(秒) | Command timeout in seconds (default: 10)
        - RENDER_WITH_SYMBOLS: 是否渲染符号 | Whether to render symbols (default: true)
        - MAX_ACTIVE_MODELS: 最大活跃模型数 | Maximum active models (default: 3)
        - ENABLE_SIMPLE_VIEW_MODE: 是否启用简化视图模式 | Whether to enable simple view mode (default: true)

    命令行参数 | Command-line Arguments:
        - --transport: 传输模式 | Transport mode
        - --host: 服务器主机地址 | Server host
        - --port: 服务器端口 | Server port
        - --project-registry-path: 项目元数据文件 | Project metadata file
        - --cmd-white-list: 命令白名单，逗号分隔 | Command whitelist, comma separated
        - --cmd-timeout: 命令超时时间(秒) | Command timeout in seconds
        - --render-with-symbols: 是否渲染符号 | Whether to render symbols
        - --max-active-models: 最大活跃模型数 | Maximum active models
        - --enable-simple-view-mode: 是否启用简化视图模式 | Whether to enable simple view mode
    """
    # 使用 confz 加载配置 | Load configuration using confz
    # confz 会自动从环境变量和命令行参数中读取配置
    # confz will automatically read configuration from environment variables and command-line arguments
    config = MCPServerConfig()

    logger.info(
        f"启动 MCP Server | Starting MCP Server: "
        f"transport={config.transport}, "
        f"host={config.host}, "
        f"port={config.port}, "
        f"project_registry_path={config.project_registry_path}, "
        f"cmd_white_list={config.cmd_white_list}, "
        f"cmd_timeout={config.cmd_time_out}, "
        f"render_with_symbols={config.render_with_symbols}, "
        f"max_active_models={config.max_active_models}, "
        f"enable_simple_view_mode={config.enable_simple_view_mode}",
    )

    # 创建并运行 server | Create and run server
    server = IDEMCPServer(config)
    try:
        await server.run()
    finally:
        server.close()


def main() -> None:
    """
    同步入口函数 | Synchronous entry point

    用于命令行调用，内部使用 asyncio.run() 运行异步主函数
    For command-line invocation, internally uses asyncio.run() to run the async main function
    """
    if _validate_cli_arguments():
        return

    import asyncio

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
