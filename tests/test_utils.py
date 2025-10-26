# -*- coding: utf-8 -*-
# filename: test_utils.py
# @Time    : 2024/5/9 11:11
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from tfrobot.drive.tool.ides.utils import is_subdirectory, list_directory_tree


def test_list_directory_tree_all_recursive(fs):
    # Setup - 创建模拟目录和文件
    fs.create_dir("/test/dir1")
    fs.create_dir("/test/dir2")
    fs.create_file("/test/dir1/file1.txt")
    fs.create_file("/test/dir2/file2.txt")

    # Action - 调用函数
    result = list_directory_tree("/test", include_dirs="all", recursive=True)

    # Assert - 检查结果是否符合预期
    expected = "dir1/\n  file1.txt\ndir2/\n  file2.txt"
    assert result == expected


def test_list_directory_tree_specific_dirs(fs):
    # Setup
    fs.create_dir("/test/dir1")
    fs.create_dir("/test/dir2")
    fs.create_dir("/test/dir3")
    fs.create_file("/test/dir1/file1.txt")
    fs.create_file("/test/dir3/file3.txt")

    # Action
    result = list_directory_tree("/test", include_dirs=["dir1", "dir3"], recursive=False)

    # Assert
    expected = "dir1/\n  file1.txt\ndir2/\ndir3/\n  file3.txt"
    assert result == expected


def test_list_directory_tree_no_recursion(fs):
    # Setup
    fs.create_dir("/test/dir1")
    fs.create_dir("/test/dir1/subdir1")
    fs.create_file("/test/dir1/subdir1/file1.txt")

    # Action
    result = list_directory_tree("/test", include_dirs="all", recursive=False)

    # Assert
    expected = "dir1/\n  subdir1/\n    file1.txt"
    assert result.strip() == expected.strip()


def test_list_spec_directory_tree_no_recursion(fs):
    # Setup
    fs.create_dir("/test/dir1")
    fs.create_dir("/test/dir1/subdir1")
    fs.create_file("/test/dir1/subdir1/file1.txt")

    # Action
    result = list_directory_tree("/test", include_dirs=["dir1"], recursive=False)

    # Assert
    expected = "dir1/\n  subdir1/"
    assert result.strip() == expected.strip()


def test_is_sub_directory(fs):
    # Setup
    fs.create_dir("/test/dir1")

    # Action
    result = is_subdirectory("/test/dir1", "/test")
    not_result = is_subdirectory("/test", "/test/dir1")

    # Assert
    assert result is True
    assert not_result is False
