# filename: test_workspace_render.py
# @Time    : 2025/10/28 20:04
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试PyWorkspace的render函数 | Test PyWorkspace render function

全面测试render函数的各个方面：
1. 最小化展开的目录树
2. 项目快捷命令检测
3. active_models渲染
4. 各种边界情况

Comprehensive tests for render function:
1. Minimally expanded directory tree
2. Project shortcut commands detection
3. active_models rendering
4. Various edge cases
"""

import os
import tempfile
from collections.abc import Generator
from typing import Any

import pytest

from ide4ai.python_ide.workspace import PyWorkspace


@pytest.fixture
def project_root_dir() -> str:
    """项目根目录 | Project root directory"""
    return os.path.dirname(__file__) + "/virtual_project"


@pytest.fixture
def py_workspace(project_root_dir) -> Generator[PyWorkspace, Any, None]:
    """PyWorkspace实例 | PyWorkspace instance"""
    workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_render_workspace")
    yield workspace
    workspace.close()


@pytest.fixture
def temp_workspace_with_makefile() -> Generator[tuple[str, PyWorkspace], Any, None]:
    """
    创建带Makefile的临时工作区 | Create temporary workspace with Makefile

    Returns:
        tuple[str, PyWorkspace]: (临时目录路径, workspace实例) | (temp dir path, workspace instance)
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建一个Makefile | Create a Makefile
        makefile_path = os.path.join(temp_dir, "Makefile")
        with open(makefile_path, "w", encoding="utf-8") as f:
            f.write("""# Test Makefile
.PHONY: all clean test

all: build

build:
\t@echo "Building..."

test:
\t@echo "Testing..."

clean:
\t@echo "Cleaning..."

install:
\t@echo "Installing..."
""")

        # 创建一些测试文件和目录结构 | Create test files and directory structure
        os.makedirs(os.path.join(temp_dir, "src"), exist_ok=True)
        os.makedirs(os.path.join(temp_dir, "tests"), exist_ok=True)

        test_file = os.path.join(temp_dir, "src", "main.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("# -*- coding: utf-8 -*-\n# Test file\ndef main():\n    pass\n")

        workspace = PyWorkspace(root_dir=temp_dir, project_name="test_makefile_workspace")
        yield temp_dir, workspace
        workspace.close()


@pytest.fixture
def temp_workspace_with_mk_files() -> Generator[tuple[str, PyWorkspace], Any, None]:
    """
    创建带.mk文件的临时工作区 | Create temporary workspace with .mk files

    Returns:
        tuple[str, PyWorkspace]: (临时目录路径, workspace实例) | (temp dir path, workspace instance)
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建多个.mk文件 | Create multiple .mk files
        common_mk = os.path.join(temp_dir, "common.mk")
        with open(common_mk, "w", encoding="utf-8") as f:
            f.write("""# Common makefile
compile:
\t@echo "Compiling..."

link:
\t@echo "Linking..."
""")

        config_mk = os.path.join(temp_dir, "config.mk")
        with open(config_mk, "w", encoding="utf-8") as f:
            f.write("""# Config makefile
setup:
\t@echo "Setup..."

configure:
\t@echo "Configure..."
""")

        # 创建测试文件 | Create test file
        test_file = os.path.join(temp_dir, "test.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("# Test\nprint('hello')\n")

        workspace = PyWorkspace(root_dir=temp_dir, project_name="test_mk_workspace")
        yield temp_dir, workspace
        workspace.close()


class TestRenderBasic:
    """基础render功能测试 | Basic render functionality tests"""

    def test_render_without_active_models(self, py_workspace):
        """
        测试没有active_models时的render输出 | Test render output without active_models

        应该包含：
        - 项目名称
        - 目录结构（普通展开）
        Should include:
        - Project name
        - Directory structure (normal expansion)
        """
        render_output = py_workspace.render()

        # 验证基本信息 | Verify basic info
        assert "当前工作区: test_render_workspace" in render_output
        assert "项目目录结构" in render_output

        # 验证没有active_models相关内容 | Verify no active_models content
        assert "当前打开的文件内容如下" not in render_output

    def test_render_with_single_active_model(self, project_root_dir, py_workspace):
        """
        测试有单个active_model时的render输出 | Test render output with single active_model

        应该包含：
        - 最小化展开的目录树
        - 当前打开文件的内容
        Should include:
        - Minimally expanded directory tree
        - Current open file content
        """
        test_file = project_root_dir + "/file_for_test_read.py"
        py_workspace.open_file(uri=f"file://{test_file}")

        render_output = py_workspace.render()

        # 验证基本信息 | Verify basic info
        assert "当前工作区: test_render_workspace" in render_output
        assert "项目目录结构" in render_output

        # 验证包含当前文件内容 | Verify contains current file content
        assert "当前打开的文件内容如下" in render_output
        assert "ACTION_CATEGORY_MAP" in render_output  # file_for_test_read.py的内容

        # 验证目录树中标记了当前文件 | Verify directory tree marks current file
        assert "file_for_test_read.py" in render_output
        assert "当前文件" in render_output or "Current file" in render_output

    def test_render_with_multiple_active_models(self, project_root_dir, py_workspace):
        """
        测试有多个active_models时的render输出 | Test render output with multiple active_models

        应该包含：
        - 前面文件的Symbols信息
        - 最后一个文件的完整内容
        Should include:
        - Symbols info for previous files
        - Full content of last file
        """
        file1 = project_root_dir + "/file_for_render_1.py"
        file2 = project_root_dir + "/file_for_test_read.py"

        py_workspace.open_file(uri=f"file://{file1}")
        py_workspace.open_file(uri=f"file://{file2}")

        render_output = py_workspace.render()

        # 验证包含Symbols信息 | Verify contains Symbols info
        assert "以下是最近使用的文件其结构信息与关键Symbols信息" in render_output
        assert "文件URI:" in render_output

        # 验证包含最后一个文件的完整内容 | Verify contains last file's full content
        assert "当前打开的文件内容如下" in render_output
        assert "ACTION_CATEGORY_MAP" in render_output


class TestRenderDirectoryTree:
    """目录树渲染测试 | Directory tree rendering tests"""

    def test_minimal_expanded_tree_with_active_file(self, temp_workspace_with_makefile):
        """
        测试最小化展开的目录树 | Test minimally expanded directory tree

        当有活跃文件时，应该只展开到该文件所在的路径
        When there's an active file, should only expand to that file's path
        """
        temp_dir, workspace = temp_workspace_with_makefile

        # 打开src/main.py | Open src/main.py
        test_file = os.path.join(temp_dir, "src", "main.py")
        workspace.open_file(uri=f"file://{test_file}")

        render_output = workspace.render()

        # 验证src目录被展开 | Verify src directory is expanded
        assert "src/" in render_output
        assert "main.py" in render_output

        # 验证标记了当前文件 | Verify current file is marked
        assert "当前文件" in render_output or "Current file" in render_output

    def test_directory_tree_without_active_file(self, temp_workspace_with_makefile):
        """
        测试没有活跃文件时的目录树 | Test directory tree without active file

        应该使用普通的目录树展开方式
        Should use normal directory tree expansion
        """
        temp_dir, workspace = temp_workspace_with_makefile

        render_output = workspace.render()

        # 验证包含目录结构 | Verify contains directory structure
        assert "项目目录结构" in render_output
        assert "Makefile" in render_output


class TestRenderShortcutCommands:
    """快捷命令渲染测试 | Shortcut commands rendering tests"""

    def test_render_with_makefile_commands(self, temp_workspace_with_makefile):
        """
        测试检测并渲染Makefile命令 | Test detect and render Makefile commands

        应该自动检测Makefile并显示可用命令
        Should auto-detect Makefile and display available commands
        """
        temp_dir, workspace = temp_workspace_with_makefile

        render_output = workspace.render()

        # 验证包含快捷命令部分 | Verify contains shortcut commands section
        assert "项目快捷命令" in render_output or "Project Shortcut Commands" in render_output
        assert "make 命令" in render_output or "make commands" in render_output

        # 验证包含具体的命令 | Verify contains specific commands
        assert "make build" in render_output
        assert "make test" in render_output
        assert "make clean" in render_output
        assert "make install" in render_output

        # 验证不包含.PHONY等内部目标 | Verify doesn't contain .PHONY and other internal targets
        assert ".PHONY" not in render_output

    def test_render_with_mk_files(self, temp_workspace_with_mk_files):
        """
        测试检测并渲染.mk文件中的命令 | Test detect and render commands from .mk files

        应该能够从*.mk文件中提取命令
        Should be able to extract commands from *.mk files
        """
        temp_dir, workspace = temp_workspace_with_mk_files

        render_output = workspace.render()

        # 验证包含快捷命令 | Verify contains shortcut commands
        assert "项目快捷命令" in render_output or "Project Shortcut Commands" in render_output

        # 验证包含从.mk文件提取的命令 | Verify contains commands from .mk files
        assert "make compile" in render_output
        assert "make link" in render_output
        assert "make setup" in render_output
        assert "make configure" in render_output

    def test_render_with_custom_shortcut_commands(self, project_root_dir):
        """
        测试使用自定义快捷命令 | Test with custom shortcut commands

        用户可以通过初始化参数传入自定义命令
        Users can pass custom commands via initialization parameters
        """
        custom_commands = {
            "poe": ["test", "lint", "format", "build"],
            "npm": ["start", "build", "test"],
        }

        workspace = PyWorkspace(
            root_dir=project_root_dir,
            project_name="test_custom_commands",
            shortcut_commands=custom_commands,
        )

        try:
            render_output = workspace.render()

            # 验证包含自定义命令 | Verify contains custom commands
            assert "项目快捷命令" in render_output
            assert "poe 命令" in render_output
            assert "npm 命令" in render_output

            # 验证具体命令 | Verify specific commands
            assert "poe test" in render_output
            assert "poe lint" in render_output
            assert "npm start" in render_output
            assert "npm build" in render_output
        finally:
            workspace.close()

    def test_render_without_makefile(self, project_root_dir, py_workspace):
        """
        测试没有Makefile时的render输出 | Test render output without Makefile

        不应该显示快捷命令部分
        Should not display shortcut commands section
        """
        render_output = py_workspace.render()

        # 如果项目根目录没有Makefile，不应该有快捷命令部分
        # If project root has no Makefile, should not have shortcut commands section
        # 注意：virtual_project可能有Makefile，这里只是验证逻辑
        # Note: virtual_project might have Makefile, just verifying the logic
        if "Makefile" not in os.listdir(project_root_dir):
            assert "项目快捷命令" not in render_output


class TestRenderEdgeCases:
    """边界情况测试 | Edge cases tests"""

    def test_render_with_empty_workspace(self):
        """
        测试空工作区的render | Test render with empty workspace

        创建一个空的临时目录作为工作区
        Create an empty temporary directory as workspace
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = PyWorkspace(root_dir=temp_dir, project_name="empty_workspace")
            try:
                render_output = workspace.render()

                # 验证基本信息存在 | Verify basic info exists
                assert "当前工作区: empty_workspace" in render_output
                assert "项目目录结构" in render_output
            finally:
                workspace.close()

    def test_render_with_nested_directories(self):
        """
        测试深层嵌套目录的render | Test render with deeply nested directories

        验证最小化展开能够正确处理深层路径
        Verify minimal expansion correctly handles deep paths
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建深层嵌套目录 | Create deeply nested directories
            deep_path = os.path.join(temp_dir, "level1", "level2", "level3", "level4")
            os.makedirs(deep_path, exist_ok=True)

            test_file = os.path.join(deep_path, "deep_file.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("# Deep file\nprint('deep')\n")

            workspace = PyWorkspace(root_dir=temp_dir, project_name="nested_workspace")
            try:
                # 打开深层文件 | Open deep file
                workspace.open_file(uri=f"file://{test_file}")

                render_output = workspace.render()

                # 验证路径被正确展开 | Verify path is correctly expanded
                assert "level1/" in render_output
                assert "level2/" in render_output
                assert "level3/" in render_output
                assert "level4/" in render_output
                assert "deep_file.py" in render_output
                assert "当前文件" in render_output or "Current file" in render_output
            finally:
                workspace.close()

    def test_render_with_special_characters_in_filename(self):
        """
        测试文件名包含特殊字符时的render | Test render with special characters in filename

        验证能够正确处理特殊字符
        Verify can correctly handle special characters
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建包含特殊字符的文件名（但要符合文件系统规范）
            # Create filename with special characters (but comply with filesystem rules)
            test_file = os.path.join(temp_dir, "test-file_123.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("# Test file\nprint('test')\n")

            workspace = PyWorkspace(root_dir=temp_dir, project_name="special_chars_workspace")
            try:
                workspace.open_file(uri=f"file://{test_file}")

                render_output = workspace.render()

                # 验证文件名正确显示 | Verify filename is correctly displayed
                assert "test-file_123.py" in render_output
            finally:
                workspace.close()

    def test_render_multiple_times(self, project_root_dir, py_workspace):
        """
        测试多次调用render | Test calling render multiple times

        验证render是幂等的，多次调用结果一致
        Verify render is idempotent, multiple calls produce consistent results
        """
        test_file = project_root_dir + "/file_for_test_read.py"
        py_workspace.open_file(uri=f"file://{test_file}")

        # 多次调用render | Call render multiple times
        render1 = py_workspace.render()
        render2 = py_workspace.render()
        render3 = py_workspace.render()

        # 验证结果一致 | Verify results are consistent
        assert render1 == render2
        assert render2 == render3

    def test_render_after_file_operations(self, project_root_dir, py_workspace):
        """
        测试文件操作后的render | Test render after file operations

        验证在打开、关闭文件后render能正确更新
        Verify render correctly updates after opening/closing files
        """
        file1 = project_root_dir + "/file_for_render_1.py"
        file2 = project_root_dir + "/file_for_test_read.py"

        # 初始render | Initial render
        render1 = py_workspace.render()
        assert "当前打开的文件内容如下" not in render1

        # 打开第一个文件 | Open first file
        py_workspace.open_file(uri=f"file://{file1}")
        render2 = py_workspace.render()
        assert "当前打开的文件内容如下" in render2

        # 打开第二个文件 | Open second file
        py_workspace.open_file(uri=f"file://{file2}")
        render3 = py_workspace.render()
        assert "以下是最近使用的文件其结构信息与关键Symbols信息" in render3

        # 验证render内容随文件操作变化 | Verify render content changes with file operations
        assert render1 != render2
        assert render2 != render3


class TestRenderIntegration:
    """集成测试 | Integration tests"""

    def test_render_complete_workflow(self):
        """
        测试完整的工作流程 | Test complete workflow

        模拟真实使用场景：创建项目、添加文件、打开文件、查看render
        Simulate real usage: create project, add files, open files, view render
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. 创建项目结构 | Create project structure
            os.makedirs(os.path.join(temp_dir, "src"), exist_ok=True)
            os.makedirs(os.path.join(temp_dir, "tests"), exist_ok=True)

            # 2. 创建Makefile | Create Makefile
            makefile_path = os.path.join(temp_dir, "Makefile")
            with open(makefile_path, "w", encoding="utf-8") as f:
                f.write("""all: build test

build:
\t@echo "Building..."

test:
\t@echo "Testing..."
""")

            # 3. 创建源文件 | Create source files
            main_file = os.path.join(temp_dir, "src", "main.py")
            with open(main_file, "w", encoding="utf-8") as f:
                f.write("""# -*- coding: utf-8 -*-
# Main module

def main():
    '''Main function'''
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")

            test_file = os.path.join(temp_dir, "tests", "test_main.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("""# -*- coding: utf-8 -*-
# Test module

def test_main():
    '''Test main function'''
    assert True
""")

            # 4. 初始化workspace | Initialize workspace
            workspace = PyWorkspace(root_dir=temp_dir, project_name="integration_test_project")

            try:
                # 5. 打开文件 | Open files
                workspace.open_file(uri=f"file://{main_file}")
                workspace.open_file(uri=f"file://{test_file}")

                # 6. 获取render输出 | Get render output
                render_output = workspace.render()

                # 7. 验证所有功能都正常工作 | Verify all features work correctly

                # 验证项目信息 | Verify project info
                assert "当前工作区: integration_test_project" in render_output

                # 验证目录结构 | Verify directory structure
                assert "项目目录结构" in render_output
                assert "src/" in render_output
                assert "tests/" in render_output

                # 验证快捷命令 | Verify shortcut commands
                assert "项目快捷命令" in render_output
                assert "make build" in render_output
                assert "make test" in render_output

                # 验证文件内容 | Verify file content
                assert "以下是最近使用的文件其结构信息与关键Symbols信息" in render_output
                assert "当前打开的文件内容如下" in render_output
                assert "Function: test_main" in render_output or "test_main" in render_output

                print("\n" + "=" * 80)
                print("完整的Render输出示例 | Complete Render Output Example:")
                print("=" * 80)
                print(render_output)
                print("=" * 80)

            finally:
                workspace.close()
