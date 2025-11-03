# filename: test_mcp_edit_tool.py
# @Time    : 2025/11/03 18:05
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 Edit MCP 工具 | Test Edit MCP Tool

测试 EditTool 的功能和集成
Test EditTool functionality and integration
"""

import tempfile
from pathlib import Path

import pytest

from ide4ai.a2c_smcp.schemas import EditOutput
from ide4ai.a2c_smcp.tools.edit import EditTool
from ide4ai.python_ide.ide import PythonIDE


class TestEditTool:
    """测试 EditTool 类 | Test EditTool class"""

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
                "duplicate.py": """# File with duplicate strings
def function1():
    value = "test"
    return value

def function2():
    value = "test"
    return value
""",
                "multiline.py": """# Multiline replacement test
def old_function():
    pass

class OldClass:
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
                project_name="test-edit-tool",
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
        tool = EditTool(ide)

        assert tool.name == "Edit"
        assert "字符串替换" in tool.description or "string replacement" in tool.description.lower()
        assert isinstance(tool.input_schema, dict)
        assert "file_path" in tool.input_schema["properties"]
        assert "old_string" in tool.input_schema["properties"]
        assert "new_string" in tool.input_schema["properties"]

    @pytest.mark.asyncio
    async def test_simple_replacement(self, temp_ide):
        """
        测试简单替换 | Test simple replacement
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "simple.py")
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": "Hello, World!",
                "new_string": "Hello, Python!",
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        assert output.replacements_made == 1
        assert "成功" in output.message or "success" in output.message.lower()

        # 验证文件内容已更改 | Verify file content changed
        content = ide.workspace.read_file(uri=f"file://{file_path}", with_line_num=False)
        assert "Hello, Python!" in content
        assert "Hello, World!" not in content

    @pytest.mark.asyncio
    async def test_multiline_replacement(self, temp_ide):
        """
        测试多行替换 | Test multiline replacement
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "multiline.py")
        # 替换类名 | Replace class name
        old_string = "class OldClass:"
        new_string = "class NewClass:"

        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": old_string,
                "new_string": new_string,
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        assert output.replacements_made == 1

        # 验证文件内容已更改 | Verify file content changed
        content = ide.workspace.read_file(uri=f"file://{file_path}", with_line_num=False)
        assert "NewClass" in content
        assert "OldClass" not in content

    @pytest.mark.asyncio
    async def test_duplicate_without_replace_all(self, temp_ide):
        """
        测试重复字符串但不使用 replace_all | Test duplicate strings without replace_all
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "duplicate.py")
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": '"test"',
                "new_string": '"updated"',
                "replace_all": False,
            },
        )

        # 验证结果 - 应该失败因为有多个匹配 | Verify result - should fail due to multiple matches
        output = EditOutput.model_validate(result)
        assert output.success is False
        assert output.error is not None
        assert "不唯一" in output.error or "not unique" in output.error.lower()
        assert output.replacements_made == 0

    @pytest.mark.asyncio
    async def test_duplicate_with_replace_all(self, temp_ide):
        """
        测试重复字符串使用 replace_all | Test duplicate strings with replace_all
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "duplicate.py")
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": '"test"',
                "new_string": '"updated"',
                "replace_all": True,
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        assert output.replacements_made == 2  # 应该替换两处 | Should replace 2 occurrences

        # 验证文件内容已更改 | Verify file content changed
        content = ide.workspace.read_file(uri=f"file://{file_path}", with_line_num=False)
        assert '"updated"' in content
        assert '"test"' not in content

    @pytest.mark.asyncio
    async def test_string_not_found(self, temp_ide):
        """
        测试字符串未找到 | Test string not found
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "simple.py")
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": "NonExistentString",
                "new_string": "NewString",
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is False
        assert output.error is not None
        assert "未找到" in output.error or "not found" in output.error.lower()
        assert output.replacements_made == 0

    @pytest.mark.asyncio
    async def test_file_not_found(self, temp_ide):
        """
        测试文件不存在 | Test file not found
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "nonexistent.py")
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": "old",
                "new_string": "new",
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is False
        assert output.error is not None
        assert "不存在" in output.error or "not found" in output.error.lower()

    @pytest.mark.asyncio
    async def test_identical_strings(self, temp_ide):
        """
        测试 old_string 和 new_string 相同 | Test identical old_string and new_string
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "simple.py")
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": "Hello, World!",
                "new_string": "Hello, World!",
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is False
        assert output.error is not None
        assert "不能相同" in output.error or "cannot be identical" in output.error.lower()

    @pytest.mark.asyncio
    async def test_with_file_uri(self, temp_ide):
        """
        测试使用 file:// URI | Test with file:// URI
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = f"file://{Path(tmpdir) / 'simple.py'}"
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": "Hello, World!",
                "new_string": "Hello, Universe!",
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is True
        assert output.error is None
        assert output.replacements_made == 1

    @pytest.mark.asyncio
    async def test_input_validation(self, temp_ide):
        """
        测试输入验证 | Test input validation
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        # 测试缺少必需参数 | Test missing required parameters
        result = await tool.execute({"file_path": "/tmp/test.py"})

        output = EditOutput.model_validate(result)
        assert output.success is False
        assert output.error is not None
        assert "验证失败" in output.error or "validation failed" in output.error.lower()

    @pytest.mark.asyncio
    async def test_metadata_in_output(self, temp_ide):
        """
        测试输出中的元数据 | Test metadata in output
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "simple.py")
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": "Hello, World!",
                "new_string": "Hello, Test!",
                "replace_all": False,
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is True
        assert output.metadata is not None
        assert output.metadata["file_path"] == file_path
        assert output.metadata["replace_all"] is False
        assert "undo_edits" in output.metadata

    @pytest.mark.asyncio
    async def test_preserve_indentation(self, temp_ide):
        """
        测试保留缩进 | Test preserve indentation
        """
        ide, tmpdir = temp_ide
        tool = EditTool(ide)

        file_path = str(Path(tmpdir) / "simple.py")
        # 替换带缩进的代码 | Replace code with indentation
        result = await tool.execute(
            {
                "file_path": file_path,
                "old_string": '    print("Hello, World!")',
                "new_string": '    print("Goodbye, World!")',
            },
        )

        # 验证结果 | Verify result
        output = EditOutput.model_validate(result)
        assert output.success is True
        assert output.replacements_made == 1

        # 验证缩进被保留 | Verify indentation is preserved
        content = ide.workspace.read_file(uri=f"file://{file_path}", with_line_num=False)
        assert '    print("Goodbye, World!")' in content
