# filename: test_workspace_grep.py
# @Time    : 2025/11/01 23:17
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 Workspace 的 grep_files 方法 | Test Workspace grep_files method

测试基于 ripgrep 的文件内容搜索功能
Test ripgrep-based file content search functionality
"""

import os
import tempfile
from pathlib import Path

import pytest

from ide4ai.python_ide.workspace import PyWorkspace


class TestWorkspaceGrepFiles:
    """测试 PyWorkspace.grep_files 方法 | Test PyWorkspace.grep_files method"""

    @pytest.fixture
    def temp_workspace(self):
        """
        创建临时工作区用于测试 | Create temporary workspace for testing
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件 | Create test files
            test_files = {
                "main.py": """# Main module
def main():
    print("Hello, World!")
    # TODO: Add error handling
    return 0

if __name__ == "__main__":
    main()
""",
                "utils.py": """# Utility functions
def helper():
    # TODO: Implement helper
    pass

class MyClass:
    def method(self):
        return "result"
""",
                "test_main.py": """# Test file
import unittest

class TestMain(unittest.TestCase):
    def test_main(self):
        assert True
""",
                "src/module.py": """# Source module
def function():
    # FIXME: Bug here
    return None
""",
                "docs/README.md": """# Documentation
This is a test project.
TODO: Add more docs
""",
            }

            # 创建文件 | Create files
            for file_path, content in test_files.items():
                full_path = Path(tmpdir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # 创建 workspace | Create workspace
            workspace = PyWorkspace(
                root_dir=tmpdir,
                project_name="test-grep",
                render_with_symbols=False,
            )

            yield workspace, tmpdir

            # 清理 | Cleanup
            workspace.close()

    def test_basic_search(self, temp_workspace):
        """
        测试基本搜索功能 | Test basic search functionality
        """
        workspace, tmpdir = temp_workspace

        # 搜索 "TODO"
        result = workspace.grep_files(pattern="TODO")

        assert result["success"] is True
        assert result["matched"] is True
        assert "main.py" in result["output"]
        assert "utils.py" in result["output"]

    def test_search_with_file_type(self, temp_workspace):
        """
        测试按文件类型搜索 | Test search with file type filter
        """
        workspace, tmpdir = temp_workspace

        # 仅搜索 Python 文件中的 "def"
        result = workspace.grep_files(
            pattern="def",
            file_type="py",
            output_mode="files_with_matches",
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 应该找到 Python 文件，但不包括 Markdown 文件
        assert "main.py" in result["output"] or "utils.py" in result["output"]
        assert "README.md" not in result["output"]

    def test_search_with_glob(self, temp_workspace):
        """
        测试使用 glob 模式搜索 | Test search with glob pattern
        """
        workspace, tmpdir = temp_workspace

        # 仅搜索测试文件
        result = workspace.grep_files(
            pattern="test",
            glob="**/test_*.py",
            output_mode="files_with_matches",
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "test_main.py" in result["output"]

    def test_search_content_mode(self, temp_workspace):
        """
        测试内容模式输出 | Test content mode output
        """
        workspace, tmpdir = temp_workspace

        # 搜索并显示内容
        result = workspace.grep_files(
            pattern="TODO",
            output_mode="content",
            line_number=True,
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 应该包含行号和内容
        assert "TODO" in result["output"]

    def test_search_with_context(self, temp_workspace):
        """
        测试带上下文的搜索 | Test search with context
        """
        workspace, tmpdir = temp_workspace

        # 搜索并显示上下文
        result = workspace.grep_files(
            pattern="TODO",
            output_mode="content",
            context=2,
            line_number=True,
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 应该包含上下文行
        output_lines = result["output"].split("\n")
        assert len(output_lines) > 1  # 应该有多行输出

    def test_search_case_insensitive(self, temp_workspace):
        """
        测试大小写不敏感搜索 | Test case-insensitive search
        """
        workspace, tmpdir = temp_workspace

        # 搜索 "todo"（小写）
        result = workspace.grep_files(
            pattern="todo",
            case_insensitive=True,
            output_mode="files_with_matches",
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 应该找到 "TODO"
        assert "main.py" in result["output"] or "utils.py" in result["output"]

    def test_search_count_mode(self, temp_workspace):
        """
        测试计数模式 | Test count mode
        """
        workspace, tmpdir = temp_workspace

        # 统计匹配数量
        result = workspace.grep_files(
            pattern="def",
            file_type="py",
            output_mode="count",
        )

        assert result["success"] is True
        assert result["matched"] is True
        # 输出应该包含计数信息
        assert result["output"]

    def test_search_with_head_limit(self, temp_workspace):
        """
        测试限制输出行数 | Test output line limit
        """
        workspace, tmpdir = temp_workspace

        # 限制输出为前 2 行
        result = workspace.grep_files(
            pattern="def",
            output_mode="content",
            head_limit=2,
        )

        assert result["success"] is True
        output_lines = result["output"].split("\n")
        # 输出行数应该不超过 2 行（可能少于 2 行如果匹配少）
        assert len([line for line in output_lines if line.strip()]) <= 2

    def test_search_in_subdirectory(self, temp_workspace):
        """
        测试在子目录中搜索 | Test search in subdirectory
        """
        workspace, tmpdir = temp_workspace

        # 仅在 src 目录中搜索
        result = workspace.grep_files(
            pattern="FIXME",
            path=os.path.join(tmpdir, "src"),
            output_mode="files_with_matches",
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "module.py" in result["output"]

    def test_search_no_matches(self, temp_workspace):
        """
        测试无匹配结果 | Test no matches found
        """
        workspace, tmpdir = temp_workspace

        # 搜索不存在的内容
        result = workspace.grep_files(
            pattern="NONEXISTENT_PATTERN_12345",
            output_mode="files_with_matches",
        )

        assert result["success"] is True
        assert result["matched"] is False
        assert result["output"] == ""

    def test_search_regex_pattern(self, temp_workspace):
        """
        测试正则表达式模式 | Test regex pattern
        """
        workspace, tmpdir = temp_workspace

        # 使用正则表达式搜索函数定义
        result = workspace.grep_files(
            pattern=r"def\s+\w+",
            output_mode="content",
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "def" in result["output"]

    def test_search_multiline(self, temp_workspace):
        """
        测试多行搜索 | Test multiline search
        """
        workspace, tmpdir = temp_workspace

        # 搜索跨行的模式
        result = workspace.grep_files(
            pattern=r"def.*\n.*print",
            multiline=True,
            output_mode="content",
        )

        assert result["success"] is True
        # 可能有匹配也可能没有，取决于文件内容

    def test_search_invalid_path(self, temp_workspace):
        """
        测试无效路径 | Test invalid path
        """
        workspace, tmpdir = temp_workspace

        # 搜索不存在的路径
        with pytest.raises(ValueError, match="搜索路径不存在"):
            workspace.grep_files(
                pattern="test",
                path="/nonexistent/path",
            )

    def test_search_path_outside_workspace(self, temp_workspace):
        """
        测试工作区外的路径 | Test path outside workspace
        """
        workspace, tmpdir = temp_workspace

        # 尝试搜索工作区外的路径
        with pytest.raises(ValueError, match="搜索路径必须在工作区根目录内"):
            workspace.grep_files(
                pattern="test",
                path="/tmp",
            )

    def test_search_metadata(self, temp_workspace):
        """
        测试返回的元数据 | Test returned metadata
        """
        workspace, tmpdir = temp_workspace

        result = workspace.grep_files(
            pattern="TODO",
            output_mode="files_with_matches",
        )

        assert result["success"] is True
        assert "metadata" in result
        assert result["metadata"]["pattern"] == "TODO"
        assert result["metadata"]["output_mode"] == "files_with_matches"
        assert "exit_code" in result["metadata"]

    def test_search_context_before_after(self, temp_workspace):
        """
        测试分别指定前后上下文 | Test separate before/after context
        """
        workspace, tmpdir = temp_workspace

        # 指定前后不同的上下文行数
        result = workspace.grep_files(
            pattern="TODO",
            output_mode="content",
            context_before=1,
            context_after=2,
            line_number=True,
        )

        assert result["success"] is True
        assert result["matched"] is True

    def test_search_relative_path(self, temp_workspace):
        """
        测试相对路径搜索 | Test relative path search
        """
        workspace, tmpdir = temp_workspace

        # 使用相对路径
        result = workspace.grep_files(
            pattern="FIXME",
            path="src",  # 相对路径
            output_mode="files_with_matches",
        )

        assert result["success"] is True
        assert result["matched"] is True
        assert "module.py" in result["output"]


class TestWorkspaceGrepEdgeCases:
    """测试边界情况 | Test edge cases"""

    def test_grep_without_ripgrep(self, monkeypatch):
        """
        测试 ripgrep 未安装的情况 | Test when ripgrep is not installed
        """
        import subprocess

        def mock_run(*args, **kwargs):
            raise FileNotFoundError("ripgrep not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = PyWorkspace(
                root_dir=tmpdir,
                project_name="test",
                render_with_symbols=False,
            )

            with pytest.raises(RuntimeError, match="ripgrep 未安装"):
                workspace.grep_files(pattern="test")

            workspace.close()

    def test_grep_timeout(self, monkeypatch):
        """
        测试搜索超时 | Test search timeout
        """
        import subprocess

        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=30)

        monkeypatch.setattr(subprocess, "run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = PyWorkspace(
                root_dir=tmpdir,
                project_name="test",
                render_with_symbols=False,
            )

            with pytest.raises(RuntimeError, match="ripgrep 执行超时"):
                workspace.grep_files(pattern="test")

            workspace.close()

    def test_grep_execution_error(self, monkeypatch):
        """
        测试 ripgrep 执行错误 | Test ripgrep execution error
        """
        import subprocess
        from unittest.mock import MagicMock

        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 2  # ripgrep 错误码
            result.stderr = "Invalid regex pattern"
            return result

        monkeypatch.setattr(subprocess, "run", mock_run)

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = PyWorkspace(
                root_dir=tmpdir,
                project_name="test",
                render_with_symbols=False,
            )

            with pytest.raises(RuntimeError, match="ripgrep 执行错误"):
                workspace.grep_files(pattern="[invalid")

            workspace.close()
