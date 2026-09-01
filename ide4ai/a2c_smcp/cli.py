# filename: server.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""Concrete project-aware IDE MCP server."""

from pathlib import Path

from loguru import logger

from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.a2c_smcp.projects import (
    ProjectConflictError,
    ProjectHost,
    ProjectLspConfig,
    ProjectNotFoundError,
    ProjectRegistry,
    ProjectTerminalRuntimeManager,
    create_ide_factory,
)
from ide4ai.a2c_smcp.projects.models import roots_refer_to_same_location
from ide4ai.a2c_smcp.providers import (
    IDEToolProvider,
    ProjectToolProvider,
    TerminalToolProvider,
    TFBashToolProvider,
    WindowResourceProvider,
)
from ide4ai.a2c_smcp.resources import WindowResource
from ide4ai.a2c_smcp.server import BaseMCPServer
from ide4ai.a2c_smcp.tools import BashTool, EditTool, GlobTool, GrepTool, LspTool, ReadTool, WriteTool
from ide4ai.a2c_smcp.tools.base import BaseTool
from ide4ai.ide import IDE


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
    parser.add_argument("--transport", choices=("stdio",), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--root-dir")
    parser.add_argument("--project-name")
    parser.add_argument("--project-registry-path")
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
    """Compose project management, generic IDE, and window providers."""

    _IDE_TOOL_TYPES = (GlobTool, GrepTool, ReadTool, EditTool, WriteTool, LspTool)
    _COMPAT_TOOL_TYPES = (BashTool, *_IDE_TOOL_TYPES)

    def __init__(self, config: MCPServerConfig) -> None:
        """
        初始化 IDE MCP Server | Initialize IDE MCP Server

        Args:
            config: MCP Server 配置 | MCP Server configuration
        """
        if config.transport != "stdio":
            raise ValueError(
                f"Multi-project MCP currently supports legacy stdio only; unsupported transport: {config.transport}"
            )
        registry = ProjectRegistry(config.project_registry_path)
        host = ProjectHost(registry, create_ide_factory(config.to_project_ide_defaults()))
        self.project_terminal_manager = ProjectTerminalRuntimeManager()
        self._bootstrap_legacy_project(config, host)
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
            resource_providers=(WindowResourceProvider(host),),
        )

    async def _close_async_resources(self) -> None:
        await self.project_terminal_manager.aclose_all()

    def close(self) -> None:
        if hasattr(self, "project_terminal_manager"):
            self.project_terminal_manager.prepare_sync_close()
        super().close()

    @staticmethod
    def _bootstrap_legacy_project(config: MCPServerConfig, host: ProjectHost) -> None:
        if config.root_dir is None or config.project_name is None:
            return
        canonical_root = str(Path(config.root_dir).expanduser().resolve(strict=True))
        try:
            project = host.registry.find(config.project_name)
            if not roots_refer_to_same_location(project.root_dir, canonical_root):
                raise ProjectConflictError(
                    f"Bootstrap project name already belongs to another root: {config.project_name}"
                )
        except ProjectNotFoundError:
            project = host.create_project(
                name=config.project_name,
                root_dir=canonical_root,
                lsp=ProjectLspConfig(
                    mode=config.lsp_mode,
                    language_id=config.lsp_language_id,
                    profile_language_id=config.lsp_profile_language_id,
                    server_command=config.lsp_server_command,
                    file_extensions=config.lsp_file_extensions,
                    root_markers=config.lsp_root_markers,
                ),
            )
        host.switch_project(project.id)

    @property
    def ide(self) -> IDE:
        """Compatibility accessor for direct, non-MCP integrations."""
        with self.project_host.lease_current() as (_, ide):
            return ide

    @property
    def tools(self) -> dict[str, BaseTool]:
        """Compatibility view of request-bound generic IDE tools."""
        with self.project_host.lease_current() as (_, ide):
            return {tool.name: tool for tool_type in self._COMPAT_TOOL_TYPES for tool in (tool_type(ide),)}

    @property
    def resources(self) -> dict[str, WindowResource]:
        """Compatibility view of the current window resource."""
        with self.project_host.lease_current() as (_, ide):
            resource = WindowResource(ide, priority=0, fullscreen=True)
            return {resource.base_uri: resource}


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
    if _print_help_if_requested():
        return

    import asyncio

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
