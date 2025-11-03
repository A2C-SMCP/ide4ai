# filename: test_notebook_edit_tool.py
# @Time    : 2025/11/03 23:40
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
NotebookEdit 工具测试 | NotebookEdit Tool Tests

测试 NotebookEdit 工具的各种功能
Tests various functionalities of the NotebookEdit tool
"""

import json
import os
import tempfile

import pytest

from ide4ai.python_ide.a2c_smcp.tools.notebook_edit import NotebookEditTool
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
        project_name="test_notebook_project",
        cmd_time_out=10,
    )
    yield ide
    ide.close()


@pytest.fixture
def notebook_edit_tool(python_ide):
    """创建 NotebookEditTool 实例 | Create NotebookEditTool instance"""
    return NotebookEditTool(ide=python_ide)


@pytest.fixture
def sample_notebook(temp_workspace):
    """创建示例 notebook 文件 | Create sample notebook file"""
    notebook_path = os.path.join(temp_workspace, "test_notebook.ipynb")

    notebook_data = {
        "cells": [
            {
                "id": "cell-1",
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["print('Hello, World!')\n"],
            },
            {
                "id": "cell-2",
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Title\n", "\n", "Some text\n"],
            },
            {
                "id": "cell-3",
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["x = 42\n", "print(x)\n"],
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    with open(notebook_path, "w", encoding="utf-8") as f:
        json.dump(notebook_data, f, indent=1)
        f.write("\n")

    return notebook_path


@pytest.mark.asyncio
async def test_replace_cell_content(notebook_edit_tool, sample_notebook):
    """测试替换单元格内容 | Test replacing cell content"""
    result = await notebook_edit_tool.execute(
        {
            "notebook_path": sample_notebook,
            "cell_id": "cell-1",
            "new_source": "print('Hello, Python!')\n",
            "edit_mode": "replace",
        }
    )

    assert result["success"] is True
    assert "成功替换" in result["message"]

    # 验证 notebook 内容 | Verify notebook content
    with open(sample_notebook, encoding="utf-8") as f:
        notebook_data = json.load(f)

    assert notebook_data["cells"][0]["source"] == ["print('Hello, Python!')\n"]


@pytest.mark.asyncio
async def test_insert_new_cell(notebook_edit_tool, sample_notebook):
    """测试插入新单元格 | Test inserting new cell"""
    result = await notebook_edit_tool.execute(
        {
            "notebook_path": sample_notebook,
            "cell_id": "cell-1",
            "new_source": "# New cell\nprint('Inserted')\n",
            "cell_type": "code",
            "edit_mode": "insert",
        }
    )

    assert result["success"] is True
    assert "成功在位置" in result["message"]
    assert result["metadata"]["total_cells"] == 4

    # 验证新单元格已插入 | Verify new cell is inserted
    with open(sample_notebook, encoding="utf-8") as f:
        notebook_data = json.load(f)

    assert len(notebook_data["cells"]) == 4
    # 新单元格应该在 cell-1 之后（索引 1）| New cell should be after cell-1 (index 1)
    assert notebook_data["cells"][1]["source"] == ["# New cell\n", "print('Inserted')\n"]
    assert notebook_data["cells"][1]["cell_type"] == "code"


@pytest.mark.asyncio
async def test_delete_cell(notebook_edit_tool, sample_notebook):
    """测试删除单元格 | Test deleting cell"""
    result = await notebook_edit_tool.execute(
        {
            "notebook_path": sample_notebook,
            "cell_id": "cell-2",
            "new_source": "",  # 删除模式下此参数会被忽略 | This parameter is ignored in delete mode
            "edit_mode": "delete",
        }
    )

    assert result["success"] is True
    assert "成功删除" in result["message"]
    assert result["metadata"]["total_cells"] == 2

    # 验证单元格已删除 | Verify cell is deleted
    with open(sample_notebook, encoding="utf-8") as f:
        notebook_data = json.load(f)

    assert len(notebook_data["cells"]) == 2
    # cell-2 应该已被删除 | cell-2 should be deleted
    cell_ids = [cell.get("id") for cell in notebook_data["cells"]]
    assert "cell-2" not in cell_ids


@pytest.mark.asyncio
async def test_change_cell_type(notebook_edit_tool, sample_notebook):
    """测试更改单元格类型 | Test changing cell type"""
    result = await notebook_edit_tool.execute(
        {
            "notebook_path": sample_notebook,
            "cell_id": "cell-1",
            "new_source": "# This is now markdown\n",
            "cell_type": "markdown",
            "edit_mode": "replace",
        }
    )

    assert result["success"] is True

    # 验证单元格类型已更改 | Verify cell type is changed
    with open(sample_notebook, encoding="utf-8") as f:
        notebook_data = json.load(f)

    assert notebook_data["cells"][0]["cell_type"] == "markdown"
    assert notebook_data["cells"][0]["source"] == ["# This is now markdown\n"]
    # code 特有字段应该被删除 | Code-specific fields should be removed
    assert "execution_count" not in notebook_data["cells"][0]
    assert "outputs" not in notebook_data["cells"][0]


@pytest.mark.asyncio
async def test_insert_at_beginning(notebook_edit_tool, sample_notebook):
    """测试在开头插入单元格 | Test inserting cell at beginning"""
    result = await notebook_edit_tool.execute(
        {
            "notebook_path": sample_notebook,
            "cell_id": None,  # None 表示插入到开头 | None means insert at beginning
            "new_source": "# First cell\n",
            "cell_type": "markdown",
            "edit_mode": "insert",
        }
    )

    assert result["success"] is True

    # 验证新单元格在开头 | Verify new cell is at beginning
    with open(sample_notebook, encoding="utf-8") as f:
        notebook_data = json.load(f)

    assert len(notebook_data["cells"]) == 4
    assert notebook_data["cells"][0]["source"] == ["# First cell\n"]
    assert notebook_data["cells"][0]["cell_type"] == "markdown"


@pytest.mark.asyncio
async def test_notebook_not_found(notebook_edit_tool, temp_workspace):
    """测试 notebook 文件不存在 | Test notebook file not found"""
    non_existent_path = os.path.join(temp_workspace, "non_existent.ipynb")

    result = await notebook_edit_tool.execute(
        {
            "notebook_path": non_existent_path,
            "cell_id": "cell-1",
            "new_source": "test",
            "edit_mode": "replace",
        }
    )

    assert result["success"] is False
    assert "文件不存在" in result["error"] or "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_invalid_cell_id(notebook_edit_tool, sample_notebook):
    """测试无效的 cell_id | Test invalid cell_id"""
    result = await notebook_edit_tool.execute(
        {
            "notebook_path": sample_notebook,
            "cell_id": "non-existent-cell",
            "new_source": "test",
            "edit_mode": "replace",
        }
    )

    assert result["success"] is False
    assert "未找到" in result["error"] or "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_insert_without_cell_type(notebook_edit_tool, sample_notebook):
    """测试插入模式下缺少 cell_type | Test insert mode without cell_type"""
    result = await notebook_edit_tool.execute(
        {
            "notebook_path": sample_notebook,
            "cell_id": "cell-1",
            "new_source": "test",
            "edit_mode": "insert",
            # 缺少 cell_type | Missing cell_type
        }
    )

    assert result["success"] is False
    assert "cell_type" in result["error"]


@pytest.mark.asyncio
async def test_invalid_file_format(notebook_edit_tool, temp_workspace):
    """测试无效的文件格式 | Test invalid file format"""
    # 创建一个非 .ipynb 文件 | Create a non-.ipynb file
    invalid_path = os.path.join(temp_workspace, "test.txt")
    with open(invalid_path, "w") as f:
        f.write("not a notebook")

    result = await notebook_edit_tool.execute(
        {
            "notebook_path": invalid_path,
            "cell_id": "cell-1",
            "new_source": "test",
            "edit_mode": "replace",
        }
    )

    assert result["success"] is False
    assert ".ipynb" in result["error"]


@pytest.mark.asyncio
async def test_notebook_edit_tool_properties(notebook_edit_tool):
    """测试工具属性 | Test tool properties"""
    assert notebook_edit_tool.name == "NotebookEdit"
    assert "notebook" in notebook_edit_tool.description.lower() or "Jupyter" in notebook_edit_tool.description
    assert "notebook_path" in notebook_edit_tool.input_schema["properties"]
    assert "cell_id" in notebook_edit_tool.input_schema["properties"]
    assert "new_source" in notebook_edit_tool.input_schema["properties"]
    assert "edit_mode" in notebook_edit_tool.input_schema["properties"]
