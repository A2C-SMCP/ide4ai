# -*- coding: utf-8 -*-
# filename: test_mcp_bash_tool.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Bash 工具测试 | MCP Bash Tool Tests

测试 Bash 工具的基本功能
Tests basic functionality of Bash tool
"""

import pytest

from ide4ai.ides import PyIDESingleton
from ide4ai.python_ide.mcp.tools.bash import BashTool


@pytest.fixture
def ide_instance():
    """
    创建 IDE 实例 | Create IDE instance

    Returns:
        PythonIDE: IDE 实例 | IDE instance
    """
    ide_singleton = PyIDESingleton(
        cmd_white_list=["ls", "pwd", "echo"],
        root_dir=".",
        project_name="test-project",
    )
    return ide_singleton.ide


@pytest.fixture
def bash_tool(ide_instance):
    """
    创建 Bash 工具实例 | Create Bash tool instance

    Args:
        ide_instance: IDE 实例 | IDE instance

    Returns:
        BashTool: Bash 工具实例 | Bash tool instance
    """
    return BashTool(ide_instance)


def test_bash_tool_properties(bash_tool):
    """
    测试 Bash 工具的属性 | Test Bash tool properties

    Args:
        bash_tool: Bash 工具实例 | Bash tool instance
    """
    assert bash_tool.name == "Bash"
    assert isinstance(bash_tool.description, str)
    assert len(bash_tool.description) > 0

    # 检查 input schema | Check input schema
    schema = bash_tool.input_schema
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "command" in schema["properties"]


@pytest.mark.asyncio
async def test_bash_tool_execute_simple_command(bash_tool):
    """
    测试执行简单命令 | Test executing simple command

    Args:
        bash_tool: Bash 工具实例 | Bash tool instance
    """
    # 执行 echo 命令 | Execute echo command
    result = await bash_tool.execute({
        "command": "echo",
        "description": "Test echo command",
    })

    # 验证结果 | Verify result
    assert isinstance(result, dict)
    assert "success" in result
    assert "output" in result


@pytest.mark.asyncio
async def test_bash_tool_execute_with_timeout(bash_tool):
    """
    测试带超时的命令执行 | Test command execution with timeout

    Args:
        bash_tool: Bash 工具实例 | Bash tool instance
    """
    result = await bash_tool.execute({
        "command": "pwd",
        "timeout": 5000,  # 5 秒 | 5 seconds
        "description": "Get current directory",
    })

    assert isinstance(result, dict)
    assert "success" in result
    assert "metadata" in result


@pytest.mark.asyncio
async def test_bash_tool_invalid_input(bash_tool):
    """
    测试无效输入 | Test invalid input

    Args:
        bash_tool: Bash 工具实例 | Bash tool instance
    """
    # 缺少必需的 command 参数 | Missing required command parameter
    result = await bash_tool.execute({})

    # 应该返回错误 | Should return error
    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result


def test_bash_tool_input_schema_validation(bash_tool):
    """
    测试输入 Schema 验证 | Test input schema validation

    Args:
        bash_tool: Bash 工具实例 | Bash tool instance
    """
    from ide4ai.python_ide.mcp.schemas.tools import BashInput

    # 有效输入 | Valid input
    valid_input = BashInput(command="ls")
    assert valid_input.command == "ls"
    assert valid_input.timeout is None

    # 带超时的有效输入 | Valid input with timeout
    valid_input_with_timeout = BashInput(command="pwd", timeout=10000)
    assert valid_input_with_timeout.timeout == 10000

    # 无效超时（超过最大值）| Invalid timeout (exceeds max)
    with pytest.raises(Exception):
        BashInput(command="ls", timeout=700000)  # 超过 600000 | Exceeds 600000
