# filename: test_write_tool.py
# @Time    : 2025/11/03 23:40
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
Write 工具测试 | Write Tool Tests

测试 Write 工具的各种功能
Tests various functionalities of the Write tool
"""

import os
import tempfile

import pytest

from ide4ai.a2c_smcp.tools.write import WriteTool
from ide4ai.python_ide.ide import PythonIDE


@pytest.fixture
def temp_workspace():
    """创建临时工作区 | Create temporary workspace"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def python_ide(temp_workspace):
    """创建 PythonIDE 实例 | Create PythonIDE instance"""
    ide = PythonIDE(
        root_dir=temp_workspace,
        project_name="test_write_project",
        cmd_time_out=10,
    )
    yield ide
    ide.close()


@pytest.fixture
def write_tool(python_ide):
    """创建 WriteTool 实例 | Create WriteTool instance"""
    return WriteTool(ide=python_ide)


@pytest.mark.asyncio
async def test_write_new_file(write_tool, temp_workspace):
    """测试写入新文件 | Test writing a new file"""
    file_path = os.path.join(temp_workspace, "test_new.py")

    result = await write_tool.execute(
        {
            "file_path": file_path,
            "content": "print('Hello, World!')\n",
        }
    )

    assert result["success"] is True
    assert "成功创建并写入文件" in result["message"]
    assert os.path.exists(file_path)

    # 验证文件内容 | Verify file content
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    assert content == "print('Hello, World!')\n"


@pytest.mark.asyncio
async def test_write_existing_file(write_tool, temp_workspace):
    """测试覆盖现有文件 | Test overwriting an existing file"""
    file_path = os.path.join(temp_workspace, "test_existing.py")

    # 先创建一个文件 | First create a file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("original content\n")

    # 覆盖文件 | Overwrite the file
    result = await write_tool.execute(
        {
            "file_path": file_path,
            "content": "new content\n",
        }
    )

    assert result["success"] is True
    assert "成功写入文件" in result["message"]

    # 验证文件内容已更新 | Verify file content is updated
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    assert content == "new content\n"


@pytest.mark.asyncio
async def test_write_empty_content(write_tool, temp_workspace):
    """测试写入空内容 | Test writing empty content"""
    file_path = os.path.join(temp_workspace, "test_empty.py")

    result = await write_tool.execute(
        {
            "file_path": file_path,
            "content": "",
        }
    )

    assert result["success"] is True
    assert os.path.exists(file_path)

    # 验证文件为空 | Verify file is empty
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    assert content == ""


@pytest.mark.asyncio
async def test_write_multiline_content(write_tool, temp_workspace):
    """测试写入多行内容 | Test writing multiline content"""
    file_path = os.path.join(temp_workspace, "test_multiline.py")

    content = """def hello():
    print('Hello')

def world():
    print('World')
"""

    result = await write_tool.execute(
        {
            "file_path": file_path,
            "content": content,
        }
    )

    assert result["success"] is True

    # 验证文件内容 | Verify file content
    with open(file_path, encoding="utf-8") as f:
        file_content = f.read()
    # 去除末尾可能的空白差异 | Remove potential trailing whitespace differences
    assert file_content.rstrip() == content.rstrip()


@pytest.mark.asyncio
async def test_write_with_subdirectory(write_tool, temp_workspace):
    """测试在子目录中写入文件 | Test writing file in subdirectory"""
    subdir = os.path.join(temp_workspace, "subdir")
    os.makedirs(subdir, exist_ok=True)

    file_path = os.path.join(subdir, "test_sub.py")

    result = await write_tool.execute(
        {
            "file_path": file_path,
            "content": "# Test file in subdirectory\n",
        }
    )

    assert result["success"] is True
    assert os.path.exists(file_path)


@pytest.mark.asyncio
async def test_write_invalid_path(write_tool):
    """测试写入无效路径 | Test writing to invalid path"""
    # 使用不存在的目录 | Use non-existent directory
    file_path = "/nonexistent/directory/test.py"

    result = await write_tool.execute(
        {
            "file_path": file_path,
            "content": "test content",
        }
    )

    # 应该失败 | Should fail
    assert result["success"] is False
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_write_missing_arguments(write_tool):
    """测试缺少必需参数 | Test missing required arguments"""
    result = await write_tool.execute(
        {
            "file_path": "/tmp/test.py",
            # 缺少 content 参数 | Missing content parameter
        }
    )

    assert result["success"] is False
    assert "参数验证失败" in result["error"]


@pytest.mark.asyncio
async def test_write_tool_properties(write_tool):
    """测试工具属性 | Test tool properties"""
    assert write_tool.name == "Write"
    assert "写入" in write_tool.description or "write" in write_tool.description.lower()
    assert "file_path" in write_tool.input_schema["properties"]
    assert "content" in write_tool.input_schema["properties"]
