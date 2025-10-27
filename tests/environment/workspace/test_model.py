# filename: test_model.py
# @Time    : 2024/4/26 13:21
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from tempfile import NamedTemporaryFile
from unittest.mock import mock_open, patch

import pytest
from pydantic import AnyUrl

from ide4ai.environment.workspace.model import TextModel
from ide4ai.environment.workspace.schema import (
    EndOfLinePreference,
    Position,
    Range,
    SingleEditOperation,
)
from ide4ai.environment.workspace.utils import (
    LARGE_FILE_HEAP_OPERATION_THRESHOLD,
)
from ide4ai.schema import LanguageId


@pytest.fixture
def python_text_model():
    # Create a temporary file for the test
    with NamedTemporaryFile(mode="w+", suffix=".py", delete=True) as temp_file:
        # Write some initial Python code to the file
        temp_file.write("\ufeff# Sample Python File\nprint('Hello, world!')\n")
        temp_file.flush()  # Ensure it's written to disk

        # Create a TextModel instance
        language_id = LanguageId.python  # Assuming you have a predefined LanguageId enum
        uri = AnyUrl(f"file://{temp_file.name}")  # Using file URI for real file handling
        model = TextModel(language_id=language_id, uri=uri)

        # Yield the model to the test
        yield model

        # Cleanup: Close and remove the temporary file
        temp_file.close()  # Make sure file is closed before removal


# Test `set_value` method
@pytest.mark.parametrize(
    "input_value, expected_exception",
    [
        ("short text", None),  # Normal operation
        (
            "a" * (LARGE_FILE_HEAP_OPERATION_THRESHOLD + 1),
            ValueError,
        ),  # Exceeding memory threshold
    ],
)
def test_set_value(python_text_model, input_value, expected_exception):
    if expected_exception:
        with pytest.raises(expected_exception):
            python_text_model.set_value(input_value)
    else:
        python_text_model.set_value(input_value)
        assert "".join(python_text_model._content) == input_value


# Test `save` method
def test_save_method(python_text_model):
    m = mock_open()
    with patch("builtins.open", m, create=True):
        python_text_model.set_value("test save content")
        python_text_model.save()
    m.assert_called_once_with(python_text_model.uri.path, "w", encoding="utf-8")
    handle = m()
    handle.write.assert_called_once_with("test save content")


def test_save_with_tmpfile(python_text_model):
    """
    注意真实写入后最后一个 \n 换行符是过滤掉了的。因为经过了一次 readlines与 eol.join过程

    Args:
        python_text_model:

    Returns:

    """
    python_text_model.set_value("\ufeff# Complex Python File\nprint('Hello, world! I'am JQQ')\n")
    python_text_model.save()
    with open(python_text_model.uri.path, encoding="utf-8") as f:
        assert f.read() == "\ufeff# Complex Python File\nprint('Hello, world! I'am JQQ')"


# Test `get_value` method
@pytest.mark.parametrize(
    "eol, preserve_bom, expected_output",
    [
        (None, False, "test content"),  # Default EOL, no BOM
        (EndOfLinePreference.LF, True, "\ufefftest content"),  # Preserve BOM
    ],
)
def test_get_value(python_text_model, eol, preserve_bom, expected_output):
    assert python_text_model._TextModel__bom == "\ufeff"  # type: ignore
    python_text_model.set_value("test content")
    result = python_text_model.get_value(eol=eol, preserve_bom=preserve_bom)
    assert result == expected_output


# Test get_value_length
@pytest.mark.parametrize(
    "eol, preserve_bom, expected_length",
    [
        (
            None,
            False,
            43,
        ),  # No EOL change, no BOM (assuming LF by default and BOM not counted)
        (EndOfLinePreference.LF, False, 43),  # Explicitly setting LF, no BOM
        (
            EndOfLinePreference.CRLF,
            False,
            44,
        ),  # CRLF adds an extra character per line (2 lines total)
        (None, True, 44),  # No EOL change, with BOM (BOM adds length of 1)
        (EndOfLinePreference.CRLF, True, 45),  # CRLF and BOM
    ],
)
def test_get_value_length(python_text_model, eol, preserve_bom, expected_length):
    assert python_text_model.get_value_length(eol=eol, preserve_bom=preserve_bom) == expected_length


# Test get_value_in_range with various range inputs
@pytest.mark.parametrize(
    "start_pos, end_pos, expected_output",
    [
        ((1, 1), (1, 20), "# Sample Python Fil"),  # Single line extraction
        (
            (1, 1),
            (2, 17),
            "# Sample Python File\nprint('Hello, wo",
        ),  # Multi-line extraction
        ((2, 1), (2, 17), "print('Hello, wo"),  # Single line partial extraction
        ((1, 10), (1, 15), "Pytho"),  # Substring of a line
        ((2, 8), (2, 14), "Hello,"),  # Another substring of a line
        ((1, 1), (1, 1), ""),  # Empty range, should return an empty string
    ],
)
def test_get_value_in_range(python_text_model, start_pos, end_pos, expected_output):
    # Initialize the range
    t_range = Range(
        start_position=Position(line=start_pos[0], character=start_pos[1]),
        end_position=Position(line=end_pos[0], character=end_pos[1]),
    )

    # Fetch the text using the range
    result_text = python_text_model.get_value_in_range(t_range, EndOfLinePreference.TEXT_DEFINED)

    # Check if the output matches the expected text
    assert result_text == expected_output


def test_get_full_model_range(python_text_model):
    expected_start_position = Position(line=1, character=1)
    # Assuming get_line_count() and get_line_max_column() are correctly implemented and used
    with open(python_text_model.uri.path, encoding="utf-8", newline="") as f:
        content = f.read().splitlines()
    expected_line_count = len(content)
    expected_last_line_max_column = len(content[-1]) + 1

    expected_range = Range(
        start_position=expected_start_position,
        end_position=Position(line=expected_line_count, character=expected_last_line_max_column),
    )

    model_range = python_text_model.get_full_model_range()
    assert python_text_model.get_line_count() == expected_line_count

    assert model_range.start_position == expected_range.start_position, "Start position does not match expected"
    assert model_range.end_position == expected_range.end_position, "End position does not match expected"


def test_get_value_in_full_range(python_text_model):
    full_range = python_text_model.get_full_model_range()
    full_content = python_text_model.get_value_in_range(full_range)
    assert full_content == python_text_model.get_value()


# Test validate_range for valid input
@pytest.mark.parametrize(
    "start_line, start_char, end_line, end_char",
    [
        (1, 1, 1, 20),  # Within single line
        (1, 1, 2, 18),  # Spanning multiple lines
        (2, 1, 2, 18),  # Entire second line
    ],
)
def test_validate_range_valid(python_text_model, start_line, start_char, end_line, end_char):
    start_position = Position(line=start_line, character=start_char)
    end_position = Position(line=end_line, character=end_char)
    t_range = Range(start_position=start_position, end_position=end_position)
    validated_range = python_text_model.validate_range(t_range)
    assert validated_range.start_position == start_position
    assert validated_range.end_position == end_position


# Test validate_range for invalid input
@pytest.mark.parametrize(
    "start_line, start_char, end_line, end_char",
    [
        (1, 1, 1, 20),  # Start before the start of the document
        (1, 1, 3, 1),  # End beyond the end of the document
        (2, 19, 2, 20),  # Beyond the end of the second line
    ],
)
def test_validate_range_invalid(python_text_model, start_line, start_char, end_line, end_char):
    start_position = Position(line=start_line, character=start_char)
    end_position = Position(line=end_line, character=end_char)
    t_range = Range(start_position=start_position, end_position=end_position)
    # Assuming validate_range corrects the range or raises an error if it can't
    try:
        validated_range = python_text_model.validate_range(t_range)
        # Check if range was adjusted if no error raised
        assert validated_range.start_position.line >= 1
        assert validated_range.end_position.line <= 2  # Assuming file has 2 lines only
        assert (
            validated_range.end_position.character
            <= len(python_text_model._content[validated_range.end_position.line - 1]) + 1
        )
    except ValueError as e:
        assert "range is out of bounds" in str(e)


# Define tests for get_position_at
@pytest.mark.parametrize(
    "offset, expected_position",
    [
        (0, Position(1, 1)),  # Start of file
        (1, Position(1, 2)),  # Second character
        (
            25,
            Position(2, 5),
        ),  # End of the first line, assuming the first line is 25 characters long
        (26, Position(2, 6)),  # Start of the second line
        (
            50,
            Position(2, 23),
        ),  # Middle of the second line, assuming it's at least 25 characters long
        (
            100,
            Position(2, 23),
        ),  # Beyond the end of the file, assuming the file has less than 100 characters
    ],
)
def test_get_position_at(python_text_model, offset, expected_position):
    result_position = python_text_model.get_position_at(offset)
    assert result_position == expected_position, f"Expected {expected_position}, got {result_position}"


# Additionally, test invalid input handling
@pytest.mark.parametrize(
    "offset",
    [
        (-1),  # Negative offset
        (-100),  # Negative as offset
    ],
)
def test_get_position_at_invalid_input(python_text_model, offset):
    pos = python_text_model.get_position_at(offset)
    assert pos == Position(1, 1), "Expected position 1:1 for negative offset"


# Assuming Position takes line and character as arguments
# Assuming validate_position throws an exception or corrects the position if it's invalid


@pytest.mark.parametrize(
    "input_position, expected_position, is_valid",
    [
        ((1, 1), (1, 1), True),  # Valid position at the start of the file
        ((2, 1), (2, 1), True),  # Valid position at the start of the second line
        ((100, 1), (2, 23), False),  # Invalid line (beyond total lines)
        ((1, 50), (1, 21), False),  # Invalid character position (beyond line length)
        ((-1, 5), (1, 5), False),  # Negative line number
        ((1, -10), (1, 1), False),  # Negative character position
        ((2, 999), (2, 23), False),  # Character way beyond actual length of second line
    ],
)
def test_validate_position(python_text_model, input_position, expected_position, is_valid):
    position = Position(line=input_position[0], character=input_position[1])
    if is_valid:
        # If position is valid, we expect the method to return it unchanged
        validated_position = python_text_model.validate_position(position)
        assert validated_position.line == expected_position[0]
        assert validated_position.character == expected_position[1]
    else:
        # If position is invalid, we might expect a correction or exception, depending on implementation
        try:
            validated_position = python_text_model.validate_position(position)
            # If no exception, check if it corrects the position
            assert validated_position.line == expected_position[0]
            assert validated_position.character == expected_position[1]
        except ValueError:
            # If an exception is expected for invalid inputs
            pytest.raises(ValueError, python_text_model.validate_position, position)


# Test cases for get_line_min_column
@pytest.mark.parametrize(
    "line_number, expected_result, expected_exception",
    [
        (1, 1, None),  # Access the first line, expecting column 1
        (2, 1, None),  # Access the second line, expecting column 1
        (0, None, ValueError),  # Access an invalid line number (less than 1)
        (3, None, ValueError),  # Access a line number greater than the number of lines
        (-1, None, ValueError),  # Negative line number
    ],
)
def test_get_line_min_column(python_text_model, line_number, expected_result, expected_exception):
    if expected_exception:
        with pytest.raises(expected_exception):
            python_text_model.get_line_min_column(line_number)
    else:
        assert python_text_model.get_line_min_column(line_number) == expected_result


# Test get_line_max_column with different scenarios
@pytest.mark.parametrize(
    "line_number, expected_max_column, exception_expected",
    [
        (1, 21, False),  # "# Sample Python File" + 1 for newline
        (2, 23, False),  # "print('Hello, world!')" + 1 for newline
        (
            3,
            1,
            True,
        ),  # Non-existent line, should return 1 (assuming it behaves as empty)
        (0, None, True),  # Invalid line number, should raise ValueError
        (-1, None, True),  # Invalid line number, should raise ValueError
        (100, None, True),  # Far out of range, should raise ValueError
    ],
)
def test_get_line_max_column(python_text_model, line_number, expected_max_column, exception_expected):
    if exception_expected:
        with pytest.raises(ValueError):
            python_text_model.get_line_max_column(line_number)
    else:
        assert python_text_model.get_line_max_column(line_number) == expected_max_column


# Test get_line_first_non_whitespace_column
@pytest.mark.parametrize(
    "content, line_num, expected",
    [
        ("\n   def main():\n", 2, 4),  # Line with spaces before text
        ("\n\tdef main():\n", 2, 2),  # Line with a tab before text
        ("\n   \t def main():\n", 2, 6),  # Line with mixed whitespace
        ("\n\n", 2, 0),  # Empty line
        ("def main():\n", 1, 1),  # No leading whitespace
        ("  # Comment\n\n\tprint('Hello')\n", 3, 2),  # Third line with a tab
    ],
)
def test_get_line_first_non_whitespace_column(python_text_model, content, line_num, expected):
    # Assuming TextModel can be directly modified or reset
    python_text_model.set_value(content)
    result = python_text_model.get_line_first_non_whitespace_column(line_num)
    assert result == expected


# Test invalid line numbers
@pytest.mark.parametrize("line_num", [0, 100])  # Assuming 100 is more than the number of lines in any test content
def test_invalid_line_number(python_text_model, line_num):
    python_text_model._content = ["def main():\n", "print('Hello, world!')\n"]
    with pytest.raises(ValueError) as exc_info:
        python_text_model.get_line_first_non_whitespace_column(line_num)
    assert "Invalid line number" in str(exc_info.value)


# Test various scenarios for get_line_last_non_whitespace_column
@pytest.mark.parametrize(
    "line_num, expected_column, expected_error",
    [
        (1, 21, False),  # '# Sample Python File'
        (
            2,
            23,
            False,
        ),  # 'print('Hello, world!')    ' (trailing spaces should be ignored)
        (3, 0, True),  # only two lines in the file
        (4, 26, True),  # only two lines in the file
    ],
)
def test_get_line_last_non_whitespace_column(python_text_model, line_num, expected_column, expected_error):
    if expected_error:
        with pytest.raises(ValueError):
            python_text_model.get_line_last_non_whitespace_column(line_num)
    else:
        assert python_text_model.get_line_last_non_whitespace_column(line_num) == expected_column


# Test invalid line numbers
@pytest.mark.parametrize("line_num", [0, 5])  # Below valid range  # Above valid range
def test_get_line_last_non_whitespace_column_invalid(python_text_model, line_num):
    with pytest.raises(ValueError):
        python_text_model.get_line_last_non_whitespace_column(line_num)


# Test the modify_position method
@pytest.mark.parametrize(
    "initial_line, initial_char, offset, expected_line, expected_char",
    [
        # Normal movement
        (1, 1, 5, 1, 6),
        # Move beyond the start of the file
        (1, 1, -1, 1, 1),
        # Move beyond the end of the file
        (2, 23, 1, 2, 23),
        # Move within bounds
        (2, 1, 5, 2, 6),
        # Attempt to split a surrogate pair or line terminator
        (2, 13, 2, 2, 15),
    ],
)
def test_modify_position(python_text_model, initial_line, initial_char, offset, expected_line, expected_char):
    initial_position = Position(line=initial_line, character=initial_char)
    new_position = python_text_model.modify_position(initial_position, offset)
    assert new_position.line == expected_line and new_position.character == expected_char


@pytest.mark.parametrize(
    "start_pos, end_pos, expected_content",
    [
        # Single line, partial delete
        (
            (1, 1),
            (1, 5),
            [" 1 content", "Line 2 content", "Line 3 content", "Line 4 content"],
        ),
        # Single line, full delete
        ((1, 1), (1, 13), ["nt", "Line 2 content", "Line 3 content", "Line 4 content"]),
        # Multiple lines, partial start and end
        ((1, 1), (3, 5), [" 3 content", "Line 4 content"]),
        # Delete across all lines partially
        ((1, 1), (4, 9), ["ontent"]),
        # Edge case: Delete entire content
        ((1, 1), (4, 13), ["nt"]),
    ],
)
def test_delete_method(python_text_model, start_pos, end_pos, expected_content):
    content = [
        "Line 1 content",
        "Line 2 content",
        "Line 3 content",
        "Line 4 content",
    ]
    python_text_model.set_value("\n".join(content))
    start_line, start_char = start_pos
    end_line, end_char = end_pos
    range_to_delete = Range(
        start_position=Position(line=start_line, character=start_char),
        end_position=Position(line=end_line, character=end_char),
    )
    python_text_model._delete(range_to_delete)
    assert python_text_model._content == expected_content


# Test various insertion scenarios for the `_insert` method
@pytest.mark.parametrize(
    "initial_content, insert_text, position, expected_content",
    [
        # Simple insertion in the middle of a line
        (["hello world"], " test", Position(line=1, character=6), ["hello test world"]),
        # Insertion at the beginning of the file
        (
            ["hello world"],
            "start ",
            Position(line=1, character=1),
            ["start hello world"],
        ),
        # Insertion at the end of the file
        (["hello world"], " end", Position(line=1, character=12), ["hello world end"]),
        # Multiline insertion
        (
            ["hello", "world"],
            " new\nlines\n",
            Position(line=1, character=6),
            ["hello new", "lines", "world"],
        ),
        # Insertion at the beginning with a newline
        (
            ["hello", "world"],
            "new line\n",
            Position(line=1, character=1),
            ["new line", "hello", "world"],
        ),
        # Insertion at an empty line
        (
            ["hello", "", "world"],
            "middle\nline\n",
            Position(line=2, character=1),
            ["hello", "middle", "line", "world"],
        ),
        # Insertion at the end of a non-empty line
        (["hello"], " world", Position(line=1, character=6), ["hello world"]),
        # Insertion in an empty document
        ([], "new content", Position(line=1, character=1), ["new content"]),
        # Boundary test: Insertion beyond the current content
        (
            ["hello"],
            " world",
            Position(line=1, character=10),
            ["hello world"],
        ),  # Assuming spaces fill the gap
    ],
)
def test_insert(python_text_model, initial_content, insert_text, position, expected_content):
    python_text_model.set_value("\n".join(initial_content))
    valid_pos = python_text_model.validate_position(position)
    if valid_pos == position:
        python_text_model._insert(position, insert_text)
        assert python_text_model._content == expected_content
    else:
        python_text_model._insert(position, insert_text)
        assert python_text_model._content == expected_content


# Test get_view method for various cursor positions
@pytest.mark.parametrize(
    "cursor_position, cursor_key, expected_output",
    [
        # Cursor at the beginning of the file
        ((1, 2), "start_test", ">start_test|1:2<"),
        # Cursor at the end of a line
        ((1, 21), "end_line", ">end_line|1:21<"),
        # Cursor in an empty file
        ((1, 2), "empty", ">empty|1:2<"),
        # Multiple cursors
        (
            [(1, 2), "first", (2, 1), "second"],
            "multiple",
            [">first|1:2<", ">second|2:1<"],
        ),
    ],
)
def test_get_view(python_text_model, cursor_position, cursor_key, expected_output):
    # Setup model with a cursor
    if isinstance(cursor_position, list):
        for pos, key in zip(cursor_position[::2], cursor_position[1::2], strict=False):
            position = Position(line=pos[0], character=pos[1])
            python_text_model.insert_cursor(key, position)
    else:
        position = Position(line=cursor_position[0], character=cursor_position[1])
        python_text_model.insert_cursor(cursor_key, position)

    # Get the view
    view = python_text_model.get_view()

    # Assert the expected cursor format is in the view
    assert ">primary|1:1<" in view
    assert (
        expected_output in view
        if not isinstance(expected_output, list)
        else all(output in view for output in expected_output)
    )


@pytest.mark.parametrize(
    "cursor_position, cursor_key, expected_output",
    [
        # Cursor at the beginning of the file
        ((1, 2), "start_test", ">start_test|1:2<"),
        # Cursor at the end of a line
        ((1, 21), "end_line", ">end_line|1:21<"),
        # Cursor in an empty file
        ((1, 2), "empty", ">empty|1:2<"),
        # Multiple cursors
        (
            [(1, 2), "first", (2, 1), "second"],
            "multiple",
            [">first|1:2<", ">second|2:1<"],
        ),
    ],
)
def test_get_simple_view(python_text_model, cursor_position, cursor_key, expected_output):
    # Setup model with a cursor
    if isinstance(cursor_position, list):
        for pos, key in zip(cursor_position[::2], cursor_position[1::2], strict=False):
            position = Position(line=pos[0], character=pos[1])
            python_text_model.insert_cursor(key, position)
    else:
        position = Position(line=cursor_position[0], character=cursor_position[1])
        python_text_model.insert_cursor(cursor_key, position)

    # Get the view
    view = python_text_model.get_simple_view()

    # Assert the expected cursor format is in the view
    assert ">primary|1:1<" not in view
    assert "1    |" in view
    assert (
        expected_output not in view
        if not isinstance(expected_output, list)
        else all(output not in view for output in expected_output)
    )


@pytest.mark.parametrize(
    "cursor_position, cursor_key, expected_output",
    [
        # Cursor at the beginning of the file
        ((1, 2), "start_test", ">start_test|1:2<"),
        # Cursor at the end of a line
        ((1, 21), "end_line", ">end_line|1:21<"),
        # Cursor in an empty file
        ((1, 2), "empty", ">empty|1:2<"),
        # Multiple cursors
        (
            [(1, 2), "first", (2, 1), "second"],
            "multiple",
            [">first|1:2<", ">second|2:1<"],
        ),
    ],
)
def test_get_render(python_text_model, cursor_position, cursor_key, expected_output):
    # Setup model with a cursor
    if isinstance(cursor_position, list):
        for pos, key in zip(cursor_position[::2], cursor_position[1::2], strict=False):
            position = Position(line=pos[0], character=pos[1])
            python_text_model.insert_cursor(key, position)
    else:
        position = Position(line=cursor_position[0], character=cursor_position[1])
        python_text_model.insert_cursor(cursor_key, position)
    # Get the view render
    jinja = """以下是{{ uri }}的文档内容:
```{{ language_id }}
{{ original_content }}
```
请注意为了方便编辑，我们使用格式化的文本将光标所在位置做了标注，同时每一行添加了行号备注。光标的格式为:
">{{ key }}|{{ line_number }}:{{ column_number }}<"
你计算位置时，需要忽略光标结构对字符串长度带来的影响，比如：
>primary|1:1<print('hello world!')
在这个例子中，第一行的字符串的长度是22，不会受光标结构影响（即光标不占用实际宽度）。行首光标的位置是1:1，同时行末位置应该是1:22，EOL并不算入行内字符。
为了方便你阅读行号，在每一行的开始，插入了一个固定宽度的字符串记录当前行号，与代码正文使用 '|' 分隔，计算光标位置的时候不要计算这一部分。光标定位坐标采用 1-based，注意均是从1开始计数
添加了光标与行号信息后的文本如下:
```{{ language_id }}
{{ content_value }}
```
"""
    view_render = python_text_model.get_render(jinja=jinja)

    # Assert the expected cursor format is in the view
    assert ">primary|1:1<" in view_render
    assert (
        expected_output in view_render
        if not isinstance(expected_output, list)
        else all(output in view_render for output in expected_output)
    )


@pytest.mark.parametrize(
    "cursor_position, cursor_key, expected_output",
    [
        # Cursor at the beginning of the file
        ((1, 2), "start_test", ">start_test|1:2<"),
        # Cursor at the end of a line
        ((1, 21), "end_line", ">end_line|1:21<"),
        # Cursor in an empty file
        ((1, 2), "empty", ">empty|1:2<"),
        # Multiple cursors
        (
            [(1, 2), "first", (2, 1), "second"],
            "multiple",
            [">first|1:2<", ">second|2:1<"],
        ),
    ],
)
def test_get_render_without_cursor(python_text_model, cursor_position, cursor_key, expected_output):
    # Setup model with a cursor
    if isinstance(cursor_position, list):
        for pos, key in zip(cursor_position[::2], cursor_position[1::2], strict=False):
            position = Position(line=pos[0], character=pos[1])
            python_text_model.insert_cursor(key, position)
    else:
        position = Position(line=cursor_position[0], character=cursor_position[1])
        python_text_model.insert_cursor(cursor_key, position)
    # Get the view render
    jinja = """以下是{{ uri }}的文档内容:
请注意为了方便编辑，为每一行添加了行号备注。
为了方便你阅读行号，在每一行的开始，插入了一个固定宽度的字符串记录当前行号，与代码正文使用 '|' 分隔，计算光标位置的时候不要计算这一部分。
光标定位坐标采用 1-based，注意均是从1开始计数。行尾使用-1表示。

```{{ language_id }}
{{ content_value }}
```
"""
    view_render = python_text_model.get_render(jinja=jinja, with_cursor=False)

    # Assert the expected cursor format is in the view
    assert ">primary|1:1<" not in view_render
    assert (
        expected_output not in view_render
        if not isinstance(expected_output, list)
        else all(output not in view_render for output in expected_output)
    )
    assert "  |" in view_render, "仍然需要有行号表示"


@pytest.mark.parametrize(
    "cursor_position, cursor_key, expected_output",
    [
        # Cursor at the beginning of the file
        ((1, 2), "start_test", ">start_test|1:2<"),
        # Cursor at the end of a line
        ((1, 21), "end_line", ">end_line|1:21<"),
        # Cursor in an empty file
        ((1, 2), "empty", ">empty|1:2<"),
        # Multiple cursors
        (
            [(1, 2), "first", (2, 1), "second"],
            "multiple",
            [">first|1:2<", ">second|2:1<"],
        ),
    ],
)
def test_get_render_without_cursor_and_line_num(python_text_model, cursor_position, cursor_key, expected_output):
    # Setup model with a cursor
    if isinstance(cursor_position, list):
        for pos, key in zip(cursor_position[::2], cursor_position[1::2], strict=False):
            position = Position(line=pos[0], character=pos[1])
            python_text_model.insert_cursor(key, position)
    else:
        position = Position(line=cursor_position[0], character=cursor_position[1])
        python_text_model.insert_cursor(cursor_key, position)
    # Get the view render
    jinja = """以下是{{ uri }}的文档内容:

```{{ language_id }}
{{ content_value }}
```
"""
    view_render = python_text_model.get_render(jinja=jinja, with_cursor=False, with_line_num=False)

    # Assert the expected cursor format is in the view
    assert ">primary|1:1<" not in view_render
    assert (
        expected_output not in view_render
        if not isinstance(expected_output, list)
        else all(output not in view_render for output in expected_output)
    )
    assert "1   |" not in view_render, "仍然需要有行号表示"


@pytest.mark.parametrize(
    "cursor_position, cursor_key, content_range, expected_output",
    [
        # Cursor at the beginning of the file
        (
            (1, 2),
            "start_test",
            (Position(1, 1), Position(1, 21)),
            ["1    |", ">start_test|1:2<", "Sample Python File"],
        ),
        # Cursor at the end of a line
        (
            (1, 21),
            "end_line",
            (Position(1, 1), Position(3, 1)),
            ["1    |", ">end_line|1:21<", "2    |"],
        ),
        # Cursor in an empty file
        ((1, 2), "empty", (Position(1, 1), Position(3, 1)), ">empty|1:2<"),
        # Multiple cursors
        (
            [(1, 2), "first", (2, 1), "second"],
            "multiple",
            (Position(1, 1), Position(3, 1)),
            [">first|1:2<", ">second|2:1<"],
        ),
    ],
)
def test_get_view_advanced(python_text_model, cursor_position, cursor_key, content_range, expected_output):
    # Setup model with a cursor
    if isinstance(cursor_position, list):
        for pos, key in zip(cursor_position[::2], cursor_position[1::2], strict=False):
            position = Position(line=pos[0], character=pos[1])
            python_text_model.insert_cursor(key, position)
    else:
        position = Position(line=cursor_position[0], character=cursor_position[1])
        python_text_model.insert_cursor(cursor_key, position)
    # Get the view
    view = python_text_model.get_view(
        with_line_num=True,
        content_range=Range(start_position=content_range[0], end_position=content_range[1]),
    )

    # Assert the expected cursor format is in the view
    assert ">primary|1:1<" in view
    assert (
        expected_output in view
        if not isinstance(expected_output, list)
        else all(output in view for output in expected_output)
    )


# Test with no cursors
def test_get_view_insert_cursor_with_invalid_pos(python_text_model):
    position = Position(line=1, character=11111)
    with pytest.raises(ValueError):
        python_text_model.insert_cursor("key", position, strict=True)
    python_text_model.insert_cursor("key", position)
    assert repr(python_text_model.cursors["key"]) == ">key|1:21<"


# Test cursor at the end of the document
def test_delete_cursor(python_text_model):
    view = python_text_model.insert_cursor("key", Position(line=1, character=21))
    assert ">key|1:21<" in view
    view = python_text_model.delete_cursor("key")
    assert ">key|1:21<" not in view


def test_clear_cursor(python_text_model):
    python_text_model.insert_cursor("key", Position(line=1, character=21))
    view = python_text_model.get_view()
    assert ">key|1:21<" in view
    view = python_text_model.clear_cursors()
    assert ">key|1:21<" not in view


# Test applying various single and multiple edit operations
@pytest.mark.parametrize(
    "edits, expected_output",
    [
        # Insert text
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(2, 1), end_position=Position(2, 1)),
                    text="import sys\n",
                ),
            ],
            "# Sample Python File\nimport sys\nprint('Hello, world!')",
        ),
        # Delete text
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(2, 1), end_position=Position(2, 17)),
                    text="",
                ),
            ],
            "# Sample Python File\nrld!')",
        ),
        # Replace text
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(2, 8), end_position=Position(2, 18)),
                    text="Python 3.8",
                ),
            ],
            "# Sample Python File\nprint('Python 3.8ld!')",
        ),
        # Multiple edits
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(2, 8), end_position=Position(2, 21)),
                    text="Python",
                ),
                SingleEditOperation(
                    range=Range(start_position=Position(3, 1), end_position=Position(3, 1)),
                    text="\nprint('World!')",
                ),
            ],
            "# Sample Python File\nprint('Python')\nprint('World!')",
        ),
        # Edge cases
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(1, 1), end_position=Position(3, 18)),
                    text="",
                ),
            ],
            "",
        ),
        # Replace one line
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(1, 1), end_position=Position(2, 1)),
                    text="New content\n",
                ),
            ],
            "New content\nprint('Hello, world!')",
        ),
    ],
)
def test_apply_edits(python_text_model, edits, expected_output):
    python_text_model.apply_edits(edits)
    assert python_text_model.get_value() == expected_output


# Complex test cases including undo operations
@pytest.mark.parametrize(
    "edits, expected_output, compute_undo_edits",
    [
        # Multiple non-overlapping edits
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(2, 1), end_position=Position(2, 1)),
                    text="import sys\n",
                ),
                SingleEditOperation(
                    range=Range(start_position=Position(3, 1), end_position=Position(3, 1)),
                    text="\nprint('finish')",
                ),
            ],
            "# Sample Python File\nimport sys\nprint('Hello, world!')\nprint('finish')",
            True,
        ),
        # Adjacent edits
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(2, 1), end_position=Position(2, 1)),
                    text=" World\n",
                ),
                SingleEditOperation(
                    range=Range(start_position=Position(2, 1), end_position=Position(2, 1)),
                    text="Hello",
                ),
            ],
            "# Sample Python File\nHello World\nprint('Hello, world!')",
            False,
        ),
        # Overlapping edits should raise an error
        (
            [
                SingleEditOperation(
                    range=Range(start_position=Position(2, 1), end_position=Position(2, 5)),
                    text="Hey",
                ),
                SingleEditOperation(
                    range=Range(start_position=Position(2, 3), end_position=Position(2, 7)),
                    text=" there",
                ),
            ],
            None,
            False,
        ),
    ],
)
def test_apply_edits_with_complex_scenarios(python_text_model, edits, expected_output, compute_undo_edits):
    origin_value = python_text_model.get_value()
    if expected_output is None:
        with pytest.raises(ValueError):
            python_text_model.apply_edits(edits, compute_undo_edits)
    else:
        undo_edits = python_text_model.apply_edits(edits, compute_undo_edits)
        assert python_text_model.get_value() == expected_output
        if compute_undo_edits:
            assert undo_edits is not None
            python_text_model.apply_edits(
                [SingleEditOperation(range=undo.range, text=undo.new_text) for undo in undo_edits],
            )
            assert python_text_model.get_value() == origin_value


@pytest.fixture
def text_model_multiline():
    with NamedTemporaryFile(mode="w+", suffix=".py", delete=True) as temp_file:
        # 写入包含多行和特殊字符的 Python 代码
        content = """
# Sample Python File
print('Hello, world!')
def hello(name):
    print(f"Hello, {name}!")
hello("Python")
# Another comment
"""
        temp_file.write(content)
        temp_file.flush()

        # 创建 TextModel 实例
        language_id = LanguageId.python
        uri = AnyUrl(f"file://{temp_file.name}")
        model = TextModel(language_id=language_id, uri=uri)

        yield model
        temp_file.close()


def test_basic_search(text_model_multiline):
    results = text_model_multiline.find_matches("hello")
    assert len(results) == 4  # 'hello' 出现在四处
    results = text_model_multiline.find_matches("hello", match_case=True)
    assert len(results) == 2  # 'hello' 出现在两处（满足大小写要求）


def test_regex_search(text_model_multiline):
    results = text_model_multiline.find_matches(r"Hello, \w+!", is_regex=True)
    assert len(results) == 1  # 一处符合正则表达式
    results = text_model_multiline.find_matches(r"Hello, {\w+}!", is_regex=True)
    assert len(results) == 1  # 源代码中有一处符合此要求


def test_case_insensitive_search(text_model_multiline):
    results = text_model_multiline.find_matches("HELLO", match_case=False)
    assert len(results) == 4  # 不区分大小写


def test_limit_results(text_model_multiline):
    results = text_model_multiline.find_matches("hello", limit_result_count=1)
    assert len(results) == 1  # 限制结果数量


def test_capture_matches(text_model_multiline):
    results = text_model_multiline.find_matches("hello", capture_matches=True)
    assert all(res.match is not None for res in results)  # 确保捕获了匹配结果


@pytest.mark.parametrize(
    "search_string, expected_count",
    [
        ("print", 2),
        ("def", 1),
        ("#", 2),
    ],
)
def test_various_search_strings(text_model_multiline, search_string, expected_count):
    results = text_model_multiline.find_matches(search_string)
    assert len(results) == expected_count  # 根据搜索字符串检查匹配数量


@pytest.mark.parametrize(
    "search_string, search_scope, expected_count",
    [
        ("print", Range(start_position=Position(1, 1), end_position=Position(4, 1)), 1),
        (
            "print",
            [
                Range(start_position=Position(1, 1), end_position=Position(4, 1)),
                Range(start_position=Position(5, 5), end_position=Position(5, 15)),
            ],
            2,
        ),
        (
            "print",
            [
                Range(start_position=Position(1, 1), end_position=Position(4, 1)),
                Range(start_position=Position(5, 5), end_position=Position(5, 7)),
                Range(start_position=Position(5, 7), end_position=Position(5, 15)),
            ],
            2,
        ),
    ],
)
def test_various_search_strings_in_scope(text_model_multiline, search_string, search_scope, expected_count):
    results = text_model_multiline.find_matches(search_string, search_scope=search_scope)
    assert len(results) == expected_count  # 根据搜索字符串检查匹配数量


def test_find_matches_line_by_line_basic(text_model_multiline):
    # 测试单行中多次出现的情况
    results = text_model_multiline.find_matches_line_by_line(
        [text_model_multiline.get_full_model_range()],
        "print",
        match_case=True,
        capture_matches=False,
        limit_result_count=None,
    )
    assert len(results) == 2  # 'print' 出现在三行中


def test_find_matches_line_by_line_case_insensitive(text_model_multiline):
    # 测试大小写不敏感的匹配
    results = text_model_multiline.find_matches_line_by_line(
        [text_model_multiline.get_full_model_range()],
        "PRINT",
        match_case=False,
        capture_matches=False,
        limit_result_count=None,
    )
    assert len(results) == 2  # 'PRINT'（不区分大小写）匹配三处


def test_find_matches_line_by_line_limit_results(text_model_multiline):
    # 测试限制结果数量
    results = text_model_multiline.find_matches_line_by_line(
        [text_model_multiline.get_full_model_range()],
        "print",
        match_case=True,
        capture_matches=False,
        limit_result_count=1,
    )
    assert len(results) == 1  # 限制结果为1


def test_find_matches_line_by_line_capture_matches(text_model_multiline):
    # 测试捕获匹配的文本
    results = text_model_multiline.find_matches_line_by_line(
        [text_model_multiline.get_full_model_range()],
        "print",
        match_case=True,
        capture_matches=True,
        limit_result_count=None,
    )
    assert all(res.match == "print" for res in results)  # 检查每个结果是否正确捕获了 'print'


@pytest.mark.parametrize(
    "line_content, search_string, match_case, expected_count",
    [
        ("this is a line with special words: this, This, THIS.", "this", True, 2),
        ("this is a line with special words: this, This, THIS.", "this", False, 4),
        ("single occurrence", "single", True, 1),
    ],
)
def test_find_matches_line_by_line_various(
    text_model_multiline,
    line_content,
    search_string,
    match_case,
    expected_count,
):
    full_range = text_model_multiline.get_full_model_range()
    operation = SingleEditOperation(range=full_range, text=line_content)
    # 设置单行内容以测试不同情况
    text_model_multiline.apply_edits([operation])
    results = text_model_multiline.find_matches_line_by_line(
        [text_model_multiline.get_full_model_range()],
        search_string,
        match_case,
        capture_matches=False,
        limit_result_count=None,
    )
    assert len(results) == expected_count  # 根据参数检查匹配数量
