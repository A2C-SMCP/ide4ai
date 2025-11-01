# filename: conftest.py
# @Time    : 2024/6/20 17:21
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from collections.abc import Generator
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from ide4ai.environment.terminal.command_filter import CommandFilterConfig
from ide4ai.python_ide.ide import PythonIDE


@pytest.fixture(scope="module")
def temp_dir():
    with TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture(scope="module")
def python_ide(temp_dir) -> Generator[PythonIDE, Any, None]:
    cmd_filter = CommandFilterConfig.from_white_list(["echo", "ls"])  # Safe commands
    ide = PythonIDE(root_dir=temp_dir, project_name="ai_editor_for_test", cmd_filter=cmd_filter)
    yield ide
    ide.close()
