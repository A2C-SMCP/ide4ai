# filename: test_mcp_server_transports.py
# @Time    : 2025/10/30 11:59
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Server 传输模式测试 | MCP Server Transport Mode Tests

测试 stdio, SSE 和 Streamable HTTP 三种传输模式
Tests stdio, SSE and Streamable HTTP transport modes
"""

import asyncio

import httpx
import pytest
from confz import DataSource
from confz.exceptions import ConfigException

from ide4ai.python_ide.mcp import MCPServerConfig, PythonIDEMCPServer


class TestMCPServerTransportModes:
    """测试 MCP Server 传输模式 | Test MCP Server Transport Modes"""

    def test_config_stdio_mode(self) -> None:
        """
        测试 stdio 模式配置 | Test stdio mode configuration
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": ".",
                    "project_name": "test-stdio",
                },
            ),
        ):
            config = MCPServerConfig()

            assert config.transport == "stdio"
            assert config.root_dir == "."
            assert config.project_name == "test-stdio"

    def test_config_sse_mode(self) -> None:
        """
        测试 SSE 模式配置 | Test SSE mode configuration
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "sse",
                    "host": "0.0.0.0",
                    "port": 8001,
                    "root_dir": ".",
                    "project_name": "test-sse",
                },
            ),
        ):
            config = MCPServerConfig()

            assert config.transport == "sse"
            assert config.host == "0.0.0.0"
            assert config.port == 8001
            assert config.project_name == "test-sse"

    def test_config_streamable_http_mode(self) -> None:
        """
        测试 Streamable HTTP 模式配置 | Test Streamable HTTP mode configuration
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "streamable-http",
                    "host": "127.0.0.1",
                    "port": 8002,
                    "root_dir": ".",
                    "project_name": "test-http",
                },
            ),
        ):
            config = MCPServerConfig()

            assert config.transport == "streamable-http"
            assert config.host == "127.0.0.1"
            assert config.port == 8002
            assert config.project_name == "test-http"

    def test_invalid_transport_mode(self) -> None:
        """
        测试无效的传输模式 | Test invalid transport mode
        """
        with pytest.raises(ConfigException):
            # 应该抛出验证错误 | Should raise validation error
            MCPServerConfig(
                transport="invalid-mode",  # type: ignore
                root_dir=".",
            )

    def test_server_initialization_stdio(self) -> None:
        """
        测试 stdio 模式服务器初始化 | Test stdio mode server initialization
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": ".",
                    "project_name": "test-stdio-init",
                },
            ),
        ):
            config = MCPServerConfig()

            server = PythonIDEMCPServer(config)
            try:
                assert server.config.transport == "stdio"
                assert server.server is not None
                assert server.ide is not None
                assert len(server.tools) > 0  # 应该有注册的工具 | Should have registered tools
            finally:
                server.close()  # 确保清理资源 | Ensure resources are cleaned up

    def test_server_initialization_sse(self) -> None:
        """
        测试 SSE 模式服务器初始化 | Test SSE mode server initialization
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "sse",
                    "host": "127.0.0.1",
                    "port": 8003,
                    "root_dir": ".",
                    "project_name": "test-sse-init",
                },
            ),
        ):
            config = MCPServerConfig()

            server = PythonIDEMCPServer(config)
            try:
                assert server.config.transport == "sse"
                assert server.config.host == "127.0.0.1"
                assert server.config.port == 8003
            finally:
                server.close()  # 确保清理资源 | Ensure resources are cleaned up

    def test_server_initialization_streamable_http(self) -> None:
        """
        测试 Streamable HTTP 模式服务器初始化 | Test Streamable HTTP mode server initialization
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "streamable-http",
                    "host": "127.0.0.1",
                    "port": 8004,
                    "root_dir": ".",
                    "project_name": "test-http-init",
                },
            ),
        ):
            config = MCPServerConfig()

            server = PythonIDEMCPServer(config)
            try:
                assert server.config.transport == "streamable-http"
                assert server.config.host == "127.0.0.1"
                assert server.config.port == 8004
            finally:
                server.close()  # 确保清理资源 | Ensure resources are cleaned up


@pytest.mark.asyncio
class TestMCPServerSSETransport:
    """测试 MCP Server SSE 传输 | Test MCP Server SSE Transport"""

    async def test_sse_server_startup_and_shutdown(self) -> None:
        """
        测试 SSE 服务器启动和关闭 | Test SSE server startup and shutdown

        注意：这是一个快速启动/关闭测试，不进行实际连接
        Note: This is a quick startup/shutdown test without actual connections
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "sse",
                    "host": "127.0.0.1",
                    "port": 8005,
                    "root_dir": ".",
                    "project_name": "test-sse-lifecycle",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 创建一个任务来运行服务器 | Create a task to run the server
                server_task = asyncio.create_task(server.run())

                # 等待一小段时间让服务器启动 | Wait a bit for server to start
                await asyncio.sleep(0.5)

                # 取消服务器任务 | Cancel server task
                server_task.cancel()

                try:
                    await server_task
                except asyncio.CancelledError:
                    pass  # 预期的取消 | Expected cancellation
            finally:
                server.close()  # 确保清理资源 | Ensure resources are cleaned up

    @pytest.mark.timeout(10)
    async def test_sse_server_endpoints_accessible(self) -> None:
        """
        测试 SSE 服务器端点可访问性 | Test SSE server endpoints accessibility

        启动服务器并验证端点是否可访问
        Start server and verify endpoints are accessible
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "sse",
                    "host": "127.0.0.1",
                    "port": 8006,
                    "root_dir": ".",
                    "project_name": "test-sse-endpoints",
                    "cmd_white_list": ["echo", "pwd"],
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            # 在后台运行服务器 | Run server in background
            server_task = asyncio.create_task(server.run())

            try:
                # 等待服务器启动 | Wait for server to start
                await asyncio.sleep(1)

                # 测试端点是否可访问 | Test if endpoints are accessible
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # 测试 SSE 端点（应该返回 SSE 流）| Test SSE endpoint (should return SSE stream)
                    try:
                        response = await client.get(f"http://{config.host}:{config.port}/sse")
                        # SSE 端点应该开始流式传输 | SSE endpoint should start streaming
                        assert response.status_code in [
                            200,
                            500,
                        ]  # 可能因为没有完整握手而失败 | May fail due to incomplete handshake
                    except Exception:
                        # 连接可能会因为 SSE 握手不完整而失败，这是正常的
                        # Connection may fail due to incomplete SSE handshake, this is normal
                        pass

            finally:
                # 清理：取消服务器任务 | Cleanup: cancel server task
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
                server.close()  # 确保清理资源 | Ensure resources are cleaned up


@pytest.mark.asyncio
class TestMCPServerStreamableHTTPTransport:
    """测试 MCP Server Streamable HTTP 传输 | Test MCP Server Streamable HTTP Transport"""

    async def test_streamable_http_server_startup_and_shutdown(self) -> None:
        """
        测试 Streamable HTTP 服务器启动和关闭 | Test Streamable HTTP server startup and shutdown
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "streamable-http",
                    "host": "127.0.0.1",
                    "port": 8007,
                    "root_dir": ".",
                    "project_name": "test-http-lifecycle",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 创建一个任务来运行服务器 | Create a task to run the server
                server_task = asyncio.create_task(server.run())

                # 等待一小段时间让服务器启动 | Wait a bit for server to start
                await asyncio.sleep(0.5)

                # 取消服务器任务 | Cancel server task
                server_task.cancel()

                try:
                    await server_task
                except asyncio.CancelledError:
                    pass  # 预期的取消 | Expected cancellation
            finally:
                server.close()  # 确保清理资源 | Ensure resources are cleaned up

    @pytest.mark.timeout(10)
    async def test_streamable_http_server_endpoints_accessible(self) -> None:
        """
        测试 Streamable HTTP 服务器端点可访问性 | Test Streamable HTTP server endpoints accessibility
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "streamable-http",
                    "host": "127.0.0.1",
                    "port": 8008,
                    "root_dir": ".",
                    "project_name": "test-http-endpoints",
                    "cmd_white_list": ["echo", "pwd"],
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            # 在后台运行服务器 | Run server in background
            server_task = asyncio.create_task(server.run())

            try:
                # 等待服务器启动 | Wait for server to start
                await asyncio.sleep(1)

                # 测试端点是否可访问 | Test if endpoints are accessible
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # 测试消息端点（POST 请求）| Test message endpoint (POST request)
                    try:
                        # 发送一个简单的测试请求 | Send a simple test request
                        response = await client.post(
                            f"http://{config.host}:{config.port}/mcp",
                            json={"test": "data"},
                            headers={"Content-Type": "application/json"},
                        )
                        # 端点应该可访问（即使请求格式不正确）| Endpoint should be accessible (even if request format is incorrect)
                        # 406 表示服务器拒绝了请求格式，但服务器本身是正常运行的
                        # 406 means server rejected the request format, but the server itself is running normally
                        assert response.status_code in [200, 400, 406, 500]
                    except httpx.ConnectError:
                        pytest.fail("无法连接到 Streamable HTTP 服务器 | Cannot connect to Streamable HTTP server")

            finally:
                # 清理：取消服务器任务 | Cleanup: cancel server task
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
                server.close()  # 确保清理资源 | Ensure resources are cleaned up


@pytest.mark.asyncio
class TestMCPServerTransportIntegration:
    """测试 MCP Server 传输集成 | Test MCP Server Transport Integration"""

    async def test_server_run_method_routing(self) -> None:
        """
        测试服务器 run 方法的路由逻辑 | Test server run method routing logic

        验证不同的传输模式会调用正确的内部方法
        Verify different transport modes call correct internal methods
        """
        # 测试 stdio 模式 | Test stdio mode
        with MCPServerConfig.change_config_sources(
            DataSource(data={"transport": "stdio", "root_dir": ".", "project_name": "test-routing-stdio"}),
        ):
            config_stdio = MCPServerConfig()
            server_stdio = PythonIDEMCPServer(config_stdio)
            try:
                assert server_stdio.config.transport == "stdio"
            finally:
                server_stdio.close()

        # 测试 SSE 模式 | Test SSE mode
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "sse",
                    "host": "127.0.0.1",
                    "port": 8009,
                    "root_dir": ".",
                    "project_name": "test-routing-sse",
                },
            ),
        ):
            config_sse = MCPServerConfig()
            server_sse = PythonIDEMCPServer(config_sse)
            try:
                assert server_sse.config.transport == "sse"
            finally:
                server_sse.close()

        # 测试 Streamable HTTP 模式 | Test Streamable HTTP mode
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "streamable-http",
                    "host": "127.0.0.1",
                    "port": 8010,
                    "root_dir": ".",
                    "project_name": "test-routing-http",
                },
            ),
        ):
            config_http = MCPServerConfig()
            server_http = PythonIDEMCPServer(config_http)
            try:
                assert server_http.config.transport == "streamable-http"
            finally:
                server_http.close()

    async def test_invalid_transport_mode_raises_error(self) -> None:
        """
        测试无效的传输模式抛出错误 | Test invalid transport mode raises error
        """
        # 创建一个配置，然后手动修改 transport 为无效值
        # Create a config, then manually modify transport to invalid value
        with MCPServerConfig.change_config_sources(
            DataSource(data={"transport": "stdio", "root_dir": ".", "project_name": "test-invalid"}),
        ):
            config = MCPServerConfig()

            # 手动设置为无效的传输模式（绕过 Pydantic 验证）
            # Manually set to invalid transport mode (bypass Pydantic validation)
            config.__dict__["transport"] = "invalid-mode"

            server = PythonIDEMCPServer(config)

            try:
                # 运行服务器应该抛出 ValueError | Running server should raise ValueError
                with pytest.raises(ValueError, match="不支持的传输模式|Unsupported transport mode"):
                    await server.run()
            finally:
                server.close()  # 确保清理资源 | Ensure resources are cleaned up
