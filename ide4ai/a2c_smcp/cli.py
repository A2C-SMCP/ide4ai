# filename: server.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""Concrete language-profile-driven IDE MCP server."""

from loguru import logger

from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.resources import WindowResource
from ide4ai.a2c_smcp.server import BaseMCPServer
from ide4ai.a2c_smcp.tools import BashTool, EditTool, GlobTool, GrepTool, LspTool, ReadTool, WriteTool
from ide4ai.ide import IDE
from ide4ai.ides import IDEInstance


def _print_help_if_requested() -> bool:
    """Print stable CLI help before confz initializes the server."""
    import argparse
    import sys

    if not any(argument in {"-h", "--help"} for argument in sys.argv[1:]):
        return False
    parser = argparse.ArgumentParser(
        prog="ide4ai-mcp",
        description="Expose an ide4ai workspace through the Model Context Protocol.",
    )
    parser.add_argument("--transport", choices=("stdio", "sse", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--project-name", default="mcp-project")
    parser.add_argument("--cmd-white-list")
    parser.add_argument("--cmd-timeout", type=int, default=10)
    parser.add_argument("--render-with-symbols")
    parser.add_argument("--max-active-models", type=int, default=3)
    parser.add_argument("--enable-simple-view-mode")
    parser.add_argument("--lsp-mode", choices=("auto", "explicit", "disabled"), default="auto")
    parser.add_argument("--lsp-language-id")
    parser.add_argument("--lsp-profile-language-id")
    parser.add_argument("--lsp-server-command")
    parser.add_argument("--lsp-file-extensions")
    parser.add_argument("--lsp-root-markers")
    parser.print_help()
    return True


class IDEMCPServer(BaseMCPServer):
    """
    Generic IDE MCP Server

    继承通用 MCP Server 基类，封装 IDE 的能力
    Inherits from generic MCP Server base class, wrapping IDE capabilities
    """

    def __init__(self, config: MCPServerConfig) -> None:
        """
        初始化 IDE MCP Server | Initialize IDE MCP Server

        Args:
            config: MCP Server 配置 | MCP Server configuration
        """
        # 调用父类初始化 | Call parent class initialization
        super().__init__(config, server_name="ide4ai-mcp")

    def _create_ide_instance(self) -> IDE:
        """
        创建 IDE 实例 | Create IDE instance

        使用 IDEInstance 获取 IDE 实例
        Get IDE instance using IDEInstance

        Returns:
            IDE: IDE 实例 | IDE instance
        """
        ide_singleton = IDEInstance(**self.config.to_ide_kwargs())
        return ide_singleton.ide

    def _register_tools(self) -> None:
        """
        注册所有工具 | Register all tools
        """
        # 注册 Bash 工具 | Register Bash tool
        bash_tool = BashTool(self.ide)
        self.tools[bash_tool.name] = bash_tool

        # 注册 Glob 工具 | Register Glob tool
        glob_tool = GlobTool(self.ide)
        self.tools[glob_tool.name] = glob_tool

        # 注册 Grep 工具 | Register Grep tool
        grep_tool = GrepTool(self.ide)
        self.tools[grep_tool.name] = grep_tool

        # 注册 Read 工具 | Register Read tool
        read_tool = ReadTool(self.ide)
        self.tools[read_tool.name] = read_tool

        # 注册 Edit 工具 | Register Edit tool
        edit_tool = EditTool(self.ide)
        self.tools[edit_tool.name] = edit_tool

        # 注册 Write 工具 | Register Write tool
        write_tool = WriteTool(self.ide)
        self.tools[write_tool.name] = write_tool

        lsp_tool = LspTool(self.ide)
        self.tools[lsp_tool.name] = lsp_tool

        logger.info(f"已注册工具 | Registered tools: {list(self.tools.keys())}")

    def _register_resources(self) -> None:
        """
        注册所有资源 | Register all resources
        """
        # 注册窗口资源 | Register Window resource
        # 使用 base_uri 作为 key，确保相同资源不同参数使用同一个实例
        # Use base_uri as key to ensure same resource with different params uses same instance
        window_resource = WindowResource(self.ide, priority=0, fullscreen=True)
        self.resources[window_resource.base_uri] = window_resource

        logger.info(f"已注册资源 | Registered resources: {list(self.resources.keys())}")

        # TODO: 注册其他资源 | Register other resources


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
        - PROJECT_ROOT: 项目根目录 | Project root directory (default: ".")
        - PROJECT_NAME: 项目名称 | Project name (default: "mcp-project")
        - CMD_WHITE_LIST: 命令白名单，逗号分隔 | Command whitelist, comma separated
        - CMD_TIMEOUT: 命令超时时间(秒) | Command timeout in seconds (default: 10)
        - RENDER_WITH_SYMBOLS: 是否渲染符号 | Whether to render symbols (default: true)
        - MAX_ACTIVE_MODELS: 最大活跃模型数 | Maximum active models (default: 3)
        - ENABLE_SIMPLE_VIEW_MODE: 是否启用简化视图模式 | Whether to enable simple view mode (default: true)

    命令行参数 | Command-line Arguments:
        - --transport: 传输模式 | Transport mode
        - --host: 服务器主机地址 | Server host
        - --port: 服务器端口 | Server port
        - --root-dir: 项目根目录 | Project root directory
        - --project-name: 项目名称 | Project name
        - --cmd-white-list: 命令白名单，逗号分隔 | Command whitelist, comma separated
        - --cmd-timeout: 命令超时时间(秒) | Command timeout in seconds
        - --render-with-symbols: 是否渲染符号 | Whether to render symbols
        - --max-active-models: 最大活跃模型数 | Maximum active models
        - --enable-simple-view-mode: 是否启用简化视图模式 | Whether to enable simple view mode
        - --lsp-mode: auto, explicit, or disabled
        - --lsp-language-id: language id used by explicit mode
        - --lsp-profile-language-id: profile id configured for auto or explicit mode
        - --lsp-server-command: shell-style language-server command override
        - --lsp-file-extensions: comma-separated extensions for a custom language
        - --lsp-root-markers: comma-separated workspace markers for a custom language
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
        f"root_dir={config.root_dir}, "
        f"project_name={config.project_name}, "
        f"cmd_white_list={config.cmd_white_list}, "
        f"cmd_timeout={config.cmd_time_out}, "
        f"render_with_symbols={config.render_with_symbols}, "
        f"max_active_models={config.max_active_models}, "
        f"enable_simple_view_mode={config.enable_simple_view_mode}, "
        f"lsp_mode={config.lsp_mode}, "
        f"lsp_language_id={config.lsp_language_id}",
    )

    # 创建并运行 server | Create and run server
    server = IDEMCPServer(config)
    await server.run()


def main() -> None:
    """
    同步入口函数 | Synchronous entry point

    用于命令行调用，内部使用 asyncio.run() 运行异步主函数
    For command-line invocation, internally uses asyncio.run() to run the async main function
    """
    if _print_help_if_requested():
        return

    import asyncio

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
