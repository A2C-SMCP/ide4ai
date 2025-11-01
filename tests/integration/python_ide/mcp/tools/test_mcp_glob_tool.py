# filename: test_mcp_glob_tool.py
# @Time    : 2025/11/01 17:13
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Glob 工具测试 | MCP Glob Tool Tests

测试 Glob 工具的基本功能
Tests basic functionality of Glob tool
"""

import pytest

from ide4ai.ides import PyIDESingleton
from ide4ai.python_ide.mcp.tools.glob import GlobTool


@pytest.fixture
def ide_instance():
    """
    创建 IDE 实例 | Create IDE instance

    Returns:
        PythonIDE: IDE 实例 | IDE instance
    """
    ide_singleton = PyIDESingleton(
        cmd_white_list=["ls", "pwd", "echo"],
        root_dir="../..",
        project_name="test-project",
    )
    return ide_singleton.ide


@pytest.fixture
def glob_tool(ide_instance):
    """
    创建 Glob 工具实例 | Create Glob tool instance

    Args:
        ide_instance: IDE 实例 | IDE instance

    Returns:
        GlobTool: Glob 工具实例 | Glob tool instance
    """
    return GlobTool(ide_instance)


def test_glob_tool_properties(glob_tool):
    """
    测试 Glob 工具的属性 | Test Glob tool properties

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    assert glob_tool.name == "Glob"
    assert isinstance(glob_tool.description, str)
    assert len(glob_tool.description) > 0
    assert "glob" in glob_tool.description.lower()

    # 检查 input schema | Check input schema
    schema = glob_tool.input_schema
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "pattern" in schema["properties"]
    assert "path" in schema["properties"]

    # 验证 pattern 是必需的 | Verify pattern is required
    assert "required" in schema
    assert "pattern" in schema["required"]


@pytest.mark.asyncio
async def test_glob_tool_execute_simple_pattern(glob_tool):
    """
    测试执行简单的 glob 模式 | Test executing simple glob pattern

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    # 查找所有 Python 文件 | Find all Python files
    result = await glob_tool.execute(
        {
            "pattern": "*.py",
        }
    )

    # 验证结果 | Verify result
    assert isinstance(result, dict)
    assert "success" in result
    assert "files" in result
    assert isinstance(result["files"], list)

    # 如果成功，应该有元数据 | If successful, should have metadata
    if result["success"]:
        assert "metadata" in result
        assert "pattern" in result["metadata"]
        assert result["metadata"]["pattern"] == "*.py"


@pytest.mark.asyncio
async def test_glob_tool_execute_recursive_pattern(glob_tool):
    """
    测试执行递归 glob 模式 | Test executing recursive glob pattern

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    # 递归查找所有 Python 文件 | Recursively find all Python files
    result = await glob_tool.execute(
        {
            "pattern": "**/*.py",
        }
    )

    # 验证结果 | Verify result
    assert isinstance(result, dict)
    assert "success" in result
    assert "files" in result
    assert isinstance(result["files"], list)

    # 验证文件格式 | Verify file format
    if result["success"] and len(result["files"]) > 0:
        first_file = result["files"][0]
        assert "path" in first_file
        assert "uri" in first_file
        assert "mtime" in first_file
        assert first_file["uri"].startswith("file://")


@pytest.mark.asyncio
async def test_glob_tool_execute_with_path(glob_tool):
    """
    测试在指定路径下执行 glob | Test executing glob with specific path

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    # 在 ide4ai 目录下查找 Python 文件 | Find Python files in ide4ai directory
    result = await glob_tool.execute(
        {
            "pattern": "*.py",
            "path": "ide4ai",
        }
    )

    # 验证结果 | Verify result
    assert isinstance(result, dict)
    assert "success" in result
    assert "files" in result

    # 如果成功，验证元数据 | If successful, verify metadata
    if result["success"]:
        assert "metadata" in result
        assert result["metadata"]["path"] == "ide4ai"


@pytest.mark.asyncio
async def test_glob_tool_execute_no_matches(glob_tool):
    """
    测试没有匹配文件的情况 | Test case with no matching files

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    # 使用不太可能匹配的模式 | Use unlikely pattern
    result = await glob_tool.execute(
        {
            "pattern": "*.nonexistent_extension_xyz",
        }
    )

    # 验证结果 | Verify result
    assert isinstance(result, dict)
    assert "success" in result
    assert "files" in result

    # 应该成功但没有文件 | Should succeed but with no files
    if result["success"]:
        assert len(result["files"]) == 0
        assert result["metadata"]["count"] == 0


@pytest.mark.asyncio
async def test_glob_tool_execute_invalid_path(glob_tool):
    """
    测试无效路径 | Test invalid path

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    # 使用不存在的路径 | Use non-existent path
    result = await glob_tool.execute(
        {
            "pattern": "*.py",
            "path": "/nonexistent/path/that/does/not/exist",
        }
    )

    # 应该返回错误 | Should return error
    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_glob_tool_invalid_input(glob_tool):
    """
    测试无效输入 | Test invalid input

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    # 缺少必需的 pattern 参数 | Missing required pattern parameter
    result = await glob_tool.execute({})

    # 应该返回错误 | Should return error
    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result


def test_glob_tool_input_schema_validation(glob_tool):
    """
    测试输入 Schema 验证 | Test input schema validation

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    from ide4ai.python_ide.mcp.schemas.tools import GlobInput

    # 有效输入 - 仅 pattern | Valid input - pattern only
    valid_input = GlobInput(pattern="*.py")
    assert valid_input.pattern == "*.py"
    assert valid_input.path is None

    # 有效输入 - 带路径 | Valid input - with path
    valid_input_with_path = GlobInput(pattern="**/*.js", path="src")
    assert valid_input_with_path.pattern == "**/*.js"
    assert valid_input_with_path.path == "src"


@pytest.mark.asyncio
async def test_glob_tool_files_sorted_by_mtime(glob_tool):
    """
    测试文件按修改时间排序 | Test files are sorted by modification time

    Args:
        glob_tool: Glob 工具实例 | Glob tool instance
    """
    # 查找多个文件 | Find multiple files
    result = await glob_tool.execute(
        {
            "pattern": "**/*.py",
        }
    )

    # 验证结果 | Verify result
    if result["success"] and len(result["files"]) > 1:
        files = result["files"]
        # 验证按 mtime 降序排列（最新的在前）| Verify sorted by mtime descending (newest first)
        for i in range(len(files) - 1):
            assert files[i]["mtime"] >= files[i + 1]["mtime"], "Files should be sorted by mtime descending"


@pytest.mark.asyncio
async def test_glob_tool_workspace_none_error(ide_instance):
    """
    测试 workspace 为 None 的情况 | Test case when workspace is None

    Args:
        ide_instance: IDE 实例 | IDE instance
    """
    # 创建工具实例 | Create tool instance
    glob_tool = GlobTool(ide_instance)

    # 临时将 workspace 设置为 None | Temporarily set workspace to None
    original_workspace = ide_instance.workspace
    ide_instance.workspace = None

    try:
        # 执行应该失败 | Execution should fail
        result = await glob_tool.execute(
            {
                "pattern": "*.py",
            }
        )

        # 验证返回错误 | Verify error is returned
        assert isinstance(result, dict)
        assert result["success"] is False
        assert "error" in result
        assert "Workspace" in result["error"] or "workspace" in result["error"]

    finally:
        # 恢复 workspace | Restore workspace
        ide_instance.workspace = original_workspace
