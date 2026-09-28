# filename: mcp_server_example.py
# @Time    : 2025/10/30 11:54
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Server stdio 传输模式示例 | MCP Server stdio Transport Mode Example

演示如何使用默认的 stdio 模式启动 MCP Server
Demonstrates how to start MCP Server with default stdio mode

运行方式 | How to Run:
    python examples/mcp_server_example.py

注意 | Note:
    stdio 模式适合本地进程间通信，如 Claude Desktop 集成
    stdio mode is suitable for local inter-process communication, e.g., Claude Desktop integration
"""

import asyncio

from confz import DataSource

from ide4ai.a2c_smcp import IDEMCPServer, MCPServerConfig


async def main() -> None:
    """
    主函数 | Main function

    启动 MCP Server 并配置基本参数
    Start MCP Server with basic configuration
    """
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
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "cmd_white_list": cmd_white_list,
                "render_with_symbols": True,
                "max_active_models": 3,
                "cmd_time_out": 30,
                "enable_simple_view_mode": True,
            }
        )
    ):
        config = MCPServerConfig()

    print("🚀 启动 IDE MCP Server | Starting IDE MCP Server")
    print(f"✅ 命令白名单 | Command whitelist: {len(cmd_white_list)} commands")
    print(f"⏱️  命令超时 | Command timeout: {config.cmd_time_out}s")
    print()
    print("💡 提示 | Tip:")
    print("   MCP Server 将通过 stdio 与客户端通信")
    print("   MCP Server will communicate with client via stdio")
    print("   启动后请通过 project_create 注册项目 | Register projects with project_create after startup")
    print()

    # 创建并运行 server | Create and run server
    server = IDEMCPServer(config)

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
