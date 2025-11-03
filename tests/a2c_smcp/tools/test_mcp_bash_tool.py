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
from pydantic import ValidationError

from ide4ai.a2c_smcp.tools import BashTool
from ide4ai.environment.terminal.command_filter import CommandFilterConfig
from ide4ai.ides import PyIDESingleton


@pytest.fixture
def ide_instance():
    """
    创建 IDE 实例 | Create IDE instance

    Returns:
        PythonIDE: IDE 实例 | IDE instance
    """
    ide_singleton = PyIDESingleton(
        root_dir="../../../integration/python_ide",
        project_name="test-project",
        cmd_filter=CommandFilterConfig.from_white_list(["ls", "pwd", "echo"]),
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
    result = await bash_tool.execute(
        {
            "command": "echo",
            "description": "Test echo command",
        },
    )

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
    result = await bash_tool.execute(
        {
            "command": "pwd",
            "timeout": 5000,  # 5 秒 | 5 seconds
            "description": "Get current directory",
        },
    )

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
    from ide4ai.a2c_smcp.schemas import BashInput

    # 有效输入 | Valid input
    valid_input = BashInput(command="ls")
    assert valid_input.command == "ls"
    assert valid_input.timeout is None

    # 带超时的有效输入 | Valid input with timeout
    valid_input_with_timeout = BashInput(command="pwd", timeout=10000)
    assert valid_input_with_timeout.timeout == 10000

    # 无效超时（超过最大值）| Invalid timeout (exceeds max)
    with pytest.raises(ValidationError):
        BashInput(command="ls", timeout=700000)  # 超过 600000 | Exceeds 600000


@pytest.mark.asyncio
async def test_bash_tool_output_truncation(bash_tool):
    """
    测试输出截断功能 | Test output truncation functionality

    当命令输出超过 30000 字符时，应该被截断
    When command output exceeds 30000 characters, it should be truncated

    Args:
        bash_tool: Bash 工具实例 | Bash tool instance
    """
    # 生成一个超过 30000 字符的输出
    # Generate output exceeding 30000 characters
    # 使用 echo 命令生成大量文本（40000 字符）
    # Use echo command to generate large text (40000 characters)
    large_text = "x" * 40000

    result = await bash_tool.execute(
        {
            "command": "echo",
            "args": large_text,
            "description": "Generate large output for truncation test",
        },
    )

    # 验证结果 | Verify result
    assert isinstance(result, dict)
    assert "output" in result
    assert "metadata" in result

    # 检查输出是否被截断 | Check if output was truncated
    output_length = len(result["output"])
    assert output_length <= bash_tool.MAX_OUTPUT_LENGTH, f"输出长度 {output_length} 超过了最大限制 {bash_tool.MAX_OUTPUT_LENGTH}"

    # 检查 metadata 中的截断标记 | Check truncation flag in metadata
    if result["metadata"].get("truncated"):
        assert result["metadata"]["original_length"] > bash_tool.MAX_OUTPUT_LENGTH
        assert output_length == bash_tool.MAX_OUTPUT_LENGTH
        print(f"✓ 输出被正确截断: {result['metadata']['original_length']} -> {output_length} 字符")


@pytest.mark.asyncio
async def test_bash_tool_no_truncation_for_small_output(bash_tool):
    """
    测试小输出不被截断 | Test small output is not truncated


    当命令输出小于 30000 字符时，不应该被截断
    When command output is less than 30000 characters, it should not be truncated

    Args:
        bash_tool: Bash 工具实例 | Bash tool instance
    """
    # 生成一个小于 30000 字符的输出
    # Generate output less than 30000 characters
    test_output_size = 1000
    small_text = "y" * test_output_size

    result = await bash_tool.execute(
        {
            "command": "echo",
            "args": small_text,
            "description": "Generate small output",
        },
    )

    # 验证结果 | Verify result
    assert isinstance(result, dict)
    assert "output" in result
    assert "metadata" in result

    # 检查输出没有被截断 | Check output was not truncated
    assert result["metadata"].get("truncated") is False or result["metadata"].get("truncated") is None
    assert result["metadata"].get("original_length") is None

    # 输出长度应该接近预期（可能包含换行符等）
    # Output length should be close to expected (may include newlines, etc.)
    output_length = len(result["output"])
    assert output_length <= bash_tool.MAX_OUTPUT_LENGTH
    print(f"✓ 小输出未被截断: {output_length} 字符")
