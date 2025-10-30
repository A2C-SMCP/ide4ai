# filename: test_utils.py
# @Time    : 2024/4/25 18:39
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import tempfile
from pathlib import Path, PurePath
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ide4ai.environment.workspace.schema import EndOfLineSequence
from ide4ai.environment.workspace.utils import (
    LARGE_FILE_HEAP_OPERATION_THRESHOLD,
    LARGE_FILE_LINE_COUNT_THRESHOLD,
    LARGE_FILE_SIZE_THRESHOLD,
    UTF_8_BOM,
    column_from_visible_width,
    contains_rtl,
    contains_unusual_line_terminators,
    count_eol,
    create_line_starts,
    detect_newline_type,
    first_non_whitespace_index,
    is_emoji_imprecise,
    is_full_width_character,
    is_high_surrogate,
    is_pure_basic_ascii,
    last_non_whitespace_index,
    next_indent_tab_stop,
    next_render_tab_stop,
    normalize_indentation,
    prev_indent_tab_stop,
    prev_render_tab_stop,
    read_file_with_bom_handling,
    visible_width_from_column,
)


def test_detect_newline_with_lf():
    # 模拟文件内容只有 \n 换行符
    mock_file_content = b"Hello\nWorld\nPython\n"
    with patch("builtins.open", mock_open(read_data=mock_file_content)) as mock_file:
        result = detect_newline_type(Path("/fake/path"))
        assert result == EndOfLineSequence.LF
        mock_file.assert_called_once_with(Path("/fake/path"), "rb")


def test_detect_newline_with_crlf():
    # 模拟文件内容只有 \r\n 换行符
    mock_file_content = b"Hello\r\nWorld\r\nPython\r\n"
    with patch("builtins.open", mock_open(read_data=mock_file_content)):
        result = detect_newline_type(Path("/fake/path"))
        assert result == EndOfLineSequence.CRLF


def test_no_newline_in_file():
    # 模拟文件没有换行符
    mock_file_content = b"Hello World Python"

    with patch("builtins.open", mock_open(read_data=mock_file_content)):
        with patch("os.name", "unknown"):
            with pytest.raises(ValueError) as excinfo:
                detect_newline_type(PurePath("/fake/path"))  # noqa
            assert "Unsupported operating system" in str(excinfo.value)

    # 额外测试：模拟不同的操作系统
    with patch("builtins.open", mock_open(read_data=mock_file_content)):
        with patch("os.name", "nt"):  # 模拟 Windows 系统
            assert detect_newline_type(PurePath("/fake/path")) == EndOfLineSequence.CRLF  # noqa

        with patch("os.name", "posix"):
            with patch("os.uname", return_value=type("obj", (object,), {"sysname": "Darwin"})):  # 模拟 macOS 系统
                assert detect_newline_type(PurePath("/fake/path")) == EndOfLineSequence.LF  # noqa

            with patch("os.uname", return_value=type("obj", (object,), {"sysname": "Linux"})):  # 模拟 Linux 系统
                assert detect_newline_type(PurePath("/fake/path")) == EndOfLineSequence.LF  # noqa


def test_detect_newline_with_mixed_newlines():
    # 模拟文件内容包含多种换行符，\r\n 在 \n 之前
    mock_file_content = b"Hello\r\nWorld\nPython\n"
    with patch("builtins.open", mock_open(read_data=mock_file_content)):
        result = detect_newline_type(Path("/fake/path"))
        assert result == EndOfLineSequence.CRLF


def test_detect_newline_raises_ioerror():
    # 模拟打开文件时的 IOError
    with patch("builtins.open", side_effect=OSError("Failed to open")):
        with pytest.raises(ValueError) as excinfo:
            detect_newline_type(Path("/fake/path"))
        assert "Error reading file" in str(excinfo.value)


def test_exceeds_file_size_limit():
    # 模拟文件大小超过限制
    with patch("os.path.getsize", return_value=LARGE_FILE_SIZE_THRESHOLD + 1):
        with pytest.raises(ValueError) as excinfo:
            read_file_with_bom_handling("/fake/path")
        assert "File size exceeds the maximum limit of 100KB" in str(excinfo.value)


def test_exceeds_line_count_limit():
    # 模拟文件行数超过限制
    lines = ["hello\n"] * (LARGE_FILE_LINE_COUNT_THRESHOLD + 1)
    mock_file_content = "".join(lines)
    with patch("os.path.getsize", return_value=LARGE_FILE_SIZE_THRESHOLD - 1):
        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            with pytest.raises(ValueError) as excinfo:
                read_file_with_bom_handling("/fake/path")
            assert "File has more lines than the maximum allowed 300 lines" in str(excinfo.value)


def test_exceeds_character_threshold():
    # 模拟文件字符总数超过内存使用阈值
    single_line = "hello" * (LARGE_FILE_HEAP_OPERATION_THRESHOLD // 10) + "\n"
    num_lines = 10
    lines = [single_line] * num_lines
    mock_file_content = "".join(lines)
    with patch("os.path.getsize", return_value=LARGE_FILE_SIZE_THRESHOLD - 1):
        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            with pytest.raises(ValueError) as excinfo:
                read_file_with_bom_handling("/fake/path")
            assert "File content exceeds the memory usage threshold of 256K characters" in str(excinfo.value)


def test_file_with_bom():
    # 模拟文件含有 BOM
    mock_file_content = f"{UTF_8_BOM}hello\nworld\n"
    with patch("os.path.getsize", return_value=100):
        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            bom, content = read_file_with_bom_handling("/fake/path")
            assert bom == UTF_8_BOM
            assert content[0] == "hello"


def test_file_without_bom():
    # 模拟文件不含 BOM
    mock_file_content = "hello\nworld\n"
    with patch("os.path.getsize", return_value=100):
        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            bom, content = read_file_with_bom_handling("/fake/path")
            assert bom == ""
            assert content[0] == "hello"


def test_non_utf8_encoded_file_raises():
    # 模拟文件编码错误
    with patch("os.path.getsize", return_value=100):
        with patch("builtins.open") as mocked_open:
            # 设置mock对象来模拟文件打开，并制定读取数据时触发的异常
            mocked_file = MagicMock()
            mocked_file.read.side_effect = UnicodeDecodeError("utf-8", b"\xff\xfe\xfa", 0, 1, "invalid start byte")
            # 使得调用open后的返回对象支持上下文管理（with...as...）
            mocked_open.return_value.__enter__.return_value = mocked_file
            with pytest.raises(ValueError) as excinfo:
                read_file_with_bom_handling("/fake/path")
            assert "Only UTF-8 encoded files are supported now" in str(excinfo.value)


def test_is_high_surrogate_with_high_surrogate():
    # 测试一个高代理字符
    char = "\ud800"  # 高代理字符的起始码点
    assert is_high_surrogate(char) is True


def test_is_high_surrogate_with_not_high_surrogate():
    # 测试一个普通字符，不是代理
    char = "A"
    assert is_high_surrogate(char) is False


def test_is_high_surrogate_with_low_surrogate():
    # 测试一个低代理字符
    char = "\udc00"  # 低代理字符的起始码点
    assert is_high_surrogate(char) is False


def test_is_high_surrogate_with_multiple_characters():
    # 测试包含多个字符的字符串，应该抛出异常
    chars = "AB"
    with pytest.raises(TypeError):
        is_high_surrogate(chars)


def test_is_high_surrogate_with_empty_input():
    # 测试空字符串，应该抛出异常
    char = ""
    with pytest.raises(TypeError):
        is_high_surrogate(char)


def test_next_render_tab_stop():
    assert next_render_tab_stop(0, 4) == 4
    assert next_render_tab_stop(3, 4) == 4
    assert next_render_tab_stop(5, 4) == 8
    assert next_render_tab_stop(8, 4) == 12


def test_next_indent_tab_stop():
    assert next_indent_tab_stop(0, 3) == 3
    assert next_indent_tab_stop(2, 3) == 3
    assert next_indent_tab_stop(3, 3) == 6
    assert next_indent_tab_stop(4, 3) == 6


def test_prev_render_tab_stop():
    assert prev_render_tab_stop(0, 4) == 0
    assert prev_render_tab_stop(3, 4) == 0
    assert prev_render_tab_stop(5, 4) == 4
    assert prev_render_tab_stop(8, 4) == 4


def test_prev_indent_tab_stop():
    assert prev_indent_tab_stop(0, 3) == 0
    assert prev_indent_tab_stop(2, 3) == 0
    assert prev_indent_tab_stop(3, 3) == 0
    assert prev_indent_tab_stop(4, 3) == 3


def test_is_full_width_character():
    # 全角字符
    assert is_full_width_character(ord("中")) is True
    # 半角字符
    assert is_full_width_character(ord("a")) is False
    # 特殊全角符号
    assert is_full_width_character(ord("ｆ")) is True


def test_is_emoji_imprecise():
    # 明确的表情符号
    assert is_emoji_imprecise(0x1F600) is True  # 😀
    # 非表情符号
    assert is_emoji_imprecise(ord("a")) is False


@pytest.mark.parametrize(
    "line_content, column, tab_size, expected",
    [
        ("hello", 6, 4, 5),  # Simple case with normal characters
        ("hello\tworld", 7, 4, 8),  # Tab handling
        ("你好", 3, 4, 4),  # Full-width characters
        ("🙂🙂", 3, 4, 4),  # Emoji handling
        ("hello\t世界", 8, 4, 10),  # Combination of characters and tab
    ],
)
def test_visible_width_from_column(line_content, column, tab_size, expected):
    assert visible_width_from_column(line_content, column, tab_size) == expected


# Assuming _next_visible_column, next_render_tab_stop, is_full_width_character, and is_emoji_imprecise are defined
@pytest.mark.parametrize(
    "line_content, visible_column, tab_size, expected_column",
    [
        ("hello world", 7, 4, 8),  # Testing within simple text
        ("hello\tworld", 10, 4, 9),  # Testing with a tab
        ("你好世界", 3, 4, 2),  # Testing with full-width characters
        ("hello\tworld", 9, 4, 8),  # Testing tab that extends visually
        ("a\tbc", 5, 4, 4),  # Testing a tab with characters before and after
        ("hello\t你好", 9, 4, 7),  # Mixed characters with tabs and full-width
        ("hello", 0, 4, 1),  # Testing at the start of the line
        (
            "hello",
            100,
            4,
            6,
        ),  # Extremely large visible column request with a small string
    ],
)
def test_column_from_visible_width(line_content, visible_column, tab_size, expected_column):
    assert column_from_visible_width(line_content, visible_column, tab_size) == expected_column


@pytest.mark.parametrize(
    "input_string, indent_size, insert_spaces, expected_output",
    [
        ("    hello", 4, True, "    hello"),  # Already normalized with spaces
        ("\thello", 4, True, "    hello"),  # Convert tabs to spaces
        ("    hello", 4, False, "\thello"),  # Convert spaces to tabs
        ("\t\thello", 2, True, "    hello"),  # Convert larger tab stops to spaces
        ("  \t  hello", 4, False, "\t  hello"),  # Mixed spaces and tabs to tabs
        ("hello", 4, True, "hello"),  # No leading whitespace
        (
            "\t\t  hello",
            4,
            False,
            "\t\t  hello",
        ),  # Mixed, with tabs staying and spaces converting
    ],
)
def test_normalize_indentation(input_string, indent_size, insert_spaces, expected_output):
    assert normalize_indentation(input_string, indent_size, insert_spaces) == expected_output


@pytest.mark.parametrize(
    "input_string, expected_index",
    [
        (" hello", 1),  # Leading space
        ("\thello", 1),  # Leading tab
        ("\nhello", 1),  # Leading newline
        ("hello", 0),  # No leading whitespace
        ("    ", -1),  # Only spaces
        ("\t\t\t", -1),  # Only tabs
        ("", -1),  # Empty string
        (" \t\nhello", 3),  # Multiple types of leading whitespace
        ("hello world", 0),  # No leading whitespace with space inside
        ("  \n  hello", 5),  # Spaces and newline before text
    ],
)
def test_first_non_whitespace_index(input_string, expected_index):
    assert first_non_whitespace_index(input_string) == expected_index


@pytest.mark.parametrize(
    "input_string, start_index, expected_index",
    [
        ("hello ", None, 4),  # Trailing space
        ("hello\t", None, 4),  # Trailing tab
        ("hello\n", None, 4),  # Trailing newline
        (" hello", None, 5),  # No trailing whitespace
        ("", None, -1),  # Empty string
        ("     ", None, -1),  # Only spaces
        ("hello", 3, 3),  # Specific start index within string
        ("hello world", 5, 4),  # Start index at space
        ("  hello  ", 5, 5),  # Space after word with exact start index
        ("hello", 10, 4),  # Start index out of range
        ("hello world", -1, -1),  # Invalid negative start index
    ],
)
def test_last_non_whitespace_index(input_string, start_index, expected_index):
    if start_index is None:
        assert last_non_whitespace_index(input_string) == expected_index
    else:
        assert last_non_whitespace_index(input_string, start_index) == expected_index


# Assuming the functions contains_rtl and contains_unusual_line_terminators are already defined and imported


@pytest.mark.parametrize(
    "input_string, expected",
    [
        ("hello", False),  # No RTL
        ("مرحبا", True),  # Arabic
        ("שלום", True),  # Hebrew
        ("hello مرحبا", True),  # Mixed with RTL
        ("12345", False),  # Numbers
    ],
)
def test_contains_rtl(input_string, expected):
    assert contains_rtl(input_string) == expected


@pytest.mark.parametrize(
    "input_string, expected",
    [
        ("hello", False),  # Normal string
        ("Line\u2028Separator", True),  # Line separator
        ("Paragraph\u2029Separator", True),  # Paragraph separator
        ("Text without\u2028special characters", True),  # Text with line separator
        ("Just a normal string.", False),  # No special characters
    ],
)
def test_contains_unusual_line_terminators(input_string, expected):
    assert contains_unusual_line_terminators(input_string) == expected


@pytest.mark.parametrize(
    "input_string, expected_results",
    [
        ("Hello\nWorld", ([0, 6], 0, 1, 0, True)),  # Single LF
        ("Hello\rWorld", ([0, 6], 1, 0, 0, True)),  # Single CR
        ("Hello\r\nWorld", ([0, 7], 0, 0, 1, True)),  # Single CRLF
        ("Hello World", ([0], 0, 0, 0, True)),  # No line breaks
        (
            "Line1\nLine2\rLine3\r\nLine4",
            ([0, 6, 12, 19], 1, 1, 1, True),
        ),  # Mixed line breaks
        (
            "ASCII and some non-ASCII \u2603 characters",
            ([0], 0, 0, 0, False),
        ),  # Contains non-ASCII
        ("Just a normal ASCII string", ([0], 0, 0, 0, True)),  # Only ASCII
    ],
)
def test_create_line_starts(input_string, expected_results):
    result_list = []
    results = create_line_starts(result_list, input_string)
    assert results == expected_results
    assert result_list == expected_results[0]


@pytest.mark.parametrize(
    "input_lines, expected",
    [
        (["Hello, world!"], True),  # Basic ASCII
        (["Hello, world!", "Goodbye, world!"], True),  # Multiple ASCII lines
        (["This is a test.", "Line\twith\ttabs."], True),  # Lines with tabs
        (["This line is fine.", "This one is not: 😊"], False),  # Line with emoji
        (["Another bad one: ü"], False),  # Line with umlaut
        (["\t"], True),  # Only a tab
        ([""], True),  # Empty string
        ([], True),  # Empty list
        (["1234567890"], True),  # Numbers
        (["Special chars !@#$%^&*()"], True),  # Special characters
        (
            ["Valid line", "Another valid line", "Invalid because of this: á"],
            False,
        ),  # Mixed valid and invalid
    ],
)
def test_is_pure_basic_ascii(input_lines, expected):
    assert is_pure_basic_ascii(input_lines) == expected


@pytest.mark.parametrize(
    "input_text, expected_results",
    [
        ("Hello\nWorld", (1, 5, 5, 1)),  # Simple LF
        ("Hello\r\nWorld", (1, 5, 5, 2)),  # Simple CRLF
        ("Hello\rWorld", (1, 5, 5, 3)),  # CR, which is treated as invalid
        ("Hello World", (0, 11, 11, 0)),  # No EOL characters
        ("\n", (1, 0, 0, 1)),  # Single LF
        ("\r\n", (1, 0, 0, 2)),  # Single CRLF
        ("Line1\rLine2\nLine3\r\n", (3, 5, 0, 3)),  # Mixed EOL characters
        ("", (0, 0, 0, 0)),  # Empty string
        ("\r", (1, 0, 0, 3)),  # Single CR, invalid
        ("First line\nSecond line\nThird line", (2, 10, 10, 1)),  # Multiple LF
        ("First line\r\nSecond line\r\nThird line", (2, 10, 10, 2)),  # Multiple CRLF
        ("\n\n\n", (3, 0, 0, 1)),  # Multiple LF only
    ],
)
def test_count_eol(input_text, expected_results):
    assert count_eol(input_text) == expected_results


# Test with LF newlines
def test_detect_newline_type_lf():
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b"Hello\nWorld\n")
        tmp_path = Path(tmp.name)
        tmp.flush()
        assert detect_newline_type(tmp_path) == EndOfLineSequence.LF


# Test with CRLF newlines
def test_detect_newline_type_crlf():
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b"Hello\r\nWorld\r\n")
        tmp_path = Path(tmp.name)
        tmp.flush()
        assert detect_newline_type(tmp_path) == EndOfLineSequence.CRLF


# Test with no newlines
def test_detect_newline_type_no_newline():
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b"HelloWorld")
        tmp_path = Path(tmp.name)
        tmp.flush()
        res = detect_newline_type(tmp_path)
        assert res in [EndOfLineSequence.LF, EndOfLineSequence.CRLF]


# Test file access errors
def test_detect_newline_type_access_error():
    # Use a path that is unlikely to be permissible or exist
    with pytest.raises(ValueError) as excinfo:
        detect_newline_type(Path("/unaccessible/path/to/nonexistent/file.txt"))
    assert "Error reading file" in str(excinfo.value)


def test_detect_newline_type_with_crlf_char():
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write("Hello,一般来讲，Windows的文件系统使用'\\r\\n'来换行\nWorld\n".encode())
        tmp_path = Path(tmp.name)
        tmp.flush()
        assert detect_newline_type(tmp_path) == EndOfLineSequence.LF
