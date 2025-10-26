# filename: conftest.py
# @Time    : 2024/6/20 17:21
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from collections.abc import Generator
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from tfrobot.drive.tool.ides.python_ide.ide import PythonIDE
from tfrobot.drive.tool.ides.tool import (
    PyAIEditor,
    PyGPTEditor,
    PyIDEApplyEdit,
    PyIDEApplySimpleEdit,
    PyIDECreateFile,
    PyIDEOpenFile,
    PyIDEReadFile,
    PyOllamaEditor,
)


@pytest.fixture(scope="module")
def temp_dir():
    with TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture(scope="module")
def python_ide(temp_dir) -> Generator[PythonIDE, Any, None]:
    cmd_white_list = ["echo", "ls"]  # Safe commands
    ide = PythonIDE(cmd_white_list, temp_dir, "ai_editor_for_test")
    yield ide
    ide.close()


@pytest.fixture(scope="module")
def create_file_tool(python_ide, temp_dir) -> Generator[PyIDECreateFile, Any, None]:
    assert python_ide is not None
    t = PyIDECreateFile(root_dir=temp_dir, project_name="ai_editor_for_test")
    yield t


@pytest.fixture(scope="module")
def open_file_tool(python_ide, temp_dir) -> Generator[PyIDEOpenFile, Any, None]:
    assert python_ide is not None
    t = PyIDEOpenFile(root_dir=temp_dir, project_name="ai_editor_for_test")
    yield t


@pytest.fixture(scope="module")
def read_file_tool(python_ide, temp_dir) -> Generator[PyIDEReadFile, Any, None]:
    assert python_ide is not None
    t = PyIDEReadFile(root_dir=temp_dir, project_name="ai_editor_for_test")
    yield t


@pytest.fixture(scope="module")
def apply_edits_tool(python_ide, temp_dir) -> Generator[PyIDEApplyEdit, Any, None]:
    assert python_ide is not None
    t = PyIDEApplyEdit(root_dir=temp_dir, project_name="ai_editor_for_test")
    yield t


@pytest.fixture(scope="module")
def apply_simple_edits_tool(python_ide, temp_dir) -> Generator[PyIDEApplySimpleEdit, Any, None]:
    assert python_ide is not None
    t = PyIDEApplySimpleEdit(root_dir=temp_dir, project_name="ai_editor_for_test")
    yield t


@pytest.fixture(scope="module")
def ai_editor(python_ide, temp_dir) -> Generator[PyAIEditor, Any, None]:
    assert python_ide is not None
    yield PyAIEditor(project_name="ai_editor_for_test", root_dir=temp_dir)


@pytest.fixture(scope="module")
def gpt_editor(python_ide, temp_dir) -> Generator[PyGPTEditor, Any, None]:
    assert python_ide is not None
    yield PyGPTEditor(project_name="gpt_editor_for_test", root_dir=temp_dir, model="gpt-4o-mini")


@pytest.fixture(scope="module")
def ollama_editor(python_ide, temp_dir) -> Generator[PyOllamaEditor, Any, None]:
    assert python_ide is not None
    yield PyOllamaEditor(project_name="ollama_editor_for_test", root_dir=temp_dir, model="qwq")
