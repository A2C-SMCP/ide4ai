# -*- coding: utf-8 -*-
# filename: mcp_server_streamable_http_example.py
# @Time    : 2025/10/30 11:54
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Server Streamable HTTP 传输模式示例 | MCP Server Streamable HTTP Transport Mode Example

演示如何使用 Streamable HTTP 模式启动 MCP Server
Demonstrates how to start MCP Server with Streamable HTTP mode

运行方式 | How to Run:
    python examples/mcp_server_streamable_http_example.py

访问方式 | How to Access:
    - 消息端点 | Message Endpoint: POST http://localhost:8000/message
"""

import asyncio

from ide4ai.python_ide.a2c_smcp import MCPServerConfig, PythonIDEMCPServer


async def main() -> None:
    """
    主函数 | Main function

    使用 Streamable HTTP 传输模式启动 MCP Server
    Start MCP Server with Streamable HTTP transport mode
    """
    # 配置 Streamable HTTP 模式 | Configure Streamable HTTP mode
    config = MCPServerConfig(
        transport="streamable-http",
        host="0.0.0.0",  # 监听所有网络接口 | Listen on all network interfaces
        port=8000,
        root_dir=".",
        project_name="streamable-http-example",
        cmd_white_list=["ls", "pwd", "echo", "cat", "grep"],
        cmd_time_out=30,
    )

    print("=" * 60)
    print("启动 MCP Server (Streamable HTTP 模式) | Starting MCP Server (Streamable HTTP Mode)")
    print("=" * 60)
    print(f"服务器地址 | Server Address: http://{config.host}:{config.port}")
    print(f"消息端点 | Message Endpoint: http://{config.host}:{config.port}/message")
    print(f"项目根目录 | Project Root: {config.root_dir}")
    print(f"项目名称 | Project Name: {config.project_name}")
    print("=" * 60)
    print("\n按 Ctrl+C 停止服务器 | Press Ctrl+C to stop the server\n")

    # 创建并运行 server | Create and run server
    server = PythonIDEMCPServer(config)
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n服务器已停止 | Server stopped")
