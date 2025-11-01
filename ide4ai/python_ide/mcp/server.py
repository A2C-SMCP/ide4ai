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

from typing import Any

from loguru import logger
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route

from ide4ai.ides import PyIDESingleton
from ide4ai.python_ide.mcp.config import MCPServerConfig
from ide4ai.python_ide.mcp.tools import BashTool, GlobTool
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

    def close(self) -> None:
        """
        关闭 MCP Server 并清理资源 | Close MCP Server and cleanup resources

        释放 IDE 和 workspace 资源，关闭 LSP 进程
        Release IDE and workspace resources, close LSP process
        """
        try:
            if self.ide:
                # 调用 IDE 的 close 方法，由 IDE 负责清理其内部资源
                # Call IDE's close method, let IDE handle its internal resource cleanup
                self.ide.close()
                logger.info(
                    f"MCP Server 资源已清理 | MCP Server resources cleaned up: project={self.config.project_name}"
                )
        except Exception as e:
            logger.error(f"关闭 MCP Server 时出错 | Error closing MCP Server: {e}")

    def __del__(self) -> None:
        """
        析构函数，确保资源被清理 | Destructor to ensure resources are cleaned up
        """
        try:
            self.close()
        except Exception as e:
            # 在析构函数中捕获所有异常，避免影响垃圾回收
            # Catch all exceptions in destructor to avoid affecting garbage collection
            logger.error(f"析构时关闭环境出错 / Error closing environment in destructor: {e}")

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

        logger.info(f"已注册工具 | Registered tools: {list(self.tools.keys())}")

        # TODO: 注册其他工具 | Register other tools
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

        根据配置选择传输协议：stdio, sse 或 streamable-http
        Choose transport protocol based on configuration: stdio, sse or streamable-http
        """
        transport = self.config.transport
        logger.info(f"启动 MCP Server | Starting MCP Server with transport: {transport}")

        if transport == "stdio":
            await self._run_stdio()
        elif transport == "sse":
            await self._run_sse()
        elif transport == "streamable-http":
            await self._run_streamable_http()
        else:
            raise ValueError(f"不支持的传输模式 | Unsupported transport mode: {transport}")

    async def _run_stdio(self) -> None:
        """
        使用 stdio 传输运行 | Run with stdio transport
        """
        logger.info("使用 stdio 传输模式 | Using stdio transport")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )

    async def _run_sse(self) -> None:
        """
        使用 SSE 传输运行 | Run with SSE transport

        SSE (Server-Sent Events) 适用于需要服务器主动推送的场景
        SSE is suitable for scenarios requiring server-initiated push
        """
        import uvicorn

        logger.info(
            f"使用 SSE 传输模式 | Using SSE transport: http://{self.config.host}:{self.config.port}",
        )

        # 创建 SSE 传输 | Create SSE transport
        sse = SseServerTransport("/messages/")

        # 定义 SSE 处理器 | Define SSE handler
        async def handle_sse(request: Any) -> Response:
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await self.server.run(
                    streams[0],
                    streams[1],
                    self.server.create_initialization_options(),
                )
            return Response()

        # 创建路由 | Create routes
        routes = [
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=sse.handle_post_message),
        ]

        # 创建并运行 Starlette 应用 | Create and run Starlette app
        app = Starlette(routes=routes)
        config = uvicorn.Config(
            app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def _run_streamable_http(self) -> None:
        """
        使用 Streamable HTTP 传输运行 | Run with Streamable HTTP transport

        Streamable HTTP 支持双向通信和流式响应，适合复杂交互场景
        Streamable HTTP supports bidirectional communication and streaming responses

        参考官方示例实现 | Reference official example implementation:
        - tests/shared/test_streamable_http.py::create_app
        """
        import uvicorn

        logger.info(
            f"使用 Streamable HTTP 传输模式 | Using Streamable HTTP transport: "
            f"http://{self.config.host}:{self.config.port}/mcp",
        )

        # 创建会话管理器 | Create session manager
        # stateless=True: 每个请求都是独立的，不维护会话状态
        # stateless=True: Each request is independent, no session state is maintained
        session_manager = StreamableHTTPSessionManager(
            app=self.server,
            stateless=True,  # 无状态模式，适合简单场景 | Stateless mode, suitable for simple scenarios
            json_response=False,  # 使用 SSE 流式响应 | Use SSE streaming response
        )

        # 创建 ASGI 应用包装器类 | Create ASGI app wrapper class
        # 参考 FastMCP 的 StreamableHTTPASGIApp 实现
        # Reference FastMCP's StreamableHTTPASGIApp implementation
        class StreamableHTTPASGIApp:
            """ASGI 应用包装器 | ASGI application wrapper"""

            def __init__(self, manager: StreamableHTTPSessionManager) -> None:
                self.session_manager = manager

            async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
                await self.session_manager.handle_request(scope, receive, send)

        # 创建 ASGI 应用实例 | Create ASGI app instance
        streamable_http_app = StreamableHTTPASGIApp(session_manager)

        # 创建 Starlette 应用 | Create Starlette application
        # 参考 FastMCP 实现：使用 Route 配合 ASGI 应用类
        # Reference FastMCP implementation: Use Route with ASGI app class
        app = Starlette(
            debug=False,
            routes=[
                # 使用 Route 处理 /mcp 端点（官方标准端点）
                # Use Route to handle /mcp endpoint (official standard endpoint)
                Route(
                    "/mcp",
                    endpoint=streamable_http_app,
                    methods=["GET", "POST", "DELETE"],
                ),
            ],
            lifespan=lambda app: session_manager.run(),
        )

        # 启动 HTTP 服务器 | Start HTTP server
        config = uvicorn.Config(
            app=app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()


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
        f"enable_simple_view_mode={config.enable_simple_view_mode}",
    )

    # 创建并运行 server | Create and run server
    server = PythonIDEMCPServer(config)
    await server.run()


def main() -> None:
    """
    同步入口函数 | Synchronous entry point

    用于命令行调用，内部使用 asyncio.run() 运行异步主函数
    For command-line invocation, internally uses asyncio.run() to run the async main function
    """
    import asyncio

    asyncio.run(async_main())
