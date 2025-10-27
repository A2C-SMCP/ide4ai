# filename: test_claude_tool.py
# @Time    : 2025/4/25 11:50
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import tempfile
from collections.abc import Generator
from typing import Any

import pytest
from pydantic import AnyUrl

from ai_ide.environment.workspace.model import TextModel
from ai_ide.schema import LanguageId


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
