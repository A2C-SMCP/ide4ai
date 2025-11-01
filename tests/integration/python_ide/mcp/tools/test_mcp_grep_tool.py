# filename: test_grep_tool.py
# @Time    : 2025/11/01 23:17
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 Grep MCP 工具 | Test Grep MCP Tool

测试 GrepTool 的功能和集成
Test GrepTool functionality and integration
"""

import os
import tempfile
from pathlib import Path

import pytest

from ide4ai.python_ide.ide import PythonIDE
from ide4ai.python_ide.mcp.schemas.tools import GrepInput, GrepOutput
from ide4ai.python_ide.mcp.tools.grep import GrepTool


class TestGrepTool:
    """测试 GrepTool 类 | Test GrepTool class"""

    @pytest.fixture
    def temp_ide(self):
        """
        创建临时 IDE 实例用于测试 | Create temporary IDE instance for testing
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件 | Create test files
            test_files = {
                "app.py": """# Application
def start():
    print("Starting app")
    # TODO: Add logging
    return True
""",
                "config.py": """# Configuration
CONFIG = {
    'debug': True,
    # TODO: Add more config
}
""",
                "tests/test_app.py": """# Tests
import unittest

class TestApp(unittest.TestCase):
    def test_start(self):
        # FIXME: Complete test
        pass
""",
            }

            # 创建文件 | Create files
            for file_path, content in test_files.items():
                full_path = Path(tmpdir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # 创建 IDE 实例 | Create IDE instance
            ide = PythonIDE(
                root_dir=tmpdir,
                project_name="test-grep-tool",
                render_with_symbols=False,
            )

            yield ide, tmpdir

            # 清理 | Cleanup
            ide.close()

    @pytest.mark.asyncio
    async def test_tool_properties(self, temp_ide):
        """
        测试工具属性 | Test tool properties
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        assert tool.name == "Grep"
        assert "ripgrep" in tool.description
        assert isinstance(tool.input_schema, dict)
        assert "pattern" in tool.input_schema["properties"]

    @pytest.mark.asyncio
    async def test_basic_search(self, temp_ide):
        """
        测试基本搜索 | Test basic search
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 搜索 "TODO"
        result = await tool.execute(
            {
                "pattern": "TODO",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "app.py" in result["output"] or "config.py" in result["output"]

    @pytest.mark.asyncio
    async def test_search_with_file_type(self, temp_ide):
        """
        测试按文件类型搜索 | Test search with file type
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 仅搜索 Python 文件
        result = await tool.execute(
            {
                "pattern": "def",
                "type": "py",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_search_content_mode(self, temp_ide):
        """
        测试内容模式 | Test content mode
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 搜索并显示内容
        result = await tool.execute(
            {
                "pattern": "TODO",
                "output_mode": "content",
                "-n": True,  # 显示行号
            }
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "TODO" in result["output"]

    @pytest.mark.asyncio
    async def test_search_with_context(self, temp_ide):
        """
        测试带上下文搜索 | Test search with context
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 搜索并显示上下文
        result = await tool.execute(
            {
                "pattern": "TODO",
                "output_mode": "content",
                "-C": 2,  # 前后各 2 行
                "-n": True,
            }
        )

        assert result["success"] is True
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, temp_ide):
        """
        测试大小写不敏感搜索 | Test case-insensitive search
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 搜索 "todo"（小写）
        result = await tool.execute(
            {
                "pattern": "todo",
                "-i": True,  # 忽略大小写
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_search_with_glob(self, temp_ide):
        """
        测试使用 glob 过滤 | Test search with glob filter
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 仅搜索测试文件
        result = await tool.execute(
            {
                "pattern": "test",
                "glob": "**/test_*.py",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "test_app.py" in result["output"]

    @pytest.mark.asyncio
    async def test_search_count_mode(self, temp_ide):
        """
        测试计数模式 | Test count mode
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 统计匹配数量
        result = await tool.execute(
            {
                "pattern": "def",
                "output_mode": "count",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_search_with_head_limit(self, temp_ide):
        """
        测试限制输出行数 | Test output line limit
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 限制输出
        result = await tool.execute(
            {
                "pattern": "def",
                "output_mode": "content",
                "head_limit": 5,
            }
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_multiline(self, temp_ide):
        """
        测试多行搜索 | Test multiline search
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 多行模式搜索
        result = await tool.execute(
            {
                "pattern": r"def.*\n.*print",
                "multiline": True,
                "output_mode": "content",
            }
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_no_matches(self, temp_ide):
        """
        测试无匹配结果 | Test no matches
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 搜索不存在的内容
        result = await tool.execute(
            {
                "pattern": "NONEXISTENT_PATTERN_XYZ",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is False
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_invalid_arguments(self, temp_ide):
        """
        测试无效参数 | Test invalid arguments
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 缺少必需参数
        result = await tool.execute({})

        assert result["success"] is False
        assert "error" in result
        assert "参数验证失败" in result["error"]

    @pytest.mark.asyncio
    async def test_search_in_subdirectory(self, temp_ide):
        """
        测试在子目录中搜索 | Test search in subdirectory
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        # 在 tests 目录中搜索
        result = await tool.execute(
            {
                "pattern": "FIXME",
                "path": os.path.join(tmpdir, "tests"),
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "test_app.py" in result["output"]

    @pytest.mark.asyncio
    async def test_search_metadata(self, temp_ide):
        """
        测试返回的元数据 | Test returned metadata
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        result = await tool.execute(
            {
                "pattern": "TODO",
                "output_mode": "files_with_matches",
            }
        )

        assert result["success"] is True
        assert "metadata" in result
        assert result["metadata"]["pattern"] == "TODO"

    @pytest.mark.asyncio
    async def test_input_validation(self, temp_ide):
        """
        测试输入验证 | Test input validation
        """
        ide, tmpdir = temp_ide

        # 测试有效输入
        valid_input = GrepInput(
            pattern="test",
            output_mode="content",
        )
        assert valid_input.pattern == "test"
        assert valid_input.output_mode == "content"

        # 测试别名参数
        input_with_aliases = GrepInput(pattern="test", **{"-n": True, "-i": True, "-C": 3})
        assert input_with_aliases.line_number is True
        assert input_with_aliases.case_insensitive is True
        assert input_with_aliases.context == 3

    @pytest.mark.asyncio
    async def test_output_schema(self, temp_ide):
        """
        测试输出 Schema | Test output schema
        """
        ide, tmpdir = temp_ide
        tool = GrepTool(ide)

        result = await tool.execute(
            {
                "pattern": "TODO",
            }
        )

        # 验证输出符合 GrepOutput schema
        output = GrepOutput.model_validate(result)
        assert output.success is True
        assert isinstance(output.matched, bool)
        assert isinstance(output.output, str)


class TestGrepToolEdgeCases:
    """测试边界情况 | Test edge cases"""

    @pytest.mark.asyncio
    async def test_workspace_not_initialized(self):
        """
        测试 workspace 未初始化的情况 | Test when workspace is not initialized
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            ide = PythonIDE(
                root_dir=tmpdir,
                project_name="test",
                render_with_symbols=False,
            )

            # 关闭 workspace
            if ide.workspace:
                ide.workspace.close()
                ide.workspace = None

            tool = GrepTool(ide)

            result = await tool.execute(
                {
                    "pattern": "test",
                }
            )

            assert result["success"] is False
            assert "Workspace 未初始化" in result["error"]

            ide.close()

    @pytest.mark.asyncio
    async def test_invalid_path_error(self):
        """
        测试无效路径错误处理 | Test invalid path error handling
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            ide = PythonIDE(
                root_dir=tmpdir,
                project_name="test",
                render_with_symbols=False,
            )

            tool = GrepTool(ide)

            # 搜索不存在的路径
            result = await tool.execute(
                {
                    "pattern": "test",
                    "path": "/nonexistent/path",
                }
            )

            assert result["success"] is False
            assert "error" in result
            assert "路径" in result["error"] or "Path" in result["error"]

            ide.close()

    @pytest.mark.asyncio
    async def test_ripgrep_error_handling(self, monkeypatch):
        """
        测试 ripgrep 错误处理 | Test ripgrep error handling
        """
        import subprocess

        def mock_run(*args, **kwargs):
            raise FileNotFoundError("ripgrep not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            ide = PythonIDE(
                root_dir=tmpdir,
                project_name="test",
                render_with_symbols=False,
            )

            tool = GrepTool(ide)

            result = await tool.execute(
                {
                    "pattern": "test",
                }
            )

            assert result["success"] is False
            assert "error" in result
            assert "ripgrep" in result["error"]

            ide.close()

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """
        测试异常处理 | Test exception handling
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            ide = PythonIDE(
                root_dir=tmpdir,
                project_name="test",
                render_with_symbols=False,
            )

            tool = GrepTool(ide)

            # 触发异常（例如，使用无效的正则表达式）
            result = await tool.execute(
                {
                    "pattern": "[invalid(regex",  # 无效的正则表达式
                }
            )

            # 应该返回错误而不是抛出异常
            assert "success" in result
            assert "error" in result or "matched" in result

            ide.close()
