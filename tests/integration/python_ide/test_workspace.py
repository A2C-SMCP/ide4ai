# filename: test_workspace.py
# @Time    : 2024/5/9 19:32
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import os
from collections.abc import Generator
from typing import Any

import pytest
from pydantic import AnyUrl

from ai_ide.environment.workspace.schema import (
    Position,
    Range,
    SingleEditOperation,
)
from ai_ide.python_ide.const import DEFAULT_SYMBOL_VALUE_SET
from ai_ide.python_ide.workspace import PyWorkspace


@pytest.fixture
def project_root_dir() -> str:
    return os.path.dirname(__file__) + "/virtual_project"


@pytest.fixture
def py_workspace(project_root_dir) -> Generator[PyWorkspace, Any, None]:
    workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_python_workspace")
    yield workspace
    workspace.close()


def test_py_workspace_init(py_workspace) -> None:
    """
    测试PyWorkspace初始化
    Args:
        py_workspace:

    Returns:

    """
    assert py_workspace is not None


def test_py_workspace_read_file(project_root_dir, py_workspace) -> None:
    test_file_path = project_root_dir + "/file_for_test_read.py"
    test_file_uri = "file://" + test_file_path
    content = py_workspace.read_file(uri=test_file_uri)
    print(content)
    with open(test_file_path) as f:
        read_res = f.read()
    assert read_res[:20] in content  # 因为文件较大，直接使用in判断会比较慢，所以截取20个字符做判断
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(content)
    print(f"内容长度: {len(tokens)}")


def test_py_workspace_render(project_root_dir, py_workspace) -> None:
    """
    测试PyWorkspace渲染

    测试激活Model，测试渲染环境
    Args:
        project_root_dir:
        py_workspace:

    Returns:

    """
    render_1 = project_root_dir + "/file_for_render_1.py"
    current_file = project_root_dir + "/file_for_test_read.py"
    py_workspace.open_file(uri=f"file://{render_1}")
    py_workspace.open_file(uri=f"file://{current_file}")
    assert AnyUrl(f"file://{current_file}") == py_workspace.active_models[-1].uri
    py_workspace.active_model(py_workspace.get_model(uri=f"file://{render_1}").m_id)
    assert AnyUrl(f"file://{render_1}") == py_workspace.active_models[-1].uri
    py_workspace.active_model(py_workspace.get_model(uri=f"file://{current_file}").m_id)
    text = py_workspace.render()
    assert "当前工作区" in text and "Class: LSPCommand" in text


def test_py_workspace_create_and_apply_edit(project_root_dir, py_workspace) -> None:
    """
    测试PyWorkspace应用编辑

    Args:
        project_root_dir:
        py_workspace:

    Returns:

    """
    test_file_path = project_root_dir + "/file_for_edit.py"
    test_file_uri = "file://" + test_file_path
    py_workspace.open_file(uri=test_file_uri)
    symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
    print(symbols)
    assert "Class: A" in symbols
    new_text = "class B:\n    b: int\n    c: int"
    edit = SingleEditOperation(
        range=Range(start_position=Position(9, 1), end_position=Position(10, 11)),
        text=new_text,
    )
    edit_res = py_workspace.apply_edit(uri=test_file_uri, edits=[edit], compute_undo_edits=True)
    symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
    print(symbols)
    assert "Class: B" in symbols
    undo_edit = py_workspace.apply_edit(
        uri=test_file_uri,
        edits=[e.to_single_edit_operation() for e in edit_res],
        compute_undo_edits=False,
    )
    assert not undo_edit
    symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
    print(symbols)
    assert "Class: A" in symbols


@pytest.fixture
def file_uri(project_root_dir) -> str:
    return f"file://{project_root_dir}/testfile.py"


def test_create_file_success(py_workspace, file_uri) -> None:
    """
    测试成功创建一个新文件。
    """
    tm = py_workspace.create_file(uri=file_uri)
    assert tm is not None
    assert os.path.exists(file_uri[7:])  # Removing 'file://' prefix


def test_create_file_with_init_content(py_workspace, file_uri) -> None:
    """
    测试创建文件时指定初始内容。
    """
    tm = py_workspace.create_file(uri=file_uri, init_content="print('Hello, World!')")
    tm.save()
    assert tm is not None
    assert os.path.exists(file_uri[7:])
    with open(file_uri[7:]) as f:
        content = f.read()
    assert content.endswith("print('Hello, World!')") and content.startswith("# -*- coding: utf-8 -*-")


def test_create_file_with_not_header_generator(project_root_dir, file_uri) -> None:
    """如果PyWorkspace没有header_generator，不会添加文件头"""
    py_workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_python_workspace", header_generators={})
    try:
        tm = py_workspace.create_file(uri=file_uri, init_content="print('Hello, World!')")
        tm.save()
        assert tm is not None
        assert os.path.exists(file_uri[7:])
        with open(file_uri[7:]) as f:
            content = f.read()
        assert content.endswith("print('Hello, World!')") and content.startswith("print('Hello, World!')")
    finally:
        py_workspace.close()


def test_overwrite_existing_file(py_workspace, file_uri) -> None:
    """
    测试如果文件存在，设置overwrite=True后能成功覆盖文件。
    """
    # 先创建一个文件
    py_workspace.create_file(uri=file_uri)
    # 再次创建同一文件并尝试覆盖
    tm = py_workspace.create_file(uri=file_uri, overwrite=True)
    assert tm is not None
    assert os.path.exists(file_uri[7:])


def test_ignore_existing_file(py_workspace, file_uri) -> None:
    """
    测试如果文件存在，并设置ignore_if_exists=True，不进行任何操作。
    """
    # 先创建一个文件
    py_workspace.create_file(uri=file_uri)
    # 再次创建同一文件并设置忽略存在的文件
    tm = py_workspace.create_file(uri=file_uri, ignore_if_exists=True)
    assert tm is None


def test_error_when_file_exists_without_overwrite(py_workspace, file_uri) -> None:
    """
    测试文件已存在且没有设置覆盖时应抛出异常。
    """
    # 先创建一个文件
    py_workspace.create_file(uri=file_uri)
    # 再次创建同一文件，没有设置overwrite或ignore_if_exists
    with pytest.raises(FileExistsError):
        py_workspace.create_file(uri=file_uri)


def test_handle_creation_error(py_workspace, file_uri, monkeypatch) -> None:
    """
    测试创建文件时发生错误（如权限问题）。
    """

    def mock_open(*args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr("builtins.open", mock_open)
    with pytest.raises(IOError) as exc_info:
        py_workspace.create_file(uri=file_uri)
    assert "Permission denied" in str(exc_info.value)


# 使用fixture清理创建的文件
@pytest.fixture(autouse=True)
def clean_up(file_uri):
    yield
    file_path = file_uri[7:]
    if os.path.exists(file_path):
        os.remove(file_path)


def test_step_open_file_success(py_workspace, project_root_dir):
    action = {
        "category": "workspace",
        "action_name": "open_file",
        "action_args": {"uri": f"file://{project_root_dir}/file_for_test_read.py"},
    }
    observation, reward, done, success, _ = py_workspace.step(action)
    assert success is True
    assert reward == 100
    assert done is True
    assert "ACTION_CATEGORY_MAP: dict[int, str] = {" in observation["obs"]


def test_step_apply_edit_success(py_workspace, project_root_dir):
    action = {
        "category": "workspace",
        "action_name": "apply_edit",
        "action_args": {
            "uri": f"file://{project_root_dir}/file_for_test.py",
            "edits": [],
        },
    }
    observation, reward, done, success, _ = py_workspace.step(action)
    assert success is False
    assert reward == 0
    assert done is True
