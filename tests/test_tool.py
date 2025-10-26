# -*- coding: utf-8 -*-
# filename: test_tool.py
# @Time    : 2024/6/18 13:28
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import os
import tempfile
from typing import Any, Generator
from unittest import mock

import pytest
from pydantic import AnyUrl

from tfrobot.drive.tool.ides.environment.workspace.model import TextModel
from tfrobot.drive.tool.ides.schema import LanguageId
from tfrobot.drive.tool.ides.tool import (
    EditOperation,
    EditPosition,
    EditRange,
    PyIDEApplyEdit,
    PyIDEApplySimpleEdit,
    PyIDEReadFile,
    SimpleEditOperation,
    construct_single_edit_operation,
)
from tfrobot.schema.exceptions import TFExecutionError


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


def test_construct_single_edit_operation(mock_text_model) -> None:
    """
    测试 construct_single_edit_operation 函数，其能力要求必须整行替换，所以当输入的参数其内容非整行时，抛出异常。
    """
    edit = {"range": {"start_position": [1, 1], "end_position": [1, 2]}, "new_text": "test"}
    with pytest.raises(TFExecutionError):
        construct_single_edit_operation(edit=edit, model=mock_text_model)


def test_apply_edit(mock_text_model) -> None:
    """
    测试 apply_edit 函数，其能力要求必须整行替换，所以当输���的参数其内容非整行时，抛出异常。
    """
    edit = EditOperation(
        range=EditRange(
            start_position=EditPosition(line=1, character=1), end_position=EditPosition(line=1, character=-1)
        ),
        new_text="test\n",
    )
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)
    apply_edit_tool = PyIDEApplyEdit(root_dir=dir_path, project_name="test")
    apply_edit_tool.run(tool_params={"uri": str(mock_text_model.uri), "edits": [edit.model_dump()]})
    with open(file_path, "r") as f:
        content = f.read()
        assert content == "test\n"


def test_apply_edit_delete(mock_text_model) -> None:
    """
    测试 PyIDEApplyEdit 工具中不提供 new_text（空字符串）时，视为删除操作。
    删除整个第一行后，文件内容应为空字符串。
    """
    edit = EditOperation(
        range=EditRange(
            start_position=EditPosition(line=1, character=1), end_position=EditPosition(line=1, character=-1)
        ),
        new_text="",  # 空文本表示删除
    )
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)

    # 预先确认文件内容
    with open(file_path, "r") as f:
        content_before = f.read()
    assert content_before == "hello world\n"

    apply_edit_tool = PyIDEApplyEdit(root_dir=dir_path, project_name="test")
    apply_edit_tool.run(tool_params={"uri": str(mock_text_model.uri), "edits": [edit.model_dump()]})

    with open(file_path, "r") as f:
        content_after = f.read()
    assert content_after == ""


def test_apply_simple_edit(mock_text_model) -> None:
    """
    测试 apply_edit 函数，其能力要求必须整行替换，所以当输���的参数其内容非整行时，抛出异常。
    """
    edit = SimpleEditOperation(
        start_line=1,
        end_line=1,
        new_text="test\n",
    )
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)
    apply_edit_tool = PyIDEApplySimpleEdit(root_dir=dir_path, project_name="test")
    apply_edit_tool.run(tool_params={"uri": str(mock_text_model.uri), "edits": [edit.model_dump()]})
    with open(file_path, "r") as f:
        content = f.read()
        assert content == "test\n"


def test_apply_simple_edit_delete(mock_text_model) -> None:
    """
    测试 PyIDEApplySimpleEdit 工具中不提供 new_text（空字符串）时，视为删除操作。
    删除指定行后，文件内容应为空字符串。
    """
    edit = SimpleEditOperation(start_line=1, end_line=1, new_text="")  # 空文本表示删除
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)

    with open(file_path, "r") as f:
        content_before = f.read()
    assert content_before == "hello world\n"

    apply_edit_tool = PyIDEApplySimpleEdit(root_dir=dir_path, project_name="test")
    apply_edit_tool.run(tool_params={"uri": str(mock_text_model.uri), "edits": [edit.model_dump()]})

    with open(file_path, "r") as f:
        content_after = f.read()
    assert content_after == ""


def test_apply_simple_edit_out_of_bound(mock_multiline_text_model) -> None:
    """
    测试 PyIDEApplySimpleEdit 工具的边界情况：
    对于一个有 3 行的文件，若编辑操作给出超出范围的行号（例如 start_line=-10, end_line=100），
    工具应自动修正到有效范围并替换整块内容。
    """
    # 对于 3 行文件：
    # - 输入 start_line=-10 将被修正为 1；
    # - 输入 end_line=100 将被修正为 3；
    edit = SimpleEditOperation(start_line=-10, end_line=100, new_text="new content\n")
    file_path = str(mock_multiline_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)

    apply_edit_tool = PyIDEApplySimpleEdit(root_dir=dir_path, project_name="test")
    apply_edit_tool.run(tool_params={"uri": str(mock_multiline_text_model.uri), "edits": [edit.model_dump()]})

    with open(file_path, "r", encoding="utf-8") as f:
        content_after = f.read()
    # 预期整个文件被替换为新内容
    assert content_after == "new content\n"


def test_apply_edit_no_edits(mock_text_model) -> None:
    """
    测试 PyIDEApplyEdit 工具在没有任何编辑操作时，文件内容应保持不变。
    """
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)

    with open(file_path, "r") as f:
        original_content = f.read()

    apply_edit_tool = PyIDEApplyEdit(root_dir=dir_path, project_name="test")
    # 无编辑操作
    apply_edit_tool.run(tool_params={"uri": str(mock_text_model.uri), "edits": []})

    with open(file_path, "r") as f:
        content_after = f.read()
    # 因为目前版本的IDE在自动保存后，会自动移除最后一行空格。这一行为是IDE实现的行为，因此测试对其兼容。如果想修复，需要IDE添加相应的Lint Format能力。
    assert content_after.rstrip("\n") == original_content.rstrip("\n"), "File content should remain unchanged."


def test_apply_simple_edit_no_edits(mock_text_model) -> None:
    """
    测试 PyIDEApplySimpleEdit 工具在没有任何编辑操作时，文件内容应保持不变。
    """
    file_path = str(mock_text_model.uri)[7:]
    dir_path = os.path.dirname(file_path)

    with open(file_path, "r") as f:
        original_content = f.read()

    apply_edit_tool = PyIDEApplySimpleEdit(root_dir=dir_path, project_name="test")
    apply_edit_tool.run(tool_params={"uri": str(mock_text_model.uri), "edits": []})

    with open(file_path, "r") as f:
        content_after = f.read()
    # 因为目前版本的IDE在自动保存后，会自动移除最后一行空格。这一行为是IDE实现的行为，因此测试对其兼容。如果想修复，需要IDE添加相应的Lint Format能力。
    assert content_after.rstrip("\n") == original_content.rstrip("\n"), "File content should remain unchanged."


def test_read_file_tool(mock_text_model) -> None:
    """
    测试 read_file_tool 函数，其能力要求必须整行替换，所以当输入的参数其内容非整行时，抛出异常。
    """
    file_path = str(mock_text_model.uri)[7:]
    with open(file_path, "w") as f:
        f.write("hello world\n")
    dir_path = os.path.dirname(file_path)
    read_file = PyIDEReadFile(root_dir=dir_path, project_name="test")
    # 模拟 os.path.getsize 返回一个大于20kB的值
    with mock.patch("os.path.getsize", return_value=101 * 1024):
        with pytest.raises(ValueError) as e:
            read_file.run(tool_params={"uri": str(mock_text_model.uri)})
    assert "File size exceeds the maximum limit of 100KB." in str(e.value)
