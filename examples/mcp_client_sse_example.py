# -*- coding: utf-8 -*-
# filename: mcp_client_sse_example.py
# @Time    : 2025/10/30 11:54
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Client SSE 连接示例 | MCP Client SSE Connection Example

演示如何连接到 SSE 模式的 MCP Server
Demonstrates how to connect to MCP Server in SSE mode

运行方式 | How to Run:
    1. 先启动 SSE Server | First start SSE Server:
       python examples/mcp_server_sse_example.py

    2. 再运行此客户端 | Then run this client:
       python examples/mcp_client_sse_example.py

注意 | Note:
    此示例需要 MCP Client SDK 支持
    This example requires MCP Client SDK support
"""

import asyncio
import json

import httpx


async def main() -> None:
    """
    主函数 | Main function

    连接到 SSE 模式的 MCP Server 并调用工具
    Connect to MCP Server in SSE mode and call tools
    """
    server_url = "http://localhost:8000"
    sse_endpoint = f"{server_url}/sse"
    message_endpoint = f"{server_url}/messages/"

    print("=" * 60)
    print("MCP Client SSE 示例 | MCP Client SSE Example")
    print("=" * 60)
    print(f"连接到 | Connecting to: {server_url}")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # 示例：调用 bash 工具 | Example: Call bash tool
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "bash",
                "arguments": {
                    "command": "ls -la",
                    "description": "List files in current directory",
                },
            },
        }

        print("\n发送请求 | Sending request:")
        print(json.dumps(request_data, indent=2))

        # 发送请求到消息端点 | Send request to message endpoint
        response = await client.post(
            message_endpoint,
            json=request_data,
            headers={"Content-Type": "application/json"},
        )

        print(f"\n响应状态码 | Response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print("\n响应结果 | Response result:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"\n错误 | Error: {response.text}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n客户端已停止 | Client stopped")
    except Exception as e:
        print(f"\n错误 | Error: {e}")
        print("\n提示 | Hint: 请确保 MCP Server 已启动 | Please ensure MCP Server is running")
