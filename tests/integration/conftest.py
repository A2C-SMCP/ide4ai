# filename: conftest.py
# @Time    : 2024/6/20 17:21
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from collections.abc import Generator
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from ide4ai.python_ide.ide import PythonIDE


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
