# filename: test_claude_tool.py
# @Time    : 2025/4/25 11:50
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import os
import tempfile
from collections.abc import Generator
from typing import Any

import pytest
from pydantic import AnyUrl
from src.ai_ide.claude_tool import ClaudeEditorTool

from src.ai_ide.environment.workspace.model import TextModel
from src.ai_ide.schema import LanguageId


@pytest.fixture
def mock_text_model() -> Generator[TextModel, Any, None]:
    """
    构建一个测试用的代码模型对象。

    Returns:
        TextModel: 代码模型对象
    """
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"hello world\n")
        f.flush()
        model = TextModel(language_id=LanguageId.python, uri=AnyUrl(f"file://{f.name}"))
        yield model


@pytest.fixture
def mock_multiline_text_model() -> Generator[TextModel, Any, None]:
    """
    构建一个测试用的多行代码模型对象。

    Returns:
        TextModel: 代码模型对象
    """
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"hello world\n")
        f.write(b"hello world\n")
        f.flush()
        model = TextModel(language_id=LanguageId.python, uri=AnyUrl(f"file://{f.name}"))
        yield model


def test_view_file(mock_text_model: TextModel) -> None:
    """
    测试查看文件的功能。
    """
    # 模拟查看文件的操作
    tool_params = {
        "command": "view",
        "path": str(mock_text_model.uri),
    }
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)
    tool = ClaudeEditorTool(root_dir=dir_path, project_name="test_project")
    res = tool.run(tool_params=tool_params)
    print(res)


def test_str_replace(mock_text_model: TextModel) -> None:
    """
    测试字符串替换的功能。
    """
    # 模拟字符串替换的操作
    tool_params = {
        "command": "str_replace",
        "path": str(mock_text_model.uri),
        "old_str": "hello",
        "new_str": "hi",
    }
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)
    tool = ClaudeEditorTool(root_dir=dir_path, project_name="test_project")
    _ = tool.run(tool_params=tool_params)
    # 检查文件内容是否被替换
    with open(file_path) as f:
        content = f.read()
        assert "hi world" in content
        assert "hello world" not in content
        print("---after-replace---")
        print(content)
    undo_params = {
        "command": "undo_edit",
        "path": str(mock_text_model.uri),
    }
    _ = tool.run(tool_params=undo_params)
    # 检查文件内容是否被还原
    with open(file_path) as f:
        content = f.read()
        assert "hello world" in content
        assert "hi world" not in content
        print("---after-undo---")
        print(content)


# 使用insert命令在两行之间插入一行
def test_insert_line(mock_multiline_text_model: TextModel) -> None:
    """
    测试在两行之间插入一行的功能。
    """
    # 模拟插入行的操作
    tool_params = {
        "command": "insert",
        "path": str(mock_multiline_text_model.uri),
        "insert_line": 1,
        "new_str": "inserted line\n",
    }
    file_path = str(mock_multiline_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)
    tool = ClaudeEditorTool(root_dir=dir_path, project_name="test_project")
    _ = tool.run(tool_params=tool_params)
    # 检查文件内容是否被插入
    with open(file_path) as f:
        content = f.read()
        assert "inserted line" in content
        print("---after-insert---")
        print(content)
    undo_params = {
        "command": "undo_edit",
        "path": str(mock_multiline_text_model.uri),
    }
    _ = tool.run(tool_params=undo_params)
    # 检查文件内容是否被还原
    with open(file_path) as f:
        content = f.read()
        assert "inserted line" not in content
        print("---after-undo---")
        print(content)
