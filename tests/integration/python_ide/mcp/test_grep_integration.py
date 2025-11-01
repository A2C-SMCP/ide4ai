# filename: test_grep_integration.py
# @Time    : 2025/11/01 23:17
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 Grep 工具的集成 | Test Grep Tool Integration

测试 Grep 工具在 MCP Server 中的完整集成
Test complete integration of Grep tool in MCP Server
"""

import tempfile
from pathlib import Path

import pytest

from ide4ai.python_ide.mcp.config import MCPServerConfig
from ide4ai.python_ide.mcp.server import PythonIDEMCPServer


class TestGrepIntegration:
    """测试 Grep 工具集成 | Test Grep tool integration"""

    @pytest.fixture(scope="function")
    def temp_server(self):
        """
        创建临时 MCP Server 用于测试 | Create temporary MCP Server for testing
        """
        # 清理可能存在的单例
        from ide4ai.ides import PyIDESingleton

        PyIDESingleton._instances.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件 | Create test files
            test_files = {
                "main.py": """#!/usr/bin/env python
# Main application
def main():
    print("Hello, World!")
    # TODO: Add error handling
    return 0

if __name__ == "__main__":
    main()
""",
                "utils.py": """# Utility functions
def helper():
    # TODO: Implement helper
    pass

def process_data(data):
    # FIXME: Handle edge cases
    return data.strip()
""",
                "tests/test_main.py": """# Test module
import unittest

class TestMain(unittest.TestCase):
    def test_main(self):
        # TODO: Add more tests
        assert True
""",
                "src/config.py": """# Configuration
CONFIG = {
    'debug': True,
    'log_level': 'INFO',
}
""",
            }

            # 创建文件 | Create files
            for file_path, content in test_files.items():
                full_path = Path(tmpdir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # 创建配置 | Create config
            from confz import DataSource

            with MCPServerConfig.change_config_sources(
                DataSource(
                    data={
                        "root_dir": tmpdir,
                        "project_name": "test-grep-integration",
                        "transport": "stdio",
                        "render_with_symbols": False,
                    }
                )
            ):
                config = MCPServerConfig()

            # 创建 server | Create server
            server = PythonIDEMCPServer(config)

            yield server, tmpdir

            # 清理 | Cleanup
            server.close()

    @pytest.mark.asyncio
    async def test_grep_tool_registered(self, temp_server):
        """
        测试 Grep 工具已注册 | Test Grep tool is registered
        """
        server, tmpdir = temp_server

        # 验证 Grep 工具已注册
        assert "Grep" in server.tools
        grep_tool = server.tools["Grep"]
        assert grep_tool.name == "Grep"

    @pytest.mark.asyncio
    async def test_list_tools_includes_grep(self, temp_server):
        """
        测试工具列表包含 Grep | Test tool list includes Grep
        """
        server, tmpdir = temp_server

        # 直接验证工具已注册
        assert "Grep" in server.tools
        grep_tool = server.tools["Grep"]

        # 验证 Grep 工具的属性
        assert grep_tool.name == "Grep"
        assert "ripgrep" in grep_tool.description.lower()
        assert "pattern" in grep_tool.input_schema["properties"]

    @pytest.mark.asyncio
    async def test_call_grep_tool(self, temp_server):
        """
        测试调用 Grep 工具 | Test calling Grep tool
        """
        server, tmpdir = temp_server

        # 直接调用 Grep 工具
        grep_tool = server.tools["Grep"]
        result = await grep_tool.execute(
            {
                "pattern": "TODO",
                "output_mode": "files_with_matches",
            }
        )

        # 验证结果
        assert result["success"] is True
        assert result["matched"] is True
        assert "main.py" in result["output"] or "utils.py" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_with_file_type_filter(self, temp_server):
        """
        测试使用文件类型过滤的 Grep | Test Grep with file type filter
        """
        server, tmpdir = temp_server

        grep_tool = server.tools["Grep"]
        result = await grep_tool.execute(
            {
                "pattern": "def",
                "type": "py",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_grep_content_mode(self, temp_server):
        """
        测试内容模式的 Grep | Test Grep in content mode
        """
        server, tmpdir = temp_server

        grep_tool = server.tools["Grep"]
        result = await grep_tool.execute(
            {
                "pattern": "TODO",
                "output_mode": "content",
                "-n": True,
            }
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "TODO" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_with_glob_pattern(self, temp_server):
        """
        测试使用 glob 模式的 Grep | Test Grep with glob pattern
        """
        server, tmpdir = temp_server

        grep_tool = server.tools["Grep"]
        result = await grep_tool.execute(
            {
                "pattern": "test",
                "glob": "**/test_*.py",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "test_main.py" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_case_insensitive(self, temp_server):
        """
        测试大小写不敏感的 Grep | Test case-insensitive Grep
        """
        server, tmpdir = temp_server

        grep_tool = server.tools["Grep"]
        result = await grep_tool.execute(
            {
                "pattern": "todo",
                "-i": True,
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, temp_server):
        """
        测试无匹配结果的 Grep | Test Grep with no matches
        """
        server, tmpdir = temp_server

        grep_tool = server.tools["Grep"]
        result = await grep_tool.execute(
            {
                "pattern": "NONEXISTENT_PATTERN_ABC123",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is False

    @pytest.mark.asyncio
    async def test_grep_invalid_tool_name(self, temp_server):
        """
        测试调用不存在的工具 | Test calling non-existent tool
        """
        server, tmpdir = temp_server

        # 验证不存在的工具不在注册列表中
        assert "NonExistentTool" not in server.tools

    @pytest.mark.asyncio
    async def test_grep_invalid_arguments(self, temp_server):
        """
        测试使用无效参数调用 Grep | Test calling Grep with invalid arguments
        """
        server, tmpdir = temp_server

        grep_tool = server.tools["Grep"]
        result = await grep_tool.execute({})  # 缺少 pattern

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_multiple_tools_available(self, temp_server):
        """
        测试多个工具可用 | Test multiple tools are available
        """
        server, tmpdir = temp_server

        # 验证多个工具已注册
        assert "Bash" in server.tools
        assert "Glob" in server.tools
        assert "Grep" in server.tools

        # 验证每个工具都可以正常工作
        assert server.tools["Bash"].name == "Bash"
        assert server.tools["Glob"].name == "Glob"
        assert server.tools["Grep"].name == "Grep"


class TestGrepIntegrationRealWorld:
    """测试真实场景的集成 | Test real-world integration scenarios"""

    @pytest.mark.asyncio
    async def test_search_python_imports(self):
        """
        测试搜索 Python 导入语句 | Test searching Python imports
        """
        # 清理单例
        from ide4ai.ides import PyIDESingleton

        PyIDESingleton._instances.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建包含导入语句的文件
            (Path(tmpdir) / "module1.py").write_text("import os\nimport sys\n")
            (Path(tmpdir) / "module2.py").write_text("from pathlib import Path\n")

            from confz import DataSource

            with MCPServerConfig.change_config_sources(DataSource(data={"root_dir": tmpdir, "project_name": "test"})):
                config = MCPServerConfig()

            server = PythonIDEMCPServer(config)

            try:
                # 搜索 import 语句
                grep_tool = server.tools["Grep"]
                result = await grep_tool.execute(
                    {
                        "pattern": r"^import\s+",
                        "output_mode": "content",
                        "-n": True,
                    }
                )

                assert result["success"] is True
            finally:
                server.close()

    @pytest.mark.asyncio
    async def test_search_function_definitions(self):
        """
        测试搜索函数定义 | Test searching function definitions
        """
        # 清理单例
        from ide4ai.ides import PyIDESingleton

        PyIDESingleton._instances.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建包含函数定义的文件
            (Path(tmpdir) / "code.py").write_text("""
def function1():
    pass

def function2(arg):
    return arg

class MyClass:
    def method(self):
        pass
""")

            from confz import DataSource

            with MCPServerConfig.change_config_sources(DataSource(data={"root_dir": tmpdir, "project_name": "test"})):
                config = MCPServerConfig()

            server = PythonIDEMCPServer(config)

            try:
                # 搜索函数定义
                grep_tool = server.tools["Grep"]
                result = await grep_tool.execute(
                    {
                        "pattern": r"^\s*def\s+\w+",
                        "output_mode": "content",
                    }
                )

                assert result["success"] is True
                assert "def" in result["output"]
            finally:
                server.close()
