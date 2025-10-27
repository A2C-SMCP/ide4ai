# filename: test_text_model_search.py
# @Time    : 2024/5/6 14:49
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import re
from tempfile import NamedTemporaryFile

import pytest
from pydantic import AnyUrl

from ide4ai.environment.workspace.model import TextModel
from ide4ai.environment.workspace.model_search import (
    LineFeedCounter,
    SearchParams,
    TextModelSearch,
    escape_regexp_characters,
)
from ide4ai.environment.workspace.schema import Position, Range
from ide4ai.schema import LanguageId


@pytest.fixture
def python_text_model():
    # Create a TextModel instance with multiple lines of Python code
    content = """# Sample Python File
class Sample:
    def hello(self):
        print("Hello, world!")

    def goodbye(self):
        print("Goodbye, world!")
    """
    with NamedTemporaryFile(mode="w+", suffix=".py", delete=True) as temp_file:
        # Write some initial Python code to the file
        temp_file.write(content)
        temp_file.flush()  # Ensure it's written to disk
        # Create a TextModel instance
        language_id = LanguageId.python  # Assuming you have a predefined LanguageId enum
        uri = AnyUrl(f"file://{temp_file.name}")  # Using file URI for real file handling
        model = TextModel(language_id=language_id, uri=uri)
        yield model
        # Cleanup: Close and remove the temporary file
        temp_file.close()  # Make sure file is closed before removal


def test_simple_string_search(python_text_model):
    search_params = SearchParams(search_string="Hello", is_regex=False, match_case=True)
    search_range = Range(start_position=Position(1, 1), end_position=Position(5, 1))
    results = TextModelSearch.find_matches(python_text_model, search_params, search_range, capture_matches=True)
    assert len(results) == 1
    assert results[0].match == "Hello"


def test_case_insensitive_search(python_text_model):
    search_params = SearchParams(search_string="hello", is_regex=False, match_case=True)
    search_range = Range(start_position=Position(1, 1), end_position=Position(5, 1))
    results = TextModelSearch.find_matches(python_text_model, search_params, search_range, capture_matches=True)
    assert len(results) == 1
    assert results[0].match == "hello"


def test_regex_search(python_text_model):
    search_params = SearchParams(search_string=r"def\s+\w+", is_regex=True, match_case=False)
    search_range = Range(start_position=Position(1, 1), end_position=Position(7, 1))
    results = TextModelSearch.find_matches(python_text_model, search_params, search_range, capture_matches=True)
    assert len(results) == 2
    assert results[0].match == "def hello"
    assert results[1].match == "def goodbye"


def test_multiline_search(python_text_model):
    search_params = SearchParams(search_string=r"def\s+.+\s+print", is_regex=True, match_case=True)
    search_range = Range(start_position=Position(1, 1), end_position=Position(8, 1))
    results = TextModelSearch.find_matches(python_text_model, search_params, search_range, capture_matches=True)
    assert len(results) == 2
    assert "print" in results[0].match
    assert "print" in results[1].match


def test_no_match_found(python_text_model):
    search_params = SearchParams(search_string="nonexistent", is_regex=False, match_case=True)
    search_range = Range(start_position=Position(1, 1), end_position=Position(5, 1))
    results = TextModelSearch.find_matches(python_text_model, search_params, search_range, capture_matches=True)
    assert len(results) == 0


def test_search_with_special_characters(python_text_model):
    search_params = SearchParams(search_string="Goodbye, world!", is_regex=False, match_case=True)
    search_range = Range(start_position=Position(1, 1), end_position=Position(8, 1))
    results = TextModelSearch.find_matches(python_text_model, search_params, search_range, capture_matches=True)
    assert len(results) == 1
    assert results[0].match == "Goodbye, world!"
    assert results[0].range == Range(start_position=Position(7, 16), end_position=Position(7, 31))


@pytest.mark.parametrize(
    "search_string, expected_result",
    [
        ("\n", True),  # Direct newline
        ("\\n", True),  # Escaped newline
        ("Hello\\nWorld", True),  # Newline in the middle of text
        ("\\r", True),  # Carriage return
        ("\\W", True),  # Non-word character shorthand
        ("\\\\n", False),  # Escaped backslash followed by 'n' should not be multiline
        ("Hello\\", False),  # Ending with a lone backslash
        ("Hello World", False),  # No special characters
        ("\\\\", False),  # Escaped backslash
        ("Hello\\r\\nWorld", True),  # Windows-style line ending
    ],
)
def test_is_multiline_regex_source(search_string, expected_result):
    search_params = SearchParams(search_string=search_string)
    assert search_params.is_multiline_regex_source() == expected_result


def test_backslash_at_end_of_search_string():
    search_string = "Hello\\"
    search_params = SearchParams(search_string=search_string)
    assert not search_params.is_multiline_regex_source()


def test_complex_regex_with_escaped_characters():
    search_string = "Line1\\nLine2\\rLine3\\WEnd"
    search_params = SearchParams(search_string=search_string)
    assert search_params.is_multiline_regex_source()


def test_create_regexp_with_multiline_regex():
    # Regex mode, search string contains explicit newline patterns
    search_params = SearchParams(search_string="one\\ntwo", is_regex=True)
    regex = search_params.create_regexp()
    assert regex.flags & re.MULTILINE  # Check if MULTILINE flag is set
    assert "one\\ntwo" == regex.pattern  # Ensure pattern is unchanged because it's already a regex


def test_create_regexp_with_newline_in_non_regex_mode():
    # Non-regex mode, search string contains actual newline
    search_params = SearchParams(search_string="one\ntwo", is_regex=False)
    regex = search_params.create_regexp()
    assert regex.flags & re.MULTILINE  # Check if MULTILINE flag is set
    escaped_pattern = escape_regexp_characters("one\ntwo")
    assert escaped_pattern == regex.pattern  # Ensure pattern is escaped properly


def test_create_regexp_without_multiline_flag_when_no_newline():
    # Regex mode but no newline characters
    search_params = SearchParams(search_string="one|two", is_regex=True)
    regex = search_params.create_regexp()
    assert not (regex.flags & re.MULTILINE)  # MULTILINE flag should not be set
    assert "one|two" == regex.pattern  # Pattern should be unchanged


def test_create_regexp_case_insensitivity():
    # Case insensitivity test
    search_params = SearchParams(search_string="caseTest", is_regex=False, match_case=False)
    regex = search_params.create_regexp()
    assert regex.flags & re.IGNORECASE  # Check if IGNORECASE flag is set


def test_create_regexp_unicode_flag():
    # Check Unicode flag
    search_params = SearchParams(search_string="unicode😊", is_regex=False)
    regex = search_params.create_regexp()
    assert regex.flags & re.UNICODE  # Check if UNICODE flag is set


@pytest.fixture
def multiline_text_model():
    # Create a TextModel instance with multiple lines of Python code using \r\n for line breaks
    content = (
        '# Sample Python File\r\nclass Sample:\r\n    def hello(self):\r\n        print("Hello, world!")\r\n    '
        'def goodbye(self):\r\n        print("Goodbye, world!")\r\n'
    )
    with NamedTemporaryFile(mode="w+", suffix=".py", delete=True) as temp_file:
        # Write some initial Python code to the file
        temp_file.write(content)
        temp_file.flush()  # Ensure it's written to disk
        # Create a TextModel instance
        language_id = LanguageId.python  # Assuming you have a predefined LanguageId enum
        uri = AnyUrl(f"file://{temp_file.name}")  # Using file URI for real file handling
        model = TextModel(language_id=language_id, uri=uri)
        yield model
        # Cleanup: Close and remove the temporary file
        temp_file.close()  # Make sure file is closed before removal


def test_line_feed_counter_usage(multiline_text_model):
    search_params = SearchParams(search_string=r"hello\(self\):\n", is_regex=True, match_case=True)
    search_range = Range(start_position=Position(1, 1), end_position=Position(5, 1))
    results = TextModelSearch._do_find_matches_multiline(
        multiline_text_model,
        search_range,
        re.compile(search_params.search_string, re.MULTILINE),
        capture_matches=True,
        limit_result_count=None,
    )
    assert len(results) == 1
    assert results[0].match == "hello(self):\n"
    assert results[0].range == Range(start_position=Position(3, 9), end_position=Position(4, 1))


def test_regular_search_with_crlf(multiline_text_model):
    search_params = SearchParams(search_string='print("Hello, world!")', is_regex=False, match_case=True)
    search_range = Range(start_position=Position(1, 1), end_position=Position(6, 35))
    results = TextModelSearch._do_find_matches_multiline(
        multiline_text_model,
        search_range,
        re.compile(re.escape(search_params.search_string), re.MULTILINE),
        capture_matches=True,
        limit_result_count=None,
    )
    assert len(results) == 1
    assert "Hello, world!" in results[0].match


@pytest.mark.parametrize(
    "text, offset, expected_count",
    [
        ("", 0, 0),  # No line feeds, checking boundary logic
        ("No line feeds here", 10, 0),  # No line feeds, middle offset
        (
            "\nStarts with a line feed",
            0,
            0,
        ),  # Line feed at start, checking exact position zero
        ("\n\nTwo line feeds at start", 1, 1),  # Offset after the first line feed
        ("Ends with a line feed\n", 22, 1),  # Offset beyond the only line feed
        ("Ends with a line feed\n", 20, 0),  # Offset beyond the only line feed
        ("Line\nFeed\nHere", 4, 0),  # Offset exactly at the line feed
        ("Line\nFeed\nHere", 5, 1),  # Offset right after a line feed
        (
            "Multiple\n\nLine Feeds\nHere",
            10,
            2,
        ),  # Middle offset, multiple line feeds before
        ("Multiple\n\nLine Feeds\nHere", 9, 1),  # Middle offset, between line feeds
        ("Line\nFeed\nHere", 50, 2),  # Offset beyond the text length
    ],
)
def test_find_line_feed_count_before_offset(text, offset, expected_count):
    lfc = LineFeedCounter(text=text)
    count = lfc.find_line_feed_count_before_offset(offset)
    assert count == expected_count


def test_binary_search_logic():
    # Specific cases to hit the binary search branches
    text = "\nOne\nTwo\nThree\nFour\nFive\nSix\nSeven\nEight\nNine\nTen"
    lfc = LineFeedCounter(text=text)

    # Edge cases around boundary conditions
    assert lfc.find_line_feed_count_before_offset(0) == 0  # Before any line feed
    assert lfc.find_line_feed_count_before_offset(1) == 1  # Immediate after the first line feed
    assert lfc.find_line_feed_count_before_offset(4) == 1  # Right before the second line feed
    assert lfc.find_line_feed_count_before_offset(5) == 2  # Right on the second line feed
    assert lfc.find_line_feed_count_before_offset(len(text)) == text.count("\n")  # At the end of all content


def test_high_offset_with_few_line_feeds():
    # Scenario with a high offset and few line feeds to test lower boundary condition logic
    text = "\nOne line feed only"
    lfc = LineFeedCounter(text=text)
    assert lfc.find_line_feed_count_before_offset(50) == 1  # Very high offset beyond text length


def test_no_line_feeds():
    # Text with no line feeds at all
    text = "Absolutely no line feeds here"
    lfc = LineFeedCounter(text=text)
    assert lfc.find_line_feed_count_before_offset(10) == 0  # Middle offset
    assert lfc.find_line_feed_count_before_offset(0) == 0  # Start offset
    assert lfc.find_line_feed_count_before_offset(100) == 0  # Offset way beyond the text length
