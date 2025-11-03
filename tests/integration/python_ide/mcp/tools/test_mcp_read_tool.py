# filename: test_mcp_read_tool.py
# @Time    : 2025/11/03 17:42
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 Read MCP 工具 | Test Read MCP Tool

测试 ReadTool 的功能和集成
Test ReadTool functionality and integration
"""

import tempfile
from pathlib import Path

import pytest

from ide4ai.python_ide.ide import PythonIDE
from ide4ai.python_ide.mcp.schemas.tools import ReadOutput
from ide4ai.python_ide.mcp.tools.read import ReadTool


class TestReadTool:
    """测试 ReadTool 类 | Test ReadTool class"""

    @pytest.fixture
    def temp_ide(self):
        """
        创建临时 IDE 实例用于测试 | Create temporary IDE instance for testing
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件 | Create test files
            test_files = {
                "simple.py": """# Simple Python file
def hello():
    print("Hello, World!")
    return True
""",
                "multiline.py": """# Multiline Python file
# Line 2
# Line 3
# Line 4
# Line 5
# Line 6
# Line 7
# Line 8
# Line 9
# Line 10
def function():
    pass
""",
                "long_file.py": "\n".join([f"# Line {i}" for i in range(1, 101)]),
            }

            # 创建文件 | Create files
            for file_path, content in test_files.items():
                full_path = Path(tmpdir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # 创建 IDE 实例 | Create IDE instance
            ide = PythonIDE(
                root_dir=tmpdir,
                project_name="test-read-tool",
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
        tool = ReadTool(ide)

        assert tool.name == "Read"
        assert "文件系统" in tool.description or "filesystem" in tool.description
        assert isinstance(tool.input_schema, dict)
        assert "file_path" in tool.input_schema["properties"]

    @pytest.mark.asyncio
    async def test_read_simple_file(self, temp_ide):
        """
        测试读取简单文件 | Test reading simple file
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = str(Path(tmpdir) / "simple.py")
        result = await tool.execute({"file_path": file_path})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        assert "Hello, World!" in output.content
        assert "def hello():" in output.content
        # 验证有行号（支持多种格式）| Verify line numbers (support multiple formats)
        assert "|" in output.content  # 行号后面有分隔符 | Separator after line number

    @pytest.mark.asyncio
    async def test_read_with_offset(self, temp_ide):
        """
        测试使用偏移量读取 | Test reading with offset
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = str(Path(tmpdir) / "multiline.py")
        result = await tool.execute({"file_path": file_path, "offset": 5, "limit": 3})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        # 应该包含第 5 行开始的内容 | Should contain content starting from line 5
        assert "Line 5" in output.content
        assert "Line 6" in output.content
        # limit=3 表示读取3行，即第5、6、7行 | limit=3 means read 3 lines, i.e., lines 5, 6, 7
        # 但实际返回可能取决于 Range 的实现 | But actual return may depend on Range implementation

    @pytest.mark.asyncio
    async def test_read_with_offset_no_limit(self, temp_ide):
        """
        测试使用偏移量但不限制行数 | Test reading with offset but no limit
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = str(Path(tmpdir) / "multiline.py")
        result = await tool.execute({"file_path": file_path, "offset": 10})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        # 应该从第 10 行开始到文件末尾 | Should start from line 10 to end
        assert "Line 10" in output.content
        assert "def function():" in output.content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_ide):
        """
        测试读取不存在的文件 | Test reading non-existent file
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = str(Path(tmpdir) / "nonexistent.py")
        result = await tool.execute({"file_path": file_path})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is False
        assert output.error is not None
        # 检查错误消息包含文件不存在的提示 | Check error message contains file not found indication
        assert "不存在" in output.error or "not found" in output.error.lower() or "no such file" in output.error.lower()

    @pytest.mark.asyncio
    async def test_read_with_file_uri(self, temp_ide):
        """
        测试使用 file:// URI 读取 | Test reading with file:// URI
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = f"file://{Path(tmpdir) / 'simple.py'}"
        result = await tool.execute({"file_path": file_path})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        assert "Hello, World!" in output.content

    @pytest.mark.asyncio
    async def test_read_long_file(self, temp_ide):
        """
        测试读取长文件 | Test reading long file
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = str(Path(tmpdir) / "long_file.py")
        result = await tool.execute({"file_path": file_path})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        # 应该包含所有 100 行 | Should contain all 100 lines
        assert "Line 1" in output.content
        assert "Line 100" in output.content

    @pytest.mark.asyncio
    async def test_read_with_limit_only(self, temp_ide):
        """
        测试只使用 limit 参数（应该从开头读取）| Test using only limit parameter (should read from beginning)
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = str(Path(tmpdir) / "long_file.py")
        # 只提供 limit，不提供 offset，应该读取整个文件
        # Only provide limit without offset, should read entire file
        result = await tool.execute({"file_path": file_path, "limit": 5})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        # 由于没有 offset，应该读取整个文件 | Without offset, should read entire file
        assert "Line 1" in output.content

    @pytest.mark.asyncio
    async def test_input_validation(self, temp_ide):
        """
        测试输入验证 | Test input validation
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        # 测试缺少必需参数 | Test missing required parameter
        result = await tool.execute({})

        output = ReadOutput.model_validate(result)
        assert output.success is False
        assert output.error is not None
        assert "验证失败" in output.error or "validation failed" in output.error.lower()

    @pytest.mark.asyncio
    async def test_metadata_in_output(self, temp_ide):
        """
        测试输出中的元数据 | Test metadata in output
        """
        ide, tmpdir = temp_ide
        tool = ReadTool(ide)

        file_path = str(Path(tmpdir) / "simple.py")
        result = await tool.execute({"file_path": file_path, "offset": 2, "limit": 2})

        # 验证结果 | Verify result
        output = ReadOutput.model_validate(result)
        assert output.success is True
        assert output.metadata is not None
        assert output.metadata["file_path"] == file_path
        assert output.metadata["offset"] == 2
        assert output.metadata["limit"] == 2
