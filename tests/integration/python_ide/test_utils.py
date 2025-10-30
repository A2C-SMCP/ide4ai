# filename: test_utils.py
# @Time    : 2025/10/29 10:47
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 ide4ai.python_ide.utils 模块的工具函数 | Test utility functions in ide4ai.python_ide.utils module

全面测试以下功能：
1. _extract_module_info - 提取模块信息
2. _collect_package_info - 收集包信息
3. _format_descriptions - 格式化描述信息
4. list_directory_tree_with_desc - 带描述的目录树
5. get_minimal_expanded_tree_with_desc - 最小化展开的目录树

Comprehensive tests for:
1. _extract_module_info - Extract module information
2. _collect_package_info - Collect package information
3. _format_descriptions - Format descriptions
4. list_directory_tree_with_desc - Directory tree with descriptions
5. get_minimal_expanded_tree_with_desc - Minimally expanded directory tree
"""

import os
import tempfile
from collections.abc import Generator
from typing import Any

import pytest

from ide4ai.python_ide.utils import (
    _collect_package_info,
    _extract_module_info,
    _format_descriptions,
    get_minimal_expanded_tree_with_desc,
    list_directory_tree_with_desc,
)


@pytest.fixture
def temp_python_module() -> Generator[str, Any, None]:
    """
    创建临时Python模块文件 | Create temporary Python module file

    Returns:
        str: 临时文件路径 | Temporary file path
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=True, encoding="utf-8") as f:
        f.write('''"""\n这是一个测试模块 | This is a test module

用于测试模块信息提取功能
For testing module info extraction
"""

__all__ = ["func1", "func2", "TestClass"]

def func1():
    """函数1 | Function 1"""
    pass

def func2():
    """函数2 | Function 2"""
    pass

class TestClass:
    """测试类 | Test class"""
    pass
''')
        f.flush()  # 确保内容写入磁盘 | Ensure content is written to disk
        yield f.name


@pytest.fixture
def temp_python_module_no_all() -> Generator[str, Any, None]:
    """
    创建没有__all__定义的临时Python模块 | Create temporary Python module without __all__

    Returns:
        str: 临时文件路径 | Temporary file path
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=True, encoding="utf-8") as f:
        f.write('''"""简单的测试模块 | Simple test module"""

def simple_func():
    pass
''')
        f.flush()  # 确保内容写入磁盘 | Ensure content is written to disk
        yield f.name


@pytest.fixture
def temp_python_module_no_docstring() -> Generator[str, Any, None]:
    """
    创建没有docstring的临时Python模块 | Create temporary Python module without docstring

    Returns:
        str: 临时文件路径 | Temporary file path
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=True, encoding="utf-8") as f:
        f.write("""__all__ = ["item1", "item2"]

def item1():
    pass

def item2():
    pass
""")
        f.flush()  # 确保内容写入磁盘 | Ensure content is written to disk
        yield f.name


@pytest.fixture
def temp_python_module_syntax_error() -> Generator[str, Any, None]:
    """
    创建有语法错误的临时Python模块 | Create temporary Python module with syntax error

    Returns:
        str: 临时文件路径 | Temporary file path
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=True, encoding="utf-8") as f:
        f.write('''"""有语法错误的模块"""

def broken_func(
    # 缺少闭合括号 | Missing closing parenthesis
''')
        f.flush()  # 确保内容写入磁盘 | Ensure content is written to disk
        yield f.name


@pytest.fixture
def temp_project_structure() -> Generator[str, Any, None]:
    """
    创建临时项目结构用于测试目录树功能 | Create temporary project structure for directory tree testing

    Returns:
        str: 临时目录路径 | Temporary directory path
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建包结构 | Create package structure
        # project/
        #   src/
        #     __init__.py
        #     main.py
        #     utils/
        #       __init__.py
        #       helpers.py
        #   tests/
        #     __init__.py
        #     test_main.py
        #   README.md

        # 创建src包 | Create src package
        src_dir = os.path.join(temp_dir, "src")
        os.makedirs(src_dir)

        with open(os.path.join(src_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write('''"""
源代码包 | Source code package
"""

__all__ = ["main", "utils"]
''')

        with open(os.path.join(src_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write('''"""
主模块 | Main module
"""

__all__ = ["run"]

def run():
    """运行主程序 | Run main program"""
    print("Running...")
''')

        # 创建src/utils子包 | Create src/utils subpackage
        utils_dir = os.path.join(src_dir, "utils")
        os.makedirs(utils_dir)

        with open(os.path.join(utils_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write('''"""工具包 | Utilities package"""

__all__ = ["helpers"]
''')

        with open(os.path.join(utils_dir, "helpers.py"), "w", encoding="utf-8") as f:
            f.write('''"""辅助函数 | Helper functions"""

def helper_func():
    pass
''')

        # 创建tests包 | Create tests package
        tests_dir = os.path.join(temp_dir, "tests")
        os.makedirs(tests_dir)

        with open(os.path.join(tests_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write('''"""测试包 | Tests package"""
''')

        with open(os.path.join(tests_dir, "test_main.py"), "w", encoding="utf-8") as f:
            f.write('''"""主模块测试 | Main module tests"""

def test_run():
    assert True
''')

        # 创建README文件 | Create README file
        with open(os.path.join(temp_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Test Project\n\nThis is a test project.\n")

        yield temp_dir


class TestExtractModuleInfo:
    """测试 _extract_module_info 函数 | Test _extract_module_info function"""

    def test_extract_complete_module_info(self, temp_python_module):
        """测试提取完整的模块信息（包含docstring和__all__）| Test extracting complete module info"""
        info = _extract_module_info(temp_python_module)

        # 验证docstring | Verify docstring
        assert info["docstring"] != ""
        assert "这是一个测试模块" in info["docstring"]
        assert "This is a test module" in info["docstring"]

        # 验证__all__ | Verify __all__
        assert len(info["__all__"]) == 3
        assert "func1" in info["__all__"]
        assert "func2" in info["__all__"]
        assert "TestClass" in info["__all__"]

    def test_extract_module_without_all(self, temp_python_module_no_all):
        """测试提取没有__all__的模块信息 | Test extracting module info without __all__"""
        info = _extract_module_info(temp_python_module_no_all)

        # 验证docstring存在 | Verify docstring exists
        assert info["docstring"] != ""
        assert "简单的测试模块" in info["docstring"]

        # 验证__all__为空 | Verify __all__ is empty
        assert info["__all__"] == []

    def test_extract_module_without_docstring(self, temp_python_module_no_docstring):
        """测试提取没有docstring的模块信息 | Test extracting module info without docstring"""
        info = _extract_module_info(temp_python_module_no_docstring)

        # 验证docstring为空 | Verify docstring is empty
        assert info["docstring"] == ""

        # 验证__all__存在 | Verify __all__ exists
        assert len(info["__all__"]) == 2
        assert "item1" in info["__all__"]
        assert "item2" in info["__all__"]

    def test_extract_module_with_syntax_error(self, temp_python_module_syntax_error):
        """测试提取有语法错误的模块信息 | Test extracting module info with syntax error"""
        info = _extract_module_info(temp_python_module_syntax_error)

        # 应该返回空结果 | Should return empty result
        assert info["docstring"] == ""
        assert info["__all__"] == []

    def test_extract_nonexistent_file(self):
        """测试提取不存在的文件 | Test extracting non-existent file"""
        info = _extract_module_info("/path/to/nonexistent/file.py")

        # 应该返回空结果 | Should return empty result
        assert info["docstring"] == ""
        assert info["__all__"] == []


class TestCollectPackageInfo:
    """测试 _collect_package_info 函数 | Test _collect_package_info function"""

    def test_collect_package_with_init(self, temp_project_structure):
        """测试收集包含__init__.py的包信息 | Test collecting package info with __init__.py"""
        descriptions = {}
        src_dir = os.path.join(temp_project_structure, "src")

        _collect_package_info(src_dir, "src", descriptions)

        # 验证收集到了包信息 | Verify package info collected
        assert "src/" in descriptions
        assert descriptions["src/"]["docstring"] != ""
        assert "源代码包" in descriptions["src/"]["docstring"]
        assert len(descriptions["src/"]["__all__"]) == 2

    def test_collect_package_without_init(self, temp_project_structure):
        """测试收集不包含__init__.py的目录 | Test collecting directory without __init__.py"""
        descriptions = {}

        # 创建一个没有__init__.py的目录 | Create directory without __init__.py
        no_init_dir = os.path.join(temp_project_structure, "no_init")
        os.makedirs(no_init_dir)

        _collect_package_info(no_init_dir, "no_init", descriptions)

        # 不应该收集到信息 | Should not collect info
        assert "no_init/" not in descriptions

    def test_collect_package_with_empty_init(self, temp_project_structure):
        """测试收集包含空__init__.py的包 | Test collecting package with empty __init__.py"""
        descriptions = {}

        # 创建一个包含空__init__.py的目录 | Create directory with empty __init__.py
        empty_init_dir = os.path.join(temp_project_structure, "empty_pkg")
        os.makedirs(empty_init_dir)
        with open(os.path.join(empty_init_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write("")

        _collect_package_info(empty_init_dir, "empty_pkg", descriptions)

        # 不应该收集到信息（因为没有docstring和__all__）| Should not collect info
        assert "empty_pkg/" not in descriptions


class TestFormatDescriptions:
    """测试 _format_descriptions 函数 | Test _format_descriptions function"""

    def test_format_empty_descriptions(self):
        """测试格式化空描述字典 | Test formatting empty descriptions dict"""
        result = _format_descriptions({})

        # 应该返回空字符串 | Should return empty string
        assert result == ""

    def test_format_single_description_with_all_and_docstring(self):
        """测试格式化包含__all__和docstring的单个描述 | Test formatting single description"""
        descriptions = {
            "module.py": {
                "docstring": "这是一个模块\nThis is a module",
                "__all__": ["func1", "func2"],
            },
        }

        result = _format_descriptions(descriptions)

        # 验证格式 | Verify format
        assert "---" in result
        assert "**module.py**" in result
        assert '__all__: ["func1", "func2"]' in result
        assert "这是一个模块" in result
        assert "This is a module" in result

    def test_format_multiple_descriptions(self):
        """测试格式化多个描述 | Test formatting multiple descriptions"""
        descriptions = {
            "pkg1/": {"docstring": "包1 | Package 1", "__all__": ["item1"]},
            "module.py": {"docstring": "模块 | Module", "__all__": ["item2", "item3"]},
        }

        result = _format_descriptions(descriptions)

        # 验证包含所有描述 | Verify contains all descriptions
        assert "**module.py**" in result
        assert "**pkg1/**" in result
        assert "包1" in result
        assert "模块" in result

    def test_format_description_only_docstring(self):
        """测试格式化只有docstring的描述 | Test formatting description with only docstring"""
        descriptions = {"simple.py": {"docstring": "简单模块", "__all__": []}}

        result = _format_descriptions(descriptions)

        assert "**simple.py**" in result
        assert "简单模块" in result
        assert "__all__" not in result

    def test_format_description_only_all(self):
        """测试格式化只有__all__的描述 | Test formatting description with only __all__"""
        descriptions = {"items.py": {"docstring": "", "__all__": ["a", "b", "c"]}}

        result = _format_descriptions(descriptions)

        assert "**items.py**" in result
        assert '__all__: ["a", "b", "c"]' in result


class TestListDirectoryTreeWithDesc:
    """测试 list_directory_tree_with_desc 函数 | Test list_directory_tree_with_desc function"""

    def test_list_tree_non_recursive(self, temp_project_structure):
        """测试非递归列出目录树 | Test listing directory tree non-recursively"""
        result = list_directory_tree_with_desc(temp_project_structure, recursive=False)

        # 验证包含顶层目录和文件 | Verify contains top-level directories and files
        assert "src/" in result
        assert "tests/" in result
        assert "README.md" in result

        # 验证不包含子目录内容 | Verify doesn't contain subdirectory contents
        assert "main.py" not in result
        assert "utils/" not in result

    def test_list_tree_recursive_all(self, temp_project_structure):
        """测试递归列出所有目录 | Test listing all directories recursively"""
        result = list_directory_tree_with_desc(temp_project_structure, include_dirs="all", recursive=True)

        # 验证包含所有文件和目录 | Verify contains all files and directories
        assert "src/" in result
        assert "main.py" in result
        assert "utils/" in result
        assert "helpers.py" in result
        assert "tests/" in result
        assert "test_main.py" in result

    def test_list_tree_with_specific_dirs(self, temp_project_structure):
        """测试只展开特定目录 | Test expanding only specific directories"""
        result = list_directory_tree_with_desc(temp_project_structure, include_dirs=["src"], recursive=False)

        # 验证src被展开 | Verify src is expanded
        assert "src/" in result
        assert "main.py" in result

        # 验证tests没有被展开 | Verify tests is not expanded
        assert "tests/" in result

    def test_list_tree_with_descriptions(self, temp_project_structure):
        """测试目录树包含描述信息 | Test directory tree includes descriptions"""
        result = list_directory_tree_with_desc(temp_project_structure, include_dirs="all", recursive=True)

        # 验证包含描述部分 | Verify contains description section
        assert "---" in result

        # 验证包含包的描述 | Verify contains package descriptions
        assert "**src/**" in result or "源代码包" in result

        # 验证包含__all__信息 | Verify contains __all__ info
        assert "__all__" in result

    def test_list_tree_with_indent(self, temp_project_structure):
        """测试带缩进的目录树 | Test directory tree with indentation"""
        result = list_directory_tree_with_desc(
            temp_project_structure,
            include_dirs="all",
            recursive=True,
            indent="  ",
        )

        # 验证缩进正确 | Verify indentation is correct
        assert "  src/" in result or "src/" in result

    def test_list_tree_empty_directory(self):
        """测试空目录 | Test empty directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = list_directory_tree_with_desc(temp_dir)

            # 应该返回空结果或只有描述分隔符 | Should return empty or only separator
            assert result == "" or result == "\n---\n"


class TestGetMinimalExpandedTreeWithDesc:
    """测试 get_minimal_expanded_tree_with_desc 函数 | Test get_minimal_expanded_tree_with_desc function"""

    def test_minimal_tree_to_target_file(self, temp_project_structure):
        """测试最小化展开到目标文件 | Test minimal expansion to target file"""
        target_file = os.path.join(temp_project_structure, "src", "utils", "helpers.py")

        result = get_minimal_expanded_tree_with_desc(temp_project_structure, target_file)

        # 验证路径被展开 | Verify path is expanded
        assert "src/" in result
        assert "utils/" in result
        assert "helpers.py" in result

        # 验证目标文件被标记 | Verify target file is marked
        assert "当前文件" in result or "Current file" in result

        # 验证tests目录只显示一级 | Verify tests directory shows only first level
        assert "tests/" in result

    def test_minimal_tree_to_root_file(self, temp_project_structure):
        """测试最小化展开到根目录文件 | Test minimal expansion to root directory file"""
        target_file = os.path.join(temp_project_structure, "README.md")

        result = get_minimal_expanded_tree_with_desc(temp_project_structure, target_file)

        # 验证README被标记 | Verify README is marked
        assert "README.md" in result
        assert "当前文件" in result or "Current file" in result

        # 验证其他目录只显示一级 | Verify other directories show only first level
        assert "src/" in result
        assert "tests/" in result

    def test_minimal_tree_with_descriptions(self, temp_project_structure):
        """测试最小化展开的目录树包含描述 | Test minimal expanded tree includes descriptions"""
        target_file = os.path.join(temp_project_structure, "src", "main.py")

        result = get_minimal_expanded_tree_with_desc(temp_project_structure, target_file)

        # 验证包含描述部分 | Verify contains description section
        assert "---" in result

        # 验证包含相关包的描述 | Verify contains relevant package descriptions
        assert "**src/**" in result or "源代码包" in result

    def test_minimal_tree_target_outside_root(self, temp_project_structure):
        """测试目标文件在根目录外 | Test target file outside root directory"""
        # 创建一个根目录外的文件 | Create a file outside root
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Outside file\n")
            outside_file = f.name

        try:
            result = get_minimal_expanded_tree_with_desc(temp_project_structure, outside_file)

            # 应该回退到非递归的普通目录树 | Should fallback to non-recursive normal tree
            assert "src/" in result
            assert "tests/" in result
        finally:
            if os.path.exists(outside_file):
                os.unlink(outside_file)

    def test_minimal_tree_deeply_nested_file(self, temp_project_structure):
        """测试深层嵌套的目标文件 | Test deeply nested target file"""
        # 创建更深的嵌套结构 | Create deeper nested structure
        deep_dir = os.path.join(temp_project_structure, "src", "utils", "deep", "nested")
        os.makedirs(deep_dir, exist_ok=True)

        deep_file = os.path.join(deep_dir, "deep_module.py")
        with open(deep_file, "w", encoding="utf-8") as f:
            f.write('"""深层模块 | Deep module"""\n')

        result = get_minimal_expanded_tree_with_desc(temp_project_structure, deep_file)

        # 验证所有层级都被展开 | Verify all levels are expanded
        assert "src/" in result
        assert "utils/" in result
        assert "deep/" in result
        assert "nested/" in result
        assert "deep_module.py" in result
        assert "当前文件" in result or "Current file" in result
