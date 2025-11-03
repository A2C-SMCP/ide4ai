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
                    },
                ),
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
            },
        )

        # 验证结果
        assert result["success"] is True, str(result)
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
            },
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
            },
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
            },
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
            },
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
            },
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
                    },
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
                    },
                )

                assert result["success"] is True
                assert "def" in result["output"]
            finally:
                server.close()


class TestGrepContextOptions:
    """测试 Grep 上下文选项组合 | Test Grep context options combinations"""

    @pytest.fixture(scope="function")
    def context_server(self):
        """
        创建包含多行上下文的测试服务器 | Create test server with multi-line context
        """
        from ide4ai.ides import PyIDESingleton

        PyIDESingleton._instances.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建包含丰富上下文的测试文件
            test_content = """# Python Module
import os
import sys
from typing import List, Dict

# Configuration section
DEBUG = True
VERSION = "1.0.0"

def setup_logging():
    \"\"\"Setup logging configuration\"\"\"
    import logging
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger(__name__)

class DataProcessor:
    \"\"\"Process data with various methods\"\"\"

    def __init__(self, config: Dict):
        self.config = config
        self.logger = setup_logging()

    def process(self, data: List):
        \"\"\"Main processing method\"\"\"
        # TODO: Implement data validation
        self.logger.info("Processing data")
        result = []
        for item in data:
            # FIXME: Handle edge cases
            processed = self._transform(item)
            result.append(processed)
        return result

    def _transform(self, item):
        \"\"\"Transform single item\"\"\"
        return item.strip().lower()

def main():
    \"\"\"Main entry point\"\"\"
    processor = DataProcessor({'debug': DEBUG})
    data = ['Item1', 'Item2', 'Item3']
    # Process the data
    result = processor.process(data)
    print(f"Processed {len(result)} items")
    return result

if __name__ == "__main__":
    main()
"""
            (Path(tmpdir) / "processor.py").write_text(test_content)

            # 创建另一个测试文件
            test_content2 = """# Test Module
import unittest
from processor import DataProcessor

class TestDataProcessor(unittest.TestCase):
    \"\"\"Test cases for DataProcessor\"\"\"

    def setUp(self):
        \"\"\"Setup test fixtures\"\"\"
        self.config = {'debug': True}
        self.processor = DataProcessor(self.config)

    def test_process_empty_list(self):
        \"\"\"Test processing empty list\"\"\"
        result = self.processor.process([])
        self.assertEqual(result, [])

    def test_process_single_item(self):
        \"\"\"Test processing single item\"\"\"
        # TODO: Add more test cases
        result = self.processor.process(['Test'])
        self.assertEqual(len(result), 1)

    def tearDown(self):
        \"\"\"Cleanup test fixtures\"\"\"
        self.processor = None
"""
            (Path(tmpdir) / "test_processor.py").write_text(test_content2)

            from confz import DataSource

            with MCPServerConfig.change_config_sources(
                DataSource(data={"root_dir": tmpdir, "project_name": "test-context"}),
            ):
                config = MCPServerConfig()

            server = PythonIDEMCPServer(config)
            yield server, tmpdir
            server.close()

    @pytest.mark.asyncio
    async def test_grep_with_line_numbers(self, context_server):
        """
        测试带行号的搜索 | Test search with line numbers (-n)
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "TODO",
                "output_mode": "content",
                "-n": True,
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 验证输出包含行号
        assert ":" in result["output"]
        assert "TODO" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_with_after_context(self, context_server):
        """
        测试带后续上下文的搜索 | Test search with after context (-A)
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "def process",
                "output_mode": "content",
                "-n": True,
                "-A": 3,  # 显示匹配行后的 3 行
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "def process" in result["output"]
        # 验证包含后续上下文
        assert "TODO" in result["output"] or "logger" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_with_before_context(self, context_server):
        """
        测试带前置上下文的搜索 | Test search with before context (-B)
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "FIXME",
                "output_mode": "content",
                "-n": True,
                "-B": 2,  # 显示匹配行前的 2 行
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "FIXME" in result["output"]
        # 验证包含前置上下文（应该能看到循环相关代码）
        assert "for" in result["output"] or "item" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_with_context_both_sides(self, context_server):
        """
        测试带双向上下文的搜索 | Test search with context on both sides (-C)
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "def main",
                "output_mode": "content",
                "-n": True,
                "-C": 2,  # 显示匹配行前后各 2 行
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "def main" in result["output"]
        # 验证包含前后上下文
        output_lines = result["output"].split("\n")
        assert len(output_lines) > 3  # 至少有匹配行 + 前后上下文

    @pytest.mark.asyncio
    async def test_grep_with_before_and_after_context(self, context_server):
        """
        测试同时指定前置和后续上下文 | Test search with both -A and -B
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "class DataProcessor",
                "output_mode": "content",
                "-n": True,
                "-B": 1,  # 前 1 行
                "-A": 4,  # 后 4 行
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "class DataProcessor" in result["output"]
        # 验证包含类的文档字符串和初始化方法
        assert "Process data" in result["output"] or "__init__" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_context_with_multiple_matches(self, context_server):
        """
        测试多个匹配时的上下文显示 | Test context display with multiple matches
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": r"def \w+",
                "output_mode": "content",
                "-n": True,
                "-A": 2,
                "-B": 1,
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 验证包含多个函数定义
        assert result["output"].count("def") >= 2

    @pytest.mark.asyncio
    async def test_grep_context_with_case_insensitive(self, context_server):
        """
        测试大小写不敏感搜索带上下文 | Test case-insensitive search with context
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "todo",
                "output_mode": "content",
                "-i": True,  # 大小写不敏感
                "-n": True,
                "-C": 2,
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 验证能找到 TODO（大写）
        assert "TODO" in result["output"] or "todo" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_grep_context_with_type_filter(self, context_server):
        """
        测试文件类型过滤带上下文 | Test file type filter with context
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "import",
                "type": "py",
                "output_mode": "content",
                "-n": True,
                "-A": 1,
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "import" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_context_with_glob_pattern(self, context_server):
        """
        测试 glob 模式匹配带上下文 | Test glob pattern with context
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "test",
                "glob": "test_*.py",
                "output_mode": "content",
                "-i": True,
                "-n": True,
                "-B": 1,
                "-A": 2,
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 应该只匹配 test_processor.py 文件
        assert "test" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_grep_large_context(self, context_server):
        """
        测试大量上下文行 | Test large context lines
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "def process",
                "output_mode": "content",
                "-n": True,
                "-A": 10,  # 大量后续上下文
                "-B": 5,  # 较多前置上下文
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 验证输出包含大量上下文
        output_lines = result["output"].split("\n")
        assert len(output_lines) > 10

    @pytest.mark.asyncio
    async def test_grep_context_regex_pattern(self, context_server):
        """
        测试正则表达式模式带上下文 | Test regex pattern with context
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": r"def \w+\(self",
                "output_mode": "content",
                "-n": True,
                "-C": 3,
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 应该匹配类方法
        assert "def" in result["output"]
        assert "self" in result["output"]

    @pytest.mark.asyncio
    async def test_grep_context_with_max_count(self, context_server):
        """
        测试限制匹配数量带上下文 | Test max count with context
        """
        server, tmpdir = context_server
        grep_tool = server.tools["Grep"]

        result = await grep_tool.execute(
            {
                "pattern": "def",
                "output_mode": "content",
                "-n": True,
                "-A": 2,
                "-m": 2,  # 最多匹配 2 次
            },
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 验证结果被限制
        assert "def" in result["output"]
