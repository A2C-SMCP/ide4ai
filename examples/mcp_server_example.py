# -*- coding: utf-8 -*-
# filename: mcp_server_example.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Server 使用示例 | MCP Server Usage Example

演示如何启动和使用 Python IDE MCP Server
Demonstrates how to start and use Python IDE MCP Server
"""

import asyncio
import os

from ide4ai.python_ide.mcp import MCPServerConfig, PythonIDEMCPServer


async def main() -> None:
    """
    主函数 | Main function

    启动 MCP Server 并配置基本参数
    Start MCP Server with basic configuration
    """
    # 从环境变量获取配置，或使用默认值 | Get config from env vars or use defaults
    root_dir = os.getenv("PROJECT_ROOT", ".")
    project_name = os.getenv("PROJECT_NAME", "example-project")

    # 定义命令白名单 | Define command whitelist
    # 这些是允许执行的命令 | These are the allowed commands
    cmd_white_list = [
        # 文件系统操作 | File system operations
        "ls",
        "pwd",
        "cd",
        "cat",
        "head",
        "tail",
        "find",
        "tree",
        # 文本处理 | Text processing
        "echo",
        "grep",
        "sed",
        "awk",
        # Git 操作 | Git operations
        "git status",
        "git log",
        "git diff",
        "git branch",
        # Python 相关 | Python related
        "python --version",
        "pip list",
        "pytest",
        # 构建工具 | Build tools
        "make",
        "npm",
        "yarn",
    ]

    # 创建配置 | Create configuration
    config = MCPServerConfig(
        cmd_white_list=cmd_white_list,
        root_dir=root_dir,
        project_name=project_name,
        render_with_symbols=True,  # 启用符号渲染 | Enable symbol rendering
        max_active_models=3,  # 最大活跃模型数 | Max active models
        cmd_time_out=30,  # 命令超时 30 秒 | Command timeout 30 seconds
        enable_simple_view_mode=True,  # 启用简化视图 | Enable simple view mode
    )

    print("🚀 启动 Python IDE MCP Server | Starting Python IDE MCP Server")
    print(f"📁 项目根目录 | Project root: {root_dir}")
    print(f"📦 项目名称 | Project name: {project_name}")
    print(f"✅ 命令白名单 | Command whitelist: {len(cmd_white_list)} commands")
    print(f"⏱️  命令超时 | Command timeout: {config.cmd_time_out}s")
    print()
    print("💡 提示 | Tip:")
    print("   MCP Server 将通过 stdio 与客户端通信")
    print("   MCP Server will communicate with client via stdio")
    print()

    # 创建并运行 server | Create and run server
    server = PythonIDEMCPServer(config)

    try:
        await server.run()
    except KeyboardInterrupt:
        print("\n👋 MCP Server 已停止 | MCP Server stopped")
    except Exception as e:
        print(f"\n❌ 错误 | Error: {e}")
        raise


if __name__ == "__main__":
    # 运行 server | Run server
    asyncio.run(main())
