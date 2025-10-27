# filename: utils.py
# @Time    : 2024/5/8 17:24
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import os
from typing import Literal

from ai_ide.dtos.text_documents import LSPRange
from ai_ide.environment.workspace.schema import Range


def render_symbols(symbols: list[dict], render_symbol_kind: list[int], indent: int = 0) -> str:
    """
    递归渲染LSP符号列表为人类可读的文本格式，并返回形成的字符串。

    Args:
        symbols: 符号列表，每个符号是一个包含name, kind, 可选children的字典。
        render_symbol_kind: 需要渲染的符号种类列表。
        indent: 当前缩进级别，用于格式化输出。

    返回:
        str: 返回形成的符号结构字符串。
    """
    # 用于缩进的空格
    indent_space = " " * 2 * indent
    # 符号种类的字典映射
    symbol_kinds = {
        1: "File",
        2: "Module",
        3: "Namespace",
        4: "Package",
        5: "Class",
        6: "Method",
        7: "Property",
        8: "Field",
        9: "Constructor",
        10: "Enum",
        11: "Interface",
        12: "Function",
        13: "Variable",
        14: "Constant",
        15: "String",
        16: "Number",
        17: "Boolean",
        18: "Array",
        19: "Object",
        20: "Key",
        21: "Null",
        22: "EnumMember",
        23: "Struct",
        24: "Event",
        25: "Operator",
        26: "TypeParameter",
    }

    lines = []  # 用于收集所有的输出行
    for symbol in symbols:
        if symbol["kind"] not in render_symbol_kind:
            continue
        # 获取符号的种类名称，如果找不到则默认为'Unknown Symbol'
        kind_name = symbol_kinds.get(symbol["kind"], "Unknown Symbol")

        # 构造当前符号的描述
        line = f"{indent_space}{kind_name}: {symbol['name']}"
        if lsp_range_dict := symbol.get("location", {}).get("range"):
            lsp_range = LSPRange.model_validate(lsp_range_dict)
            tf_ide_range = Range.from_lsp_range(lsp_range)
            line += (
                f" Range({tf_ide_range.start_position.line}:{tf_ide_range.start_position.character}-"
                f"{tf_ide_range.end_position.line}:{tf_ide_range.end_position.character})"
            )
        lines.append(line)

        # 如果有子符号，递归调用以渲染它们，并将结果添加到lines中
        if "children" in symbol:
            child_output = render_symbols(symbol["children"], render_symbol_kind, indent + 1)
            lines.append(child_output)

    return "\n".join(lines)  # 将所有行合并为一个单独的字符串并返回


def list_directory_tree(
    path: str,
    include_dirs: list[str] | set[str] | Literal["all"] | None = None,
    recursive: bool = True,
    indent: str = "",
) -> str:
    """
    递归或非递归列出目录树结构，返回一个目录树的字符串。

    Args:
        path (str): 要遍历的根目录路径。
        include_dirs (Iterable[str] | 'all'): 允许展开的目录列表或 'all' 表示展开所有目录。
        recursive (bool): 是否递归展开目录。
        indent (str): 当前递归层的缩进，用于格式化输出。

    Returns:
        str: 格式化的目录树字符串。
    """
    output = []
    if include_dirs is None:
        include_dirs = []
    with os.scandir(path) as entries:
        for entry in entries:
            entry_path = os.path.join(path, entry.name)
            if entry.is_dir(follow_symlinks=False):
                output.append(f"{indent}{entry.name}/")
                if include_dirs == "all" or entry.name in include_dirs:
                    new_indent = "  " + indent  # 增加缩进
                    output.append(
                        list_directory_tree(
                            entry_path,
                            "all" if recursive else include_dirs,
                            recursive,
                            new_indent,
                        ),
                    )
            elif entry.is_file(follow_symlinks=False):
                output.append(f"{indent}{entry.name}")

    return "\n".join(output)


def is_subdirectory(sub_dir: str, root_dir: str) -> bool:
    """
    Determines if a directory is a subdirectory of another directory.

    Args:
        sub_dir: A string representing the subdirectory path.
        root_dir: A string representing the root directory path.

    Returns:
        A boolean value indicating whether the subdirectory is a subdirectory of the root directory.

    Note:
        This method ensures that both paths are absolute paths by using os.path.realpath.
        It checks if both directories exist using os.path.exists.
        It compares the common path between the subdirectory and root directory using os.path.commonpath.
        If the common path is equal to the root directory, it returns True, indicating that the subdirectory is a subdirectory of the
        root directory. Otherwise, it returns False.

    Example:
        is_subdirectory('/path/to/subdir', '/path/to')
        # returns True
    """
    # 确保两个路径都是绝对路径
    sub_dir = os.path.realpath(sub_dir)
    root_dir = os.path.realpath(root_dir)

    # 检查两个目录是否存在
    if not os.path.exists(sub_dir) or not os.path.exists(root_dir):
        return False

    # 检查sub_dir是否是root_dir的子目录
    # 这里使用os.path.commonpath来比较两个路径的公共部分是否为root_dir
    common_path = os.path.commonpath([sub_dir, root_dir])
    if common_path == root_dir:
        return True
    else:
        return False
