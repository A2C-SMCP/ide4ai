# -*- coding: utf-8 -*-
# filename: test_base.py
# @Time    : 2025/10/28 16:08
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import os
import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from ide4ai.python_ide.workspace import PyWorkspace


@pytest.fixture
def temp_workspace() -> Generator[tuple[PyWorkspace, str], Any, None]:
    """
    创建一个临时工作区用于测试 / Create a temporary workspace for testing

    Returns:
        Generator: 生成器，返回 (workspace, temp_dir) 元组 / Generator yielding (workspace, temp_dir) tuple
    """
    # 创建临时目录 / Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix="ide4ai_test_")

    try:
        # 创建测试文件结构 / Create test file structure
        # 根目录文件 / Root directory files
        (Path(temp_dir) / "root_file1.py").write_text("# Root Python file 1")
        (Path(temp_dir) / "root_file2.py").write_text("# Root Python file 2")
        (Path(temp_dir) / "root_file.js").write_text("// Root JavaScript file")
        (Path(temp_dir) / "README.md").write_text("# README")

        # src 目录 / src directory
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# Main Python file")
        (src_dir / "utils.py").write_text("# Utils Python file")
        (src_dir / "app.js").write_text("// App JavaScript file")

        # src/components 子目录 / src/components subdirectory
        components_dir = src_dir / "components"
        components_dir.mkdir()
        (components_dir / "button.tsx").write_text("// Button component")
        (components_dir / "input.tsx").write_text("// Input component")
        (components_dir / "helper.py").write_text("# Helper Python file")

        # tests 目录 / tests directory
        tests_dir = Path(temp_dir) / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("# Test main")
        (tests_dir / "test_utils.py").write_text("# Test utils")

        # docs 目录 / docs directory
        docs_dir = Path(temp_dir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "guide.md").write_text("# Guide")
        (docs_dir / "api.md").write_text("# API")

        # 添加一些延迟以确保文件有不同的修改时间 / Add delays to ensure different modification times
        time.sleep(0.01)
        (Path(temp_dir) / "newer_file.py").write_text("# Newer file")

        # 初始化工作区 / Initialize workspace
        workspace = PyWorkspace(root_dir=temp_dir, project_name="test_glob_workspace")

        yield workspace, temp_dir

        # 清理：关闭工作区 / Cleanup: close workspace
        workspace.close()

    finally:
        # 清理：删除临时目录及其所有内容 / Cleanup: remove temporary directory and all contents
        import shutil

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def test_glob_files_all_python_files(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试查找所有 Python 文件 / Test finding all Python files

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 查找所有 Python 文件 / Find all Python files
    results = workspace.glob_files(pattern="**/*.py")

    # 验证结果 / Verify results
    assert len(results) > 0, "应该找到至少一个 Python 文件 / Should find at least one Python file"

    # 验证所有结果都是 .py 文件 / Verify all results are .py files
    for result in results:
        assert result["path"].endswith(".py"), f"路径应该以 .py 结尾 / Path should end with .py: {result['path']}"
        assert "uri" in result, "结果应该包含 uri 字段 / Result should contain uri field"
        assert "path" in result, "结果应该包含 path 字段 / Result should contain path field"
        assert "mtime" in result, "结果应该包含 mtime 字段 / Result should contain mtime field"
        assert result["uri"].startswith("file://"), "URI 应该以 file:// 开头 / URI should start with file://"

    # 验证找到了预期的文件 / Verify expected files are found
    paths = [r["path"] for r in results]
    assert "root_file1.py" in paths, "应该找到 root_file1.py / Should find root_file1.py"
    assert "src/main.py" in paths, "应该找到 src/main.py / Should find src/main.py"
    assert "tests/test_main.py" in paths, "应该找到 tests/test_main.py / Should find tests/test_main.py"

    print(f"\n找到 {len(results)} 个 Python 文件 / Found {len(results)} Python files:")
    for r in results[:5]:  # 打印前5个 / Print first 5
        print(f"  - {r['path']}")


def test_glob_files_specific_directory(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试在特定目录中查找文件 / Test finding files in specific directory

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 在 src 目录中查找所有 Python 文件 / Find all Python files in src directory
    results = workspace.glob_files(pattern="**/*.py", path=os.path.join(temp_dir, "src"))

    # 验证结果 / Verify results
    assert len(results) > 0, "应该在 src 目录找到 Python 文件 / Should find Python files in src directory"

    # 验证所有文件都在 src 目录下 / Verify all files are under src directory
    for result in results:
        assert result["path"].startswith("src/"), f"路径应该以 src/ 开头 / Path should start with src/: {result['path']}"

    paths = [r["path"] for r in results]
    assert "src/main.py" in paths, "应该找到 src/main.py / Should find src/main.py"
    assert "src/components/helper.py" in paths, "应该找到 src/components/helper.py / Should find src/components/helper.py"

    print(f"\n在 src 目录找到 {len(results)} 个 Python 文件 / Found {len(results)} Python files in src directory:")
    for r in results:
        print(f"  - {r['path']}")


def test_glob_files_non_recursive(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试非递归模式查找文件 / Test non-recursive file finding

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 只在根目录查找 Python 文件（不递归）/ Find Python files only in root directory (non-recursive)
    results = workspace.glob_files(pattern="*.py")

    # 验证结果 / Verify results
    assert len(results) > 0, "应该在根目录找到 Python 文件 / Should find Python files in root directory"

    # 验证所有文件都在根目录（不在子目录）/ Verify all files are in root directory (not in subdirectories)
    for result in results:
        assert "/" not in result["path"], f"路径不应该包含子目录 / Path should not contain subdirectories: {result['path']}"

    paths = [r["path"] for r in results]
    assert "root_file1.py" in paths, "应该找到 root_file1.py / Should find root_file1.py"
    assert "src/main.py" not in paths, "不应该找到 src/main.py / Should not find src/main.py"

    print(f"\n在根目录找到 {len(results)} 个 Python 文件 / Found {len(results)} Python files in root directory:")
    for r in results:
        print(f"  - {r['path']}")


def test_glob_files_multiple_extensions(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试查找多种文件类型 / Test finding multiple file types

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 查找 TypeScript 文件 / Find TypeScript files
    tsx_results = workspace.glob_files(pattern="**/*.tsx")
    assert len(tsx_results) == 2, "应该找到 2 个 .tsx 文件 / Should find 2 .tsx files"

    # 查找 Markdown 文件 / Find Markdown files
    md_results = workspace.glob_files(pattern="**/*.md")
    assert len(md_results) == 3, "应该找到 3 个 .md 文件 / Should find 3 .md files"

    # 查找 JavaScript 文件 / Find JavaScript files
    js_results = workspace.glob_files(pattern="**/*.js")
    assert len(js_results) == 2, "应该找到 2 个 .js 文件 / Should find 2 .js files"

    print(f"\n找到 {len(tsx_results)} 个 .tsx 文件 / Found {len(tsx_results)} .tsx files")
    print(f"找到 {len(md_results)} 个 .md 文件 / Found {len(md_results)} .md files")
    print(f"找到 {len(js_results)} 个 .js 文件 / Found {len(js_results)} .js files")


def test_glob_files_sorted_by_mtime(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试结果按修改时间排序 / Test results are sorted by modification time

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 查找所有 Python 文件 / Find all Python files
    results = workspace.glob_files(pattern="**/*.py")

    # 验证结果按修改时间降序排序 / Verify results are sorted by modification time descending
    if len(results) > 1:
        for i in range(len(results) - 1):
            assert results[i]["mtime"] >= results[i + 1]["mtime"], (
                "结果应该按修改时间降序排序 / Results should be sorted by mtime descending"
            )

    # 验证最新的文件在最前面 / Verify newest file is first
    if len(results) > 0:
        newest_file = results[0]
        assert "newer_file.py" in newest_file["path"], (
            f"最新的文件应该是 newer_file.py / Newest file should be newer_file.py, got {newest_file['path']}"
        )

    print("\n文件按修改时间排序（最新的在前）/ Files sorted by modification time (newest first):")
    for r in results[:3]:  # 打印前3个 / Print first 3
        print(f"  - {r['path']} (mtime: {r['mtime']})")


def test_glob_files_invalid_path(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试使用无效路径时抛出异常 / Test exception is raised with invalid path

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 测试不存在的路径 / Test non-existent path
    with pytest.raises(ValueError, match="搜索路径不存在"):
        workspace.glob_files(pattern="*.py", path="/non/existent/path")

    print("\n✓ 正确处理不存在的路径 / Correctly handled non-existent path")


def test_glob_files_outside_workspace(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试搜索工作区外的路径时抛出异常 / Test exception is raised when searching outside workspace

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 测试工作区外的路径 / Test path outside workspace
    with pytest.raises(ValueError, match="搜索路径必须在工作区根目录内"):
        workspace.glob_files(pattern="*.py", path="/tmp")

    print("\n✓ 正确阻止搜索工作区外的路径 / Correctly prevented searching outside workspace")


def test_glob_files_empty_results(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试没有匹配文件时返回空列表 / Test empty list is returned when no files match

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 查找不存在的文件类型 / Find non-existent file type
    results = workspace.glob_files(pattern="**/*.xyz")

    assert len(results) == 0, "应该返回空列表 / Should return empty list"
    assert isinstance(results, list), "应该返回列表类型 / Should return list type"

    print("\n✓ 正确处理无匹配结果的情况 / Correctly handled no matching results")


def test_glob_files_relative_path(temp_workspace: tuple[PyWorkspace, str]) -> None:
    """
    测试使用相对路径 / Test using relative path

    Args:
        temp_workspace: 临时工作区和目录 / Temporary workspace and directory
    """
    workspace, temp_dir = temp_workspace

    # 使用相对路径 / Use relative path
    results = workspace.glob_files(pattern="*.py", path="src")

    # 验证结果 / Verify results
    assert len(results) > 0, "应该找到文件 / Should find files"

    # 验证所有文件都在 src 目录下 / Verify all files are under src directory
    for result in results:
        # 相对路径会被转换为绝对路径，结果应该在 src 目录下 / Relative path is converted to absolute, results should be under src
        assert result["path"].startswith("src/"), f"路径应该以 src/ 开头 / Path should start with src/: {result['path']}"

    print(
        f"\n✓ 正确处理相对路径，找到 {len(results)} 个文件 / Correctly handled relative path, found {len(results)} files",
    )
