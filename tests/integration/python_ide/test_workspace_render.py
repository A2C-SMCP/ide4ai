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
    workspace = PyWorkspace(
        root_dir=project_root_dir,
        project_name="test_render_workspace",
        diagnostics_timeout=15.0,  # 增加超时时间以适应低配置电脑 / Increase timeout for low-spec computers
    )
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

        workspace = PyWorkspace(root_dir=temp_dir, project_name="test_makefile_workspace", diagnostics_timeout=15.0)
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

        workspace = PyWorkspace(root_dir=temp_dir, project_name="test_mk_workspace", diagnostics_timeout=15.0)
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
            diagnostics_timeout=15.0,
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
            workspace = PyWorkspace(root_dir=temp_dir, project_name="empty_workspace", diagnostics_timeout=15.0)
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

            workspace = PyWorkspace(root_dir=temp_dir, project_name="nested_workspace", diagnostics_timeout=15.0)
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

            workspace = PyWorkspace(root_dir=temp_dir, project_name="special_chars_workspace", diagnostics_timeout=15.0)
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
            workspace = PyWorkspace(
                root_dir=temp_dir, project_name="integration_test_project", diagnostics_timeout=15.0
            )

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


class TestRenderVerboseMode:
    """verbose模式测试 | Verbose mode tests"""

    @pytest.fixture
    def temp_python_project(self) -> Generator[tuple[str, PyWorkspace], Any, None]:
        """
        创建带Python包结构的临时项目 | Create temporary project with Python package structure

        Returns:
            tuple[str, PyWorkspace]: (临时目录路径, workspace实例) | (temp dir path, workspace instance)
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建包结构 | Create package structure
            # project/
            #   mypackage/
            #     __init__.py (with docstring and __all__)
            #     core.py (with docstring and __all__)
            #     utils/
            #       __init__.py (with docstring and __all__)
            #       helpers.py
            #   tests/
            #     test_core.py
            #   README.md

            # 创建mypackage包 | Create mypackage package
            pkg_dir = os.path.join(temp_dir, "mypackage")
            os.makedirs(pkg_dir)

            with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write('''"""
我的包 | My Package

这是一个测试包，用于演示verbose模式
This is a test package for demonstrating verbose mode
"""

__all__ = ["core", "utils"]
''')

            with open(os.path.join(pkg_dir, "core.py"), "w", encoding="utf-8") as f:
                f.write('''"""
核心模块 | Core Module

提供核心功能
Provides core functionality
"""

__all__ = ["process", "validate"]

def process(data):
    """处理数据 | Process data"""
    return data

def validate(data):
    """验证数据 | Validate data"""
    return True
''')

            # 创建utils子包 | Create utils subpackage
            utils_dir = os.path.join(pkg_dir, "utils")
            os.makedirs(utils_dir)

            with open(os.path.join(utils_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write('''"""
工具包 | Utils Package

提供辅助工具函数
Provides utility functions
"""

__all__ = ["helpers"]
''')

            with open(os.path.join(utils_dir, "helpers.py"), "w", encoding="utf-8") as f:
                f.write('''"""辅助函数模块 | Helper functions module"""

def helper_func():
    """辅助函数 | Helper function"""
    pass
''')

            # 创建tests目录 | Create tests directory
            tests_dir = os.path.join(temp_dir, "tests")
            os.makedirs(tests_dir)

            with open(os.path.join(tests_dir, "test_core.py"), "w", encoding="utf-8") as f:
                f.write('''"""测试核心模块 | Test core module"""

def test_process():
    assert True
''')

            # 创建README | Create README
            with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write("# Test Project\n\nThis is a test project.\n")

            workspace = PyWorkspace(root_dir=temp_dir, project_name="verbose_test_project", diagnostics_timeout=15.0)
            yield temp_dir, workspace
            workspace.close()

    def test_render_verbose_false_default(self, temp_python_project):
        """
        测试默认的简化模式（verbose=False）| Test default simplified mode (verbose=False)

        简化模式应该：
        - 目录树部分只显示目录结构，不包含包/模块描述
        - 不包含描述分隔符 "---"
        - 当前打开文件的内容正常显示（这部分不受verbose影响）

        Simplified mode should:
        - Directory tree shows only structure, no package/module descriptions
        - No description separator "---"
        - Current open file content displays normally (not affected by verbose)
        """
        temp_dir, workspace = temp_python_project

        # 打开一个文件 | Open a file
        test_file = os.path.join(temp_dir, "mypackage", "core.py")
        workspace.open_file(uri=f"file://{test_file}")

        # 使用默认模式（verbose=False）| Use default mode (verbose=False)
        render_output = workspace.render()

        # 验证包含基本目录结构 | Verify contains basic directory structure
        assert "项目目录结构" in render_output
        assert "mypackage/" in render_output
        assert "core.py" in render_output

        # 验证目录树部分不包含描述分隔符 | Verify directory tree doesn't contain description separator
        # 注意：分隔符 "---" 只在verbose=True时出现在目录树后
        # Note: Separator "---" only appears after directory tree when verbose=True
        lines = render_output.split("\n")
        dir_tree_section = []
        for i, line in enumerate(lines):
            if "项目目录结构" in line:
                # 收集目录树部分（到"当前打开的文件内容"之前）
                for j in range(i, len(lines)):
                    if "当前打开的文件内容" in lines[j]:
                        break
                    dir_tree_section.append(lines[j])
                break

        dir_tree_text = "\n".join(dir_tree_section)

        # 验证目录树部分不包含描述信息 | Verify directory tree section doesn't contain descriptions
        assert "---" not in dir_tree_text  # 描述分隔符不在目录树部分
        assert "**mypackage/**" not in dir_tree_text  # 包描述格式不在目录树部分

    def test_render_verbose_true_with_descriptions(self, temp_python_project):
        """
        测试详细模式（verbose=True）| Test verbose mode (verbose=True)

        详细模式应该：
        - 显示目录结构
        - 包含Python包/模块的描述信息
        - 包含__all__定义

        Verbose mode should:
        - Show directory structure
        - Include Python package/module descriptions
        - Include __all__ definitions
        """
        temp_dir, workspace = temp_python_project

        # 打开一个文件 | Open a file
        test_file = os.path.join(temp_dir, "mypackage", "core.py")
        workspace.open_file(uri=f"file://{test_file}")

        # 使用详细模式 | Use verbose mode
        render_output = workspace.render(verbose=True)

        # 验证包含基本目录结构 | Verify contains basic directory structure
        assert "项目目录结构" in render_output
        assert "mypackage/" in render_output
        assert "core.py" in render_output

        # 验证包含描述分隔符 | Verify contains description separator
        assert "---" in render_output

        # 验证包含包的描述信息 | Verify contains package descriptions
        assert "**mypackage/**" in render_output
        assert "我的包" in render_output or "My Package" in render_output

        # 验证包含__all__信息 | Verify contains __all__ info
        assert "__all__" in render_output
        assert '["core", "utils"]' in render_output or "core" in render_output

    def test_render_verbose_comparison(self, temp_python_project):
        """
        测试verbose=False和verbose=True的对比 | Test comparison between verbose=False and verbose=True

        验证两种模式的输出确实不同
        Verify the outputs of two modes are indeed different
        """
        temp_dir, workspace = temp_python_project

        # 打开一个文件 | Open a file
        test_file = os.path.join(temp_dir, "mypackage", "utils", "helpers.py")
        workspace.open_file(uri=f"file://{test_file}")

        # 获取两种模式的输出 | Get outputs from both modes
        simple_output = workspace.render(verbose=False)
        verbose_output = workspace.render(verbose=True)

        # 验证两种输出不同 | Verify outputs are different
        assert simple_output != verbose_output

        # 验证verbose输出更长（包含更多信息）| Verify verbose output is longer (contains more info)
        assert len(verbose_output) > len(simple_output)

        # 提取目录树部分进行对比 | Extract directory tree sections for comparison
        def extract_dir_tree_section(output):
            lines = output.split("\n")
            for i, line in enumerate(lines):
                if "项目目录结构" in line:
                    for j in range(i, len(lines)):
                        if "当前打开的文件内容" in lines[j] or "项目快捷命令" in lines[j]:
                            return "\n".join(lines[i:j])
                    return "\n".join(lines[i:])
            return ""

        simple_tree = extract_dir_tree_section(simple_output)
        verbose_tree = extract_dir_tree_section(verbose_output)

        # 验证简化版本的目录树不包含描述 | Verify simplified version's tree doesn't contain descriptions
        assert "**mypackage/**" not in simple_tree
        assert "**utils/**" not in simple_tree

        # 验证详细版本的目录树包含描述 | Verify verbose version's tree contains descriptions
        assert "**mypackage/**" in verbose_tree
        assert "我的包" in verbose_tree or "My Package" in verbose_tree

    def test_render_verbose_without_active_models(self, temp_python_project):
        """
        测试没有active_models时的verbose模式 | Test verbose mode without active_models

        验证在没有打开文件时，verbose模式也能正常工作
        Verify verbose mode works correctly even without open files
        """
        temp_dir, workspace = temp_python_project

        # 不打开任何文件，直接render | Don't open any files, render directly
        simple_output = workspace.render(verbose=False)
        verbose_output = workspace.render(verbose=True)

        # 两种模式都应该包含基本信息 | Both modes should contain basic info
        assert "当前工作区" in simple_output
        assert "当前工作区" in verbose_output

        # 验证verbose模式包含描述信息 | Verify verbose mode contains descriptions
        assert "---" in verbose_output
        assert "**mypackage/**" in verbose_output
        assert "我的包" in verbose_output or "My Package" in verbose_output

        # 验证简化模式不包含描述 | Verify simplified mode doesn't contain descriptions
        assert "---" not in simple_output
        assert "**mypackage/**" not in simple_output

    def test_render_verbose_with_nested_packages(self, temp_python_project):
        """
        测试嵌套包的verbose模式 | Test verbose mode with nested packages

        验证能够正确显示嵌套包的描述信息
        Verify correctly displays descriptions for nested packages
        """
        temp_dir, workspace = temp_python_project

        # 打开嵌套包中的文件 | Open file in nested package
        test_file = os.path.join(temp_dir, "mypackage", "utils", "helpers.py")
        workspace.open_file(uri=f"file://{test_file}")

        render_output = workspace.render(verbose=True)

        # 验证包含父包的描述 | Verify contains parent package description
        assert "**mypackage/**" in render_output
        assert "我的包" in render_output or "My Package" in render_output

        # 验证包含子包的描述 | Verify contains subpackage description
        assert "**utils/**" in render_output or "mypackage/utils/" in render_output
        assert "工具包" in render_output or "Utils Package" in render_output

    def test_render_verbose_minimal_expanded_tree(self, temp_python_project):
        """
        测试verbose模式下的最小化展开目录树 | Test minimally expanded tree in verbose mode

        验证verbose模式使用get_minimal_expanded_tree_with_desc
        Verify verbose mode uses get_minimal_expanded_tree_with_desc
        """
        temp_dir, workspace = temp_python_project

        # 打开深层文件 | Open deep file
        test_file = os.path.join(temp_dir, "mypackage", "utils", "helpers.py")
        workspace.open_file(uri=f"file://{test_file}")

        render_output = workspace.render(verbose=True)

        # 验证路径被正确展开 | Verify path is correctly expanded
        assert "mypackage/" in render_output
        assert "utils/" in render_output
        assert "helpers.py" in render_output

        # 验证标记了当前文件 | Verify current file is marked
        assert "当前文件" in render_output or "Current file" in render_output

        # 验证包含描述信息 | Verify contains descriptions
        assert "---" in render_output
        assert "工具包" in render_output or "Utils Package" in render_output

    def test_render_verbose_idempotent(self, temp_python_project):
        """
        测试verbose模式的幂等性 | Test idempotence of verbose mode

        多次调用应该返回相同结果
        Multiple calls should return same result
        """
        temp_dir, workspace = temp_python_project

        test_file = os.path.join(temp_dir, "mypackage", "core.py")
        workspace.open_file(uri=f"file://{test_file}")

        # 多次调用verbose模式 | Call verbose mode multiple times
        output1 = workspace.render(verbose=True)
        output2 = workspace.render(verbose=True)
        output3 = workspace.render(verbose=True)

        # 验证结果一致 | Verify results are consistent
        assert output1 == output2
        assert output2 == output3

        # 多次调用简化模式 | Call simplified mode multiple times
        simple1 = workspace.render(verbose=False)
        simple2 = workspace.render(verbose=False)

        # 验证简化模式结果一致 | Verify simplified mode results are consistent
        assert simple1 == simple2

    def test_render_verbose_with_empty_package(self):
        """
        测试包含空包的verbose模式 | Test verbose mode with empty packages

        验证空包（没有docstring和__all__）不会导致错误
        Verify empty packages (no docstring and __all__) don't cause errors
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建空包 | Create empty package
            pkg_dir = os.path.join(temp_dir, "empty_pkg")
            os.makedirs(pkg_dir)

            with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write("")  # 空的__init__.py

            test_file = os.path.join(pkg_dir, "module.py")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("# Empty module\npass\n")

            workspace = PyWorkspace(root_dir=temp_dir, project_name="empty_pkg_test", diagnostics_timeout=15.0)
            try:
                workspace.open_file(uri=f"file://{test_file}")

                # verbose模式不应该报错 | Verbose mode should not error
                render_output = workspace.render(verbose=True)

                # 验证基本信息存在 | Verify basic info exists
                assert "项目目录结构" in render_output
                assert "empty_pkg/" in render_output
                assert "module.py" in render_output

            finally:
                workspace.close()
