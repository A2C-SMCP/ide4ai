# filename: test_workspace.py
# @Time    : 2024/5/9 19:32
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import os
from collections.abc import Generator
from typing import Any

import pytest
from pydantic import AnyUrl

from ide4ai.environment.workspace.schema import (
    Position,
    Range,
    SingleEditOperation,
)
from ide4ai.python_ide.const import DEFAULT_SYMBOL_VALUE_SET
from ide4ai.python_ide.workspace import PyWorkspace


@pytest.fixture
def project_root_dir() -> str:
    return os.path.dirname(__file__) + "/virtual_project"


@pytest.fixture
def py_workspace(project_root_dir) -> Generator[PyWorkspace, Any, None]:
    # 使用更长的超时时间以适应低配置电脑 / Use longer timeout for low-spec computers
    workspace = PyWorkspace(
        root_dir=project_root_dir,
        project_name="test_python_workspace",
        diagnostics_timeout=15.0,  # 增加到15秒 / Increase to 15 seconds
    )
    yield workspace
    workspace.close()


def test_py_workspace_init(py_workspace) -> None:
    """
    测试PyWorkspace初始化
    Args:
        py_workspace:

    Returns:

    """
    assert py_workspace is not None


def test_py_workspace_read_file(project_root_dir, py_workspace) -> None:
    test_file_path = project_root_dir + "/file_for_test_read.py"
    test_file_uri = "file://" + test_file_path
    content = py_workspace.read_file(uri=test_file_uri)
    print(content)
    with open(test_file_path) as f:
        read_res = f.read()
    assert read_res[:20] in content  # 因为文件较大，直接使用in判断会比较慢，所以截取20个字符做判断
    print(f"内容长度: {len(content)}")


def test_py_workspace_render(project_root_dir, py_workspace) -> None:
    """
    测试PyWorkspace渲染

    测试激活Model，测试渲染环境

    Args:
        project_root_dir:
        py_workspace:

    Returns:

    """
    render_1 = project_root_dir + "/file_for_render_1.py"
    current_file = project_root_dir + "/file_for_test_read.py"
    py_workspace.open_file(uri=f"file://{render_1}")
    py_workspace.open_file(uri=f"file://{current_file}")
    assert AnyUrl(f"file://{current_file}") == py_workspace.active_models[-1].uri
    py_workspace.active_model(py_workspace.get_model(uri=f"file://{render_1}").m_id)
    assert AnyUrl(f"file://{render_1}") == py_workspace.active_models[-1].uri
    py_workspace.active_model(py_workspace.get_model(uri=f"file://{current_file}").m_id)
    text = py_workspace.render()
    assert "当前工作区" in text and "Class: LSPCommand" in text


def test_py_workspace_create_and_apply_edit(project_root_dir, py_workspace) -> None:
    """
    测试PyWorkspace应用编辑

    Args:
        project_root_dir:
        py_workspace:

    Returns:

    """
    test_file_path = project_root_dir + "/file_for_edit.py"
    test_file_uri = "file://" + test_file_path

    # 备份原始文件内容 / Backup original file content
    with open(test_file_path) as f:
        original_content = f.read()

    try:
        py_workspace.open_file(uri=test_file_uri)
        symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
        print(symbols)
        assert "Class: A" in symbols
        new_text = "class B:\n    b: int\n    c: int"
        edit = SingleEditOperation(
            range=Range(start_position=Position(8, 1), end_position=Position(10, 11)),
            text=new_text,
        )
        edit_res, diagnostics = py_workspace.apply_edit(uri=test_file_uri, edits=[edit], compute_undo_edits=True)
        # 诊断信息可能为None（超时）或有值，这里不强制要求 / Diagnostics may be None (timeout) or have value
        # 主要验证返回值结构正确 / Mainly verify return value structure is correct
        symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
        print(symbols)
        assert "Class: B" in symbols
        undo_edit, _ = py_workspace.apply_edit(
            uri=test_file_uri,
            edits=[e.to_single_edit_operation() for e in edit_res],
            compute_undo_edits=False,
        )
        assert not undo_edit
        symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
        print(symbols)
        assert "Class: A" in symbols
    finally:
        # 恢复原始文件内容 / Restore original file content
        with open(test_file_path, "w") as f:
            f.write(original_content)


@pytest.fixture
def file_uri(project_root_dir) -> str:
    return f"file://{project_root_dir}/testfile.py"


def test_create_file_success(py_workspace, file_uri) -> None:
    """
    测试成功创建一个新文件。
    """
    tm, diagnostics = py_workspace.create_file(uri=file_uri)
    assert tm is not None
    # 诊断信息可能为None（超时）或有值 / Diagnostics may be None (timeout) or have value
    # 主要验证返回值结构正确，包含两个元素 / Mainly verify return structure is correct with two elements
    assert os.path.exists(file_uri[7:])  # Removing 'file://' prefix


def test_create_file_with_init_content(py_workspace, file_uri) -> None:
    """
    测试创建文件时指定初始内容。
    """
    tm, diagnostics = py_workspace.create_file(uri=file_uri, init_content="print('Hello, World!')")
    tm.save()
    assert tm is not None
    assert diagnostics is not None
    assert os.path.exists(file_uri[7:])
    with open(file_uri[7:]) as f:
        content = f.read()
    assert content.endswith("print('Hello, World!')") and content.startswith("# -*- coding: utf-8 -*-")


def test_create_file_with_not_header_generator(project_root_dir, file_uri) -> None:
    """如果PyWorkspace没有header_generator，不会添加文件头"""
    py_workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_python_workspace", header_generators={})
    try:
        tm, diagnostics = py_workspace.create_file(uri=file_uri, init_content="print(undefined_var)")
        tm.save()
        assert tm is not None
        assert diagnostics is not None
        assert os.path.exists(file_uri[7:])
        with open(file_uri[7:]) as f:
            content = f.read()
        assert content.endswith("print(undefined_var)") and content.startswith("print(undefined_var)")
    finally:
        py_workspace.close()


def test_overwrite_existing_file(py_workspace, file_uri) -> None:
    """
    测试如果文件存在，设置overwrite=True后能成功覆盖文件。
    """
    # 先创建一个文件
    py_workspace.create_file(uri=file_uri)
    # 再次创建同一文件并尝试覆盖
    tm, diagnostics = py_workspace.create_file(uri=file_uri, overwrite=True)
    assert tm is not None
    assert diagnostics is not None
    assert os.path.exists(file_uri[7:])


def test_ignore_existing_file(py_workspace, file_uri) -> None:
    """
    测试如果文件存在，并设置ignore_if_exists=True，不进行任何操作。
    """
    # 先创建一个文件
    py_workspace.create_file(uri=file_uri)
    # 再次创建同一文件并设置忽略存在的文件
    tm, diagnostics = py_workspace.create_file(uri=file_uri, ignore_if_exists=True)
    assert tm is None
    assert diagnostics is None


def test_error_when_file_exists_without_overwrite(py_workspace, file_uri) -> None:
    """
    测试文件已存在且没有设置覆盖时应抛出异常。
    """
    # 先创建一个文件
    py_workspace.create_file(uri=file_uri)
    # 再次创建同一文件，没有设置overwrite或ignore_if_exists
    with pytest.raises(FileExistsError):
        py_workspace.create_file(uri=file_uri)


def test_handle_creation_error(py_workspace, file_uri, monkeypatch) -> None:
    """
    测试创建文件时发生错误（如权限问题）。
    """

    def mock_open(*args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr("builtins.open", mock_open)
    with pytest.raises(IOError) as exc_info:
        py_workspace.create_file(uri=file_uri)
    assert "Permission denied" in str(exc_info.value)


# 使用fixture清理创建的文件
@pytest.fixture(autouse=True)
def clean_up(file_uri):
    yield
    file_path = file_uri[7:]
    if os.path.exists(file_path):
        os.remove(file_path)


def test_step_open_file_success(py_workspace, project_root_dir):
    action = {
        "category": "workspace",
        "action_name": "open_file",
        "action_args": {"uri": f"file://{project_root_dir}/file_for_test_read.py"},
    }
    observation, reward, done, success, _ = py_workspace.step(action)
    assert success is True
    assert reward == 100
    assert done is True
    assert "ACTION_CATEGORY_MAP: dict[int, str] = {" in observation["obs"]


def test_step_apply_edit_success(py_workspace, project_root_dir):
    action = {
        "category": "workspace",
        "action_name": "apply_edit",
        "action_args": {
            "uri": f"file://{project_root_dir}/file_for_test.py",
            "edits": [],
        },
    }
    observation, reward, done, success, _ = py_workspace.step(action)
    assert success is False
    assert reward == 0
    assert done is True


def test_apply_edit_with_auto_diagnostics(project_root_dir) -> None:
    """
    测试apply_edit后自动拉取诊断信息 / Test auto-pull diagnostics after apply_edit

    验证在编辑文件后，系统会自动拉取诊断信息并返回
    Verify that diagnostics are automatically pulled and returned after editing a file
    """
    import tempfile

    # 创建一个临时Python文件 / Create a temporary Python file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir=project_root_dir) as f:
        f.write(
            """# -*- coding: utf-8 -*-
# Test file
def test_function():
    x = 1
    return x
""",
        )
        temp_file_path = f.name

    temp_file_uri = f"file://{temp_file_path}"
    workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_auto_diagnostics")

    try:
        # 打开文件 / Open file
        workspace.open_file(uri=temp_file_uri)

        # 编辑文件，引入一个错误 / Edit file to introduce an error
        edit = SingleEditOperation(
            range=Range(start_position=Position(6, 1), end_position=Position(6, 1)),
            text="print(undefined_variable)\n",  # 引入未定义变量错误 / Introduce undefined variable error
        )

        # 应用编辑并获取诊断信息 / Apply edit and get diagnostics
        undo_edits, diagnostics = workspace.apply_edit(uri=temp_file_uri, edits=[edit], compute_undo_edits=True)

        # 验证返回了撤销编辑 / Verify undo edits are returned
        assert undo_edits is not None

        # 验证返回了诊断信息 / Verify diagnostics are returned
        assert diagnostics is not None
        print(f"Diagnostics after edit: {diagnostics}")

        # 验证诊断信息包含错误 / Verify diagnostics contain error
        if hasattr(diagnostics, "items") and diagnostics.items:
            # 应该包含 "undefined_variable" 相关的错误 / Should contain error about "undefined_variable"
            has_error = any(
                "undefined_variable" in str(getattr(diagnostic, "message", "")).lower()
                for diagnostic in diagnostics.items
            )
            assert has_error, f"Expected error about undefined_variable, got: {diagnostics.items}"

    finally:
        workspace.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def test_create_file_with_auto_diagnostics(project_root_dir) -> None:
    """
    测试create_file后自动拉取诊断信息 / Test auto-pull diagnostics after create_file

    验证在创建文件后，系统会自动拉取诊断信息并返回
    Verify that diagnostics are automatically pulled and returned after creating a file
    """

    temp_file_path = os.path.join(project_root_dir, "test_new_file_with_error.py")
    temp_file_uri = f"file://{temp_file_path}"
    workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_create_diagnostics")

    try:
        # 创建文件并包含错误代码 / Create file with error code
        tm, diagnostics = workspace.create_file(
            uri=temp_file_uri,
            init_content="import os\nprint(undefined_var)",  # 引入未定义变量 / Introduce undefined variable
        )

        # 验证文件创建成功 / Verify file created successfully
        assert tm is not None

        # 验证返回了诊断信息 / Verify diagnostics are returned
        assert diagnostics is not None
        print(f"Diagnostics after create: {diagnostics}")

        # 验证诊断信息包含错误 / Verify diagnostics contain error
        if hasattr(diagnostics, "items") and diagnostics.items:
            has_error = any(
                "undefined_var" in str(getattr(diagnostic, "message", "")).lower() for diagnostic in diagnostics.items
            )
            assert has_error, f"Expected error about undefined_var, got: {diagnostics.items}"

    finally:
        workspace.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def test_apply_edit_with_syntax_error_must_have_diagnostics(project_root_dir) -> None:
    """
    测试apply_edit引入语法错误后必须返回诊断信息 / Test apply_edit with syntax error must return diagnostics

    故意引入语法错误，验证诊断信息必须不为空
    Intentionally introduce syntax errors and verify diagnostics must not be None
    """
    import tempfile
    import time

    # 创建一个临时Python文件 / Create a temporary Python file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir=project_root_dir) as f:
        f.write(
            """# -*- coding: utf-8 -*-
# Test file
def valid_function():
    return 42
""",
        )
        temp_file_path = f.name

    temp_file_uri = f"file://{temp_file_path}"
    workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_syntax_error_diagnostics")

    try:
        # 打开文件 / Open file
        workspace.open_file(uri=temp_file_uri)

        # 等待LSP初始化完成 / Wait for LSP initialization
        time.sleep(1)

        # 编辑文件，引入明显的语法错误 / Edit file to introduce obvious syntax errors
        edit = SingleEditOperation(
            range=Range(start_position=Position(5, 1), end_position=Position(5, 1)),
            text="""
# 引入多个语法错误 / Introduce multiple syntax errors
import os
print(undefined_var)  # 未定义变量 / Undefined variable
result = nonexistent_func()  # 未定义函数 / Undefined function
x = unknown_module.something  # 未导入模块 / Unimported module
""",
        )

        # 应用编辑并获取诊断信息 / Apply edit and get diagnostics
        undo_edits, diagnostics = workspace.apply_edit(uri=temp_file_uri, edits=[edit], compute_undo_edits=True)

        # 验证返回了撤销编辑 / Verify undo edits are returned
        assert undo_edits is not None, "应该返回撤销编辑 / Should return undo edits"

        # 验证返回了诊断信息（不能为空）/ Verify diagnostics are returned (must not be None)
        assert diagnostics is not None, (
            "引入语法错误后必须返回诊断信息 / Diagnostics must be returned after introducing syntax errors"
        )

        # 验证诊断信息包含错误项 / Verify diagnostics contain error items
        assert hasattr(diagnostics, "items"), "诊断结果应该有items属性 / Diagnostics should have items attribute"
        assert diagnostics.items, "诊断信息不应为空列表 / Diagnostics items should not be empty"
        assert len(diagnostics.items) >= 3, (
            f"应该至少检测到3个错误，实际检测到{len(diagnostics.items)}个 / "
            f"Should detect at least 3 errors, actually detected {len(diagnostics.items)}"
        )

        # 验证包含预期的错误信息 / Verify contains expected error messages
        error_messages = [str(getattr(d, "message", "")).lower() for d in diagnostics.items]
        print(f"检测到的错误信息 / Detected error messages: {error_messages}")

        has_undefined_var = any("undefined_var" in msg for msg in error_messages)
        has_nonexistent_func = any("nonexistent_func" in msg for msg in error_messages)
        has_unknown_module = any("unknown_module" in msg for msg in error_messages)

        assert has_undefined_var or has_nonexistent_func or has_unknown_module, (
            f"应该检测到至少一个预期的错误，实际错误信息: {error_messages} / "
            f"Should detect at least one expected error, actual messages: {error_messages}"
        )

    finally:
        workspace.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def test_create_file_with_syntax_error_must_have_diagnostics(project_root_dir) -> None:
    """
    测试create_file创建带语法错误的文件后必须返回诊断信息 / Test create_file with syntax error must return diagnostics

    故意创建包含语法错误的文件，验证诊断信息必须不为空
    Intentionally create file with syntax errors and verify diagnostics must not be None
    """

    temp_file_path = os.path.join(project_root_dir, "test_file_with_multiple_errors.py")
    temp_file_uri = f"file://{temp_file_path}"
    workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_create_syntax_error")

    try:
        # 创建文件并包含多个明显的语法错误 / Create file with multiple obvious syntax errors
        tm, diagnostics = workspace.create_file(
            uri=temp_file_uri,
            init_content="""import sys

# 多个未定义的变量和函数 / Multiple undefined variables and functions
print(undefined_variable_1)
print(os.getenv("test"))
result = undefined_function()
data = another_undefined_var
obj = nonexistent_module.method()
""",
        )

        # 验证文件创建成功 / Verify file created successfully
        assert tm is not None, "文件应该创建成功 / File should be created successfully"

        # 验证返回了诊断信息（不能为空）/ Verify diagnostics are returned (must not be None)
        assert diagnostics is not None, (
            "创建包含语法错误的文件后必须返回诊断信息 / Diagnostics must be returned after creating file with syntax errors"
        )

        # 验证诊断信息包含错误项 / Verify diagnostics contain error items
        assert hasattr(diagnostics, "items"), "诊断结果应该有items属性 / Diagnostics should have items attribute"
        assert diagnostics.items, "诊断信息不应为空列表 / Diagnostics items should not be empty"
        assert len(diagnostics.items) >= 4, (
            f"应该至少检测到4个错误，实际检测到{len(diagnostics.items)}个 / "
            f"Should detect at least 4 errors, actually detected {len(diagnostics.items)}"
        )

        # 验证包含预期的错误信息 / Verify contains expected error messages
        error_messages = [str(getattr(d, "message", "")).lower() for d in diagnostics.items]
        print(f"检测到的错误信息 / Detected error messages: {error_messages}")

        # 至少应该检测到一些未定义的变量或函数 / Should detect at least some undefined variables or functions
        has_undefined_errors = any("undefined" in msg or "not defined" in msg for msg in error_messages)
        assert has_undefined_errors, (
            f"应该检测到未定义变量或函数的错误，实际错误信息: {error_messages} / "
            f"Should detect undefined variable or function errors, actual messages: {error_messages}"
        )

    finally:
        workspace.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def test_workspace_pull_diagnostics_with_error_file(project_root_dir) -> None:
    """
    测试使用workspace封装的方法进行文件诊断（类似test_lsp_diagnostic_notification）
    Test file diagnostics using workspace wrapper methods (similar to test_lsp_diagnostic_notification)

    使用workspace提供的open_file, apply_edit, pull_diagnostics等封装方法，
    验证workspace的LSP诊断功能正常工作
    Use workspace's open_file, apply_edit, pull_diagnostics wrapper methods to verify
    that workspace's LSP diagnostic functionality works correctly

    Returns:

    """
    import tempfile

    # 创建一个包含错误的临时Python文件 / Create a temporary Python file with errors
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir=project_root_dir) as f:
        f.write(
            """# -*- coding: utf-8 -*-
# filename: fake_py_with_err.py
# @Time    : 2024/4/29 10:24
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import pydantic


def test():
    print("pydantic")


print(os.path)
""",
        )
        temp_file_path = f.name

    temp_file_uri = f"file://{temp_file_path}"

    # 创建workspace实例 / Create workspace instance
    workspace = PyWorkspace(root_dir=project_root_dir, project_name="test_diagnostics_workspace")

    try:
        # 1. 使用workspace的open_file方法打开文件 / Use workspace's open_file method to open file
        text_model = workspace.open_file(uri=temp_file_uri)
        assert text_model is not None, "文件打开失败 / Failed to open file"
        assert text_model.uri == AnyUrl(temp_file_uri), "文件URI不匹配 / File URI mismatch"

        # 2. 使用workspace的apply_edit方法编辑文件 / Use workspace's apply_edit method to edit file
        # 在第一行第二个字符位置插入字符'a' / Insert character 'a' at position (1, 2)
        edit = SingleEditOperation(
            range=Range(start_position=Position(1, 2), end_position=Position(1, 2)),
            text="a",
        )
        undo_edits, auto_diagnostics = workspace.apply_edit(uri=temp_file_uri, edits=[edit], compute_undo_edits=True)
        assert undo_edits is not None, "编辑操作失败 / Edit operation failed"
        # 验证自动拉取的诊断信息 / Verify auto-pulled diagnostics
        assert auto_diagnostics is not None, "编辑后应自动返回诊断信息 / Diagnostics should be auto-returned after edit"

        # 3. 使用workspace的pull_diagnostics方法拉取诊断信息 / Use workspace's pull_diagnostics method to pull diagnostics
        diagnostics_result = workspace.pull_diagnostics(uri=temp_file_uri, timeout=20.0)

        assert diagnostics_result is not None, (
            "未能获取到诊断信息，LSP可能未正常工作 / Failed to get diagnostics, LSP may not be working properly"
        )
        print(f"diagnostic result is: {diagnostics_result}")

        # 4. 验证诊断结果包含预期的错误信息 / Verify diagnostics contain expected error
        # Pull Diagnostics返回的是RelatedFullDocumentDiagnosticReport或RelatedUnchangedDocumentDiagnosticReport
        # Pull Diagnostics returns RelatedFullDocumentDiagnosticReport or RelatedUnchangedDocumentDiagnosticReport
        if hasattr(diagnostics_result, "items"):
            # 如果是full report，items字段包含诊断列表 / If it's a full report, items field contains diagnostic list
            diagnostics_items = diagnostics_result.items
        elif hasattr(diagnostics_result, "kind") and diagnostics_result.kind == "unchanged":
            # 如果是unchanged report，说明没有新的诊断 / If it's unchanged report, no new diagnostics
            diagnostics_items = []
        else:
            diagnostics_items = []

        # 验证包含"os" is not defined错误 / Verify contains "os" is not defined error
        has_os_error = any(
            '"os" is not defined' in str(getattr(diagnostic, "message", "")) for diagnostic in diagnostics_items
        )
        assert has_os_error, (
            f"诊断结果中未找到预期的错误信息 / Expected error not found in diagnostics. Got: {diagnostics_items}"
        )

        # 5. 测试读取文件内容 / Test reading file content
        file_content = workspace.read_file(uri=temp_file_uri, with_line_num=True)
        assert "os.path" in file_content, "文件内容读取异常 / File content reading error"

        # 6. 测试获取文件symbols / Test getting file symbols
        symbols = workspace.get_file_symbols(uri=temp_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
        print(f"Symbols output: {symbols}")
        # 验证symbols方法正常工作（至少返回了结果，即使可能为空）/ Verify symbols method works (returns result even if empty)
        assert "以上是文件的符号信息" in symbols or "Function: test" in symbols, (
            f"未能获取到文件symbols / Failed to get file symbols. Got: {symbols}"
        )

    finally:
        # 清理：关闭workspace并删除临时文件 / Cleanup: close workspace and delete temp file
        workspace.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def test_replace_in_file_basic(project_root_dir, py_workspace) -> None:
    """
    测试replace_in_file基本功能 / Test basic replace_in_file functionality

    验证replace_in_file能够正确替换文件中的文本并返回undo_edits和diagnostics
    Verify that replace_in_file correctly replaces text and returns undo_edits and diagnostics
    """
    test_file_path = project_root_dir + "/file_for_edit.py"
    test_file_uri = "file://" + test_file_path

    # 备份原始文件内容 / Backup original file content
    with open(test_file_path) as f:
        original_content = f.read()

    try:
        py_workspace.open_file(uri=test_file_uri)

        # 替换类名 A -> B / Replace class name A -> B
        undo_edits, diagnostics = py_workspace.replace_in_file(
            uri=test_file_uri,
            query="class A:",
            replacement="class B:",
            compute_undo_edits=True,
        )

        # 验证返回值结构 / Verify return value structure
        assert undo_edits is not None, "应该返回undo_edits / Should return undo_edits"
        # diagnostics可能为None（超时）或有值 / diagnostics may be None (timeout) or have value

        # 验证替换成功 / Verify replacement succeeded
        symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
        assert "Class: B" in symbols, "类名应该被替换为B / Class name should be replaced with B"
        assert "Class: A" not in symbols, "原类名A不应该存在 / Original class name A should not exist"

        # 使用undo_edits恢复 / Restore using undo_edits
        _, _ = py_workspace.apply_edit(
            uri=test_file_uri,
            edits=[e.to_single_edit_operation() for e in undo_edits],
            compute_undo_edits=False,
        )

        # 验证恢复成功 / Verify restoration succeeded
        symbols = py_workspace.get_file_symbols(uri=test_file_uri, kinds=DEFAULT_SYMBOL_VALUE_SET)
        assert "Class: A" in symbols, "类名应该被恢复为A / Class name should be restored to A"

    finally:
        # 恢复原始文件内容 / Restore original file content
        with open(test_file_path, "w") as f:
            f.write(original_content)


def test_replace_in_file_with_regex(project_root_dir, py_workspace) -> None:
    """
    测试replace_in_file使用正则表达式 / Test replace_in_file with regex

    验证replace_in_file能够使用正则表达式进行替换
    Verify that replace_in_file can use regex for replacement
    """
    test_file_path = project_root_dir + "/file_for_edit.py"
    test_file_uri = "file://" + test_file_path

    # 备份原始文件内容 / Backup original file content
    with open(test_file_path) as f:
        original_content = f.read()

    try:
        py_workspace.open_file(uri=test_file_uri)

        # 使用正则表达式替换类定义 / Replace class definition using regex
        undo_edits, diagnostics = py_workspace.replace_in_file(
            uri=test_file_uri,
            query=r"class\s+\w+:",
            replacement="class NewClass:",
            is_regex=True,
            compute_undo_edits=True,
        )

        # 验证返回值 / Verify return values
        assert undo_edits is not None, "应该返回undo_edits / Should return undo_edits"

        # 验证替换成功 / Verify replacement succeeded
        content = py_workspace.read_file(uri=test_file_uri)
        assert "class NewClass:" in content, "应该包含新类名 / Should contain new class name"
        py_workspace.close()  # 提前调用close触发dispose，否则会在fixture触发close导致文件被篡改

    finally:
        # 恢复原始文件内容 / Restore original file content
        with open(test_file_path, "w") as f:
            f.write(original_content)


def test_replace_in_file_with_range(project_root_dir, py_workspace) -> None:
    """
    测试replace_in_file在指定范围内替换 / Test replace_in_file with specific range

    验证replace_in_file能够在指定范围内进行替换
    Verify that replace_in_file can replace within a specific range
    """
    test_file_path = project_root_dir + "/file_for_edit.py"
    test_file_uri = "file://" + test_file_path

    # 备份原始文件内容 / Backup original file content
    with open(test_file_path) as f:
        original_content = f.read()

    try:
        py_workspace.open_file(uri=test_file_uri)

        # 只在第8-9行范围内替换 / Replace only within lines 8-9
        search_range = Range(
            start_position=Position(7, 1),  # 第8行开始 / Start at line 8
            end_position=Position(9, 1),  # 第9行结束 / End at line 9
        )

        undo_edits, diagnostics = py_workspace.replace_in_file(
            uri=test_file_uri,
            query="A",
            replacement="ReplacedA",
            match_case=True,
            search_scope=search_range,
            compute_undo_edits=True,
        )

        # 验证返回值 / Verify return values
        assert undo_edits is not None, "应该返回undo_edits / Should return undo_edits"

        # 验证替换成功 / Verify replacement succeeded
        content = py_workspace.read_file(uri=test_file_uri)
        assert "class ReplacedA:" in content, "类名应该被替换 / Class name should be replaced"

        py_workspace.close()

    finally:
        # 恢复原始文件内容 / Restore original file content
        with open(test_file_path, "w") as f:
            f.write(original_content)


def test_replace_in_file_no_match(project_root_dir, py_workspace) -> None:
    """
    测试replace_in_file没有匹配时的行为 / Test replace_in_file behavior when no match

    验证当没有找到匹配项时，replace_in_file返回(None, None)
    Verify that replace_in_file returns (None, None) when no match is found
    """
    test_file_path = project_root_dir + "/file_for_edit.py"
    test_file_uri = "file://" + test_file_path

    py_workspace.open_file(uri=test_file_uri)

    # 查询不存在的文本 / Query for non-existent text
    undo_edits, diagnostics = py_workspace.replace_in_file(
        uri=test_file_uri,
        query="NonExistentText",
        replacement="Replacement",
        compute_undo_edits=True,
    )

    # 验证返回(None, None) / Verify returns (None, None)
    assert undo_edits is None, "没有匹配时应该返回None / Should return None when no match"
    assert diagnostics is None, "没有匹配时应该返回None / Should return None when no match"


def test_replace_in_file_case_sensitive(project_root_dir, py_workspace) -> None:
    """
    测试replace_in_file区分大小写 / Test replace_in_file case sensitivity

    验证replace_in_file能够正确处理大小写敏感的替换
    Verify that replace_in_file correctly handles case-sensitive replacement
    """
    test_file_path = project_root_dir + "/file_for_edit.py"
    test_file_uri = "file://" + test_file_path

    # 备份原始文件内容 / Backup original file content
    with open(test_file_path) as f:
        original_content = f.read()

    try:
        py_workspace.open_file(uri=test_file_uri)

        # 区分大小写替换 / Case-sensitive replacement
        undo_edits, diagnostics = py_workspace.replace_in_file(
            uri=test_file_uri,
            query="class A:",
            replacement="class B:",
            match_case=True,
            compute_undo_edits=True,
        )

        # 验证返回值 / Verify return values
        assert undo_edits is not None, "应该找到匹配并返回undo_edits / Should find match and return undo_edits"

        # 尝试用小写查询（不应该匹配）/ Try lowercase query (should not match)
        undo_edits2, diagnostics2 = py_workspace.replace_in_file(
            uri=test_file_uri,
            query="class b:",
            replacement="class C:",
            match_case=True,
            compute_undo_edits=True,
        )

        # 验证没有匹配 / Verify no match
        assert undo_edits2 is None, "大小写不匹配时不应该找到结果 / Should not find match when case doesn't match"
        py_workspace.close()

    finally:
        # 恢复原始文件内容 / Restore original file content
        with open(test_file_path, "w") as f:
            f.write(original_content)


def test_replace_in_file_with_diagnostics(project_root_dir) -> None:
    """
    测试replace_in_file引入错误后返回诊断信息 / Test replace_in_file returns diagnostics after introducing errors

    验证replace_in_file在引入语法错误后能够返回诊断信息
    Verify that replace_in_file returns diagnostics after introducing syntax errors
    """
    import tempfile

    # 创建一个临时Python文件 / Create a temporary Python file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir=project_root_dir) as f:
        f.write(
            """# -*- coding: utf-8 -*-
# Test file
def valid_function():
    x = 1
    return x
""",
        )
        temp_file_path = f.name

    temp_file_uri = f"file://{temp_file_path}"
    workspace = PyWorkspace(
        root_dir=project_root_dir,
        project_name="test_replace_diagnostics",
        diagnostics_timeout=15.0,  # 增加超时时间以适应低配置电脑 / Increase timeout for low-spec computers
    )

    try:
        # 打开文件 / Open file
        workspace.open_file(uri=temp_file_uri)

        # 使用replace_in_file引入错误 / Introduce error using replace_in_file
        undo_edits, diagnostics = workspace.replace_in_file(
            uri=temp_file_uri,
            query="return x",
            replacement="return undefined_variable",
            compute_undo_edits=True,
        )

        # 验证返回了撤销编辑 / Verify undo edits are returned
        assert undo_edits is not None, "应该返回undo_edits / Should return undo_edits"

        # 验证返回了诊断信息 / Verify diagnostics are returned
        assert diagnostics is not None, "应该返回诊断信息 / Should return diagnostics"

        # 验证诊断信息包含错误 / Verify diagnostics contain error
        if hasattr(diagnostics, "items") and diagnostics.items:
            has_error = any(
                "undefined_variable" in str(getattr(diagnostic, "message", "")).lower()
                for diagnostic in diagnostics.items
            )
            assert has_error, "应该包含undefined_variable错误 / Should contain undefined_variable error"

    finally:
        workspace.close()
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def test_find_in_folder(project_root_dir: str, py_workspace: PyWorkspace) -> None:
    """
    测试在文件夹中搜索功能 / Test find in folder functionality
    """
    # 在整个项目文件夹中搜索 "def" / Search for "def" in the entire project folder
    folder_uri = f"file://{project_root_dir}"
    results = py_workspace.find_in_path(uri=folder_uri, query="def", match_case=True)

    # 验证返回了结果 / Verify results are returned
    assert len(results) > 0, "应该在文件夹中找到匹配项 / Should find matches in folder"

    # 验证结果包含匹配的文本 / Verify results contain matched text
    for result in results:
        assert result.match is not None, "结果应该包含匹配的文本 / Result should contain matched text"
        assert "def" in result.match, "匹配的文本应该包含 'def' / Matched text should contain 'def'"

    print(f"在文件夹中找到 {len(results)} 个匹配项 / Found {len(results)} matches in folder")


def test_find_in_folder_with_limit(project_root_dir: str, py_workspace: PyWorkspace) -> None:
    """
    测试在文件夹中搜索时使用结果限制 / Test find in folder with result limit
    """
    folder_uri = f"file://{project_root_dir}"

    # 限制返回5个结果 / Limit to 5 results
    results = py_workspace.find_in_path(uri=folder_uri, query="def", limit_result_count=5)

    # 验证结果数量不超过限制 / Verify result count doesn't exceed limit
    assert len(results) <= 5, "结果数量不应超过限制 / Result count should not exceed limit"

    print(f"限制为5个结果，实际返回 {len(results)} 个 / Limited to 5 results, actually returned {len(results)}")


def test_find_in_folder_with_regex(project_root_dir: str, py_workspace: PyWorkspace) -> None:
    """
    测试在文件夹中使用正则表达式搜索 / Test find in folder with regex
    """
    folder_uri = f"file://{project_root_dir}"

    # 使用正则表达式搜索函数定义 / Search for function definitions using regex
    results = py_workspace.find_in_path(uri=folder_uri, query=r"class\s+\w+", is_regex=True)

    # 验证返回了结果 / Verify results are returned
    assert len(results) > 0, "应该找到类定义 / Should find class definitions"

    print(f"使用正则表达式找到 {len(results)} 个类定义 / Found {len(results)} class definitions using regex")


def test_find_in_file_vs_folder(project_root_dir: str, py_workspace: PyWorkspace) -> None:
    """
    测试在单个文件和文件夹中搜索的区别 / Test difference between searching in file vs folder
    """
    # 在单个文件中搜索 / Search in a single file
    file_uri = f"file://{project_root_dir}/file_for_test_read.py"
    file_results = py_workspace.find_in_path(uri=file_uri, query="def")

    # 在整个文件夹中搜索 / Search in the entire folder
    folder_uri = f"file://{project_root_dir}"
    folder_results = py_workspace.find_in_path(uri=folder_uri, query="def")

    # 文件夹搜索结果应该包含文件搜索结果 / Folder search should include file search results
    assert len(folder_results) >= len(file_results), (
        "文件夹搜索结果应该 >= 文件搜索结果 / Folder results should be >= file results"
    )

    print(f"文件搜索: {len(file_results)} 个结果 / File search: {len(file_results)} results")
    print(f"文件夹搜索: {len(folder_results)} 个结果 / Folder search: {len(folder_results)} results")


def test_find_in_folder_with_search_scope_error(project_root_dir: str, py_workspace: PyWorkspace) -> None:
    """
    测试在文件夹搜索时使用 search_scope 参数应该报错 / Test that using search_scope with folder search raises error
    """
    folder_uri = f"file://{project_root_dir}"

    # 尝试在文件夹搜索时使用 search_scope，应该抛出 ValueError / Try to use search_scope with folder search, should raise ValueError
    with pytest.raises(ValueError, match="search_scope"):
        py_workspace.find_in_path(
            uri=folder_uri,
            query="def",
            search_scope=Range(
                start_position=Position(line=1, character=1), end_position=Position(line=10, character=1)
            ),
        )
