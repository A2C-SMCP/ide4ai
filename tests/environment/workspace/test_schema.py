# filename: test_schema.py
# @Time    : 2024/4/18 14:46
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import pytest
from pydantic import ValidationError

from src.ai_ide.environment.workspace.schema import (
    Cursor,
    Position,
    Range,
    TextChange,
)


# 测试 Position 比较
def test_position_comparisons():
    pos1 = Position(1, 5)
    pos2 = Position(1, 10)
    pos3 = Position(2, 1)

    assert pos1 < pos2, "pos1应该小于pos2"
    assert pos3 > pos2, "pos3应该大于pos2"
    assert pos1 != pos3, "pos1应该不等于pos3"


# 测试 Range 的并集
def test_range_union():
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 10))
    r2 = Range(start_position=Position(1, 10), end_position=Position(1, 15))
    union = r1 | r2

    assert union.start_position == Position(1, 5), "并集的开始位置错误"
    assert union.end_position == Position(1, 15), "并集的结束位置错误"


def test_sort_range() -> None:
    ranges = [
        {
            "range": Range(start_position=Position(1, 1), end_position=Position(1, 5)),
            "identifier": "b",
        },
        {
            "range": Range(start_position=Position(1, 1), end_position=Position(1, 3)),
            "identifier": "b2",
        },
        {
            "range": Range(start_position=Position(2, 1), end_position=Position(2, 5)),
            "identifier": "c",
        },
        {
            "range": Range(start_position=Position(3, 1), end_position=Position(3, 5)),
            "identifier": "a",
        },
    ]
    # 对ranges列表进行排序
    ranges.sort(key=lambda x: x["range"], reverse=True)
    expected_identifiers = ["a", "c", "b", "b2"]
    identifiers = [r["identifier"] for r in ranges]

    assert identifiers == expected_identifiers, f"Expected order was {expected_identifiers}, but got {identifiers}"


def test_range_assignment() -> None:
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 10))
    with pytest.raises(ValidationError):
        r1.start_position = Position(2, 11)


# 测试 Range 的交集
def test_range_intersection():
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 15))
    r2 = Range(start_position=Position(1, 10), end_position=Position(1, 20))
    intersection = r1 & r2

    assert intersection.start_position == Position(1, 10), "交集的开始位置错误"
    assert intersection.end_position == Position(1, 15), "交集的结束位置错误"

    # 测试没有交集的情况
    r3 = Range(start_position=Position(2, 1), end_position=Position(2, 5))
    intersection = r1 & r3
    assert intersection is None, "应当返回 None 表示没有交集"


# 测试 Range 的差集
def test_range_difference():
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 15))
    r2 = Range(start_position=Position(1, 10), end_position=Position(1, 12))
    difference = r1 - r2

    assert len(difference) == 2, "差集应包含两个区间"
    assert difference[0].start_position == Position(1, 5), "第一个区间的开始位置错误"
    assert difference[0].end_position == Position(1, 10), "第一个区间的结束位置错误"
    assert difference[1].start_position == Position(1, 12), "第二个区间的开始位置错误"
    assert difference[1].end_position == Position(1, 15), "第二个区间的结束位置错误"


# 禁用加法运算测试
def test_range_add_not_implemented():
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 10))
    with pytest.raises(NotImplementedError):
        r1 + r1


# 测试 Range 的并集赋值操作 |=
def test_range_union_inplace():
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 10))
    r2 = Range(start_position=Position(1, 10), end_position=Position(1, 15))
    r1 |= r2

    assert r1.start_position == Position(1, 5), "并集赋值操作后开始位置错误"
    assert r1.end_position == Position(1, 15), "并集赋值操作后结束位置错误"


# 测试 Range 的交集赋值操作 &=
def test_range_intersection_inplace():
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 15))
    r2 = Range(start_position=Position(1, 10), end_position=Position(1, 20))
    r1 &= r2

    assert r1.start_position == Position(1, 10), "交集赋值操作后开始位置错误"
    assert r1.end_position == Position(1, 15), "交集赋值操作后结束位置错误"

    # 测试没有交集的情况应引发异常
    r3 = Range(start_position=Position(2, 1), end_position=Position(2, 5))
    with pytest.raises(ValueError):
        r1 &= r3


# 测试 Range 的差集赋值操作 -=
def test_range_difference_inplace():
    r1 = Range(start_position=Position(1, 5), end_position=Position(1, 15))
    r2 = Range(start_position=Position(1, 10), end_position=Position(1, 12))
    with pytest.raises(ValueError):
        r1 -= r2

    r3 = Range(start_position=Position(1, 10), end_position=Position(1, 15))
    r1 -= r3
    # 由于差集可能产生一个或多个区间，此操作需要谨慎处理
    assert r1.start_position == Position(1, 5), "差集赋值操作后第一个区间开始位置错误"
    assert r1.end_position == Position(1, 10), "差集赋值操作后第一个区间结束位置错误"

    # 如果差集结果为多个区间，则应引发异常
    r3 = Range(start_position=Position(1, 5), end_position=Position(1, 15))
    r4 = Range(start_position=Position(1, 7), end_position=Position(1, 10))
    with pytest.raises(ValueError):
        r3 -= r4


@pytest.mark.parametrize(
    "pos1, pos2, expected_lt, expected_eq, expected_le",
    [
        (Position(1, 5), Position(1, 5), False, True, True),  # Equal positions
        (
            Position(1, 3),
            Position(1, 5),
            True,
            False,
            True,
        ),  # Same line, lesser character
        (Position(2, 1), Position(1, 10), False, False, False),  # Greater line
        (Position(1, 10), Position(2, 1), True, False, True),  # Lesser line
    ],
)
def test_position_ordering(pos1, pos2, expected_lt, expected_eq, expected_le):
    assert (pos1 < pos2) == expected_lt
    assert (pos1 == pos2) == expected_eq
    assert (pos1 <= pos2) == expected_le
    assert (pos1 > pos2) is not expected_le
    assert (pos1 >= pos2) is not expected_lt
    assert (pos1 != pos2) is not expected_eq


@pytest.mark.parametrize(
    "start, end, is_empty",
    [
        ((1, 1), (1, 1), True),
        ((1, 1), (1, 5), False),
        ((1, 5), (2, 1), False),
    ],
)
def test_range_empty(start, end, is_empty):
    start_pos = Position(*start)
    end_pos = Position(*end)
    range_instance = Range(start_position=start_pos, end_position=end_pos)
    assert range_instance.is_empty() == is_empty


@pytest.mark.parametrize(
    "range_info, position, contains",
    [
        (((1, 1), (1, 5)), (1, 3), True),
        (((1, 1), (1, 5)), (1, 6), False),
    ],
)
def test_contains_position(range_info, position, contains):
    start_pos = Position(*range_info[0])
    end_pos = Position(*range_info[1])
    c_pos = Position(*position)
    range_instance = Range(start_position=start_pos, end_position=end_pos)
    assert range_instance.contains_position(c_pos) == contains


@pytest.mark.parametrize(
    "base_range, test_range, result",
    [
        (((1, 1), (1, 5)), ((1, 1), (1, 3)), True),
        (((1, 1), (1, 5)), ((1, 1), (1, 5)), True),
        (((1, 1), (1, 5)), ((1, 1), (1, 6)), False),
    ],
)
def test_contains_range(base_range, test_range, result):
    base = Range(start_position=Position(*base_range[0]), end_position=Position(*base_range[1]))
    test = Range(start_position=Position(*test_range[0]), end_position=Position(*test_range[1]))
    assert base.contains_range(test) == result


@pytest.mark.parametrize(
    "base_range, test_range, expected_intersection",
    [
        (((1, 1), (1, 5)), ((1, 3), (1, 6)), ((1, 3), (1, 5))),
        (((1, 1), (1, 5)), ((1, 6), (1, 7)), None),
    ],
)
def test_intersect_ranges_1(base_range, test_range, expected_intersection):
    base = Range(start_position=Position(*base_range[0]), end_position=Position(*base_range[1]))
    test = Range(start_position=Position(*test_range[0]), end_position=Position(*test_range[1]))
    intersection = base.intersect_ranges(test)
    another_intersection = base & test
    assert another_intersection == intersection
    if expected_intersection is None:
        assert intersection is None
    else:
        expected = Range(
            start_position=Position(*expected_intersection[0]),
            end_position=Position(*expected_intersection[1]),
        )
        assert intersection == expected


@pytest.mark.parametrize(
    "old_text, new_text, old_pos, new_pos, expected",
    [
        ("", "hello", 0, 0, '(insert@0 "hello")'),
        ("world", "", 5, 5, '(delete@5 "world")'),
        ("old", "new", 3, 3, '(replace@3 "old" with "new")'),
    ],
)
def test_text_change_str(old_text, new_text, old_pos, new_pos, expected):
    text_change = TextChange(
        old_position_offset=old_pos,
        old_text=old_text,
        new_position_offset=new_pos,
        new_text=new_text,
    )
    assert str(text_change) == expected


@pytest.mark.parametrize(
    "old_text, new_text, old_pos, new_pos",
    [
        ("text", "more text", 1, 1),
        ("", "inserted", 0, 0),
        ("delete", "", 5, 5),
    ],
)
def test_text_change_write_read(old_text, new_text, old_pos, new_pos):
    original = TextChange(
        old_position_offset=old_pos,
        old_text=old_text,
        new_position_offset=new_pos,
        new_text=new_text,
    )
    buffer = bytearray()
    offset = original.write(buffer, 0)
    read_change, final_offset = TextChange.read(buffer, 0)

    assert original == read_change
    assert offset == final_offset


@pytest.mark.parametrize(
    "old_text, expected_length",
    [
        ("text", 4),
        ("", 0),
    ],
)
def test_old_length(old_text, expected_length):
    text_change = TextChange(old_position_offset=0, old_text=old_text, new_position_offset=0, new_text="")
    assert text_change.old_length == expected_length


@pytest.mark.parametrize(
    "new_text, expected_length",
    [
        ("new", 3),
        ("", 0),
    ],
)
def test_new_length(new_text, expected_length):
    text_change = TextChange(old_position_offset=0, old_text="", new_position_offset=0, new_text=new_text)
    assert text_change.new_length == expected_length


@pytest.mark.parametrize(
    "old_text, old_pos, expected_end",
    [
        ("text", 1, 5),
        ("", 0, 0),
    ],
)
def test_old_end(old_text, old_pos, expected_end):
    text_change = TextChange(
        old_position_offset=old_pos,
        old_text=old_text,
        new_position_offset=0,
        new_text="",
    )
    assert text_change.old_end == expected_end


@pytest.mark.parametrize(
    "new_text, new_pos, expected_end",
    [
        ("text", 1, 5),
        ("", 0, 0),
    ],
)
def test_new_end(new_text, new_pos, expected_end):
    text_change = TextChange(
        old_position_offset=0,
        old_text="",
        new_position_offset=new_pos,
        new_text=new_text,
    )
    assert text_change.new_end == expected_end


@pytest.fixture
def create_position():
    def _create_position(line, char):
        return Position(line=line, character=char)

    return _create_position


@pytest.fixture
def create_range(create_position):
    def _create_range(start, end):
        return Range(start_position=create_position(*start), end_position=create_position(*end))

    return _create_range


# Test strict_contains_range
@pytest.mark.parametrize(
    "base_range, test_range, expected",
    [
        (((1, 1), (5, 5)), ((2, 2), (4, 4)), True),
        (((1, 1), (5, 5)), ((1, 1), (5, 5)), False),
        (((1, 1), (5, 5)), ((1, 1), (6, 6)), False),
    ],
)
def test_strict_contains_range(create_range, base_range, test_range, expected):
    base = create_range(base_range[0], base_range[1])
    test = create_range(test_range[0], test_range[1])
    assert base.strict_contains_range(test) == expected


# Test plus_range
@pytest.mark.parametrize(
    "range1, range2, expected_result",
    [
        (((1, 1), (2, 2)), ((2, 3), (3, 4)), ((1, 1), (3, 4))),
    ],
)
def test_plus_range(create_range, range1, range2, expected_result):
    r1 = create_range(range1[0], range1[1])
    r2 = create_range(range2[0], range2[1])
    expected = create_range(expected_result[0], expected_result[1])
    result = r1.plus_range(r2)
    assert result == expected


# Test intersect_ranges
@pytest.mark.parametrize(
    "range1, range2, expected_result",
    [
        (((1, 1), (2, 2)), ((2, 1), (3, 3)), ((2, 1), (2, 2))),
        (((1, 1), (2, 2)), ((3, 1), (4, 4)), None),
    ],
)
def test_intersect_ranges(create_range, range1, range2, expected_result):
    r1 = create_range(range1[0], range1[1])
    r2 = create_range(range2[0], range2[1])
    if expected_result is None:
        assert r1.intersect_ranges(r2) is None
    else:
        expected = create_range(expected_result[0], expected_result[1])
        assert r1.intersect_ranges(r2) == expected


# Test collapse_to_start
@pytest.mark.parametrize(
    "range_input, expected",
    [
        (((1, 1), (3, 3)), ((1, 1), (1, 1))),
    ],
)
def test_collapse_to_start(create_range, range_input, expected):
    r = create_range(range_input[0], range_input[1])
    expected_range = create_range(expected[0], expected[1])
    assert r.collapse_to_start() == expected_range


# Test collapse_to_end
@pytest.mark.parametrize(
    "range_input, expected",
    [
        (((1, 1), (3, 3)), ((3, 3), (3, 3))),
    ],
)
def test_collapse_to_end(create_range, range_input, expected):
    r = create_range(range_input[0], range_input[1])
    expected_range = create_range(expected[0], expected[1])
    assert r.collapse_to_end() == expected_range


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ((1, 1), (1, 5), False),  # Same line
        ((1, 5), (2, 1), True),  # Different lines
        ((2, 3), (5, 6), True),  # Several lines apart
        ((5, 1), (5, 2), False),  # Same line, close characters
        ((5, 2), (6, 1), True),  # Line break at the end
    ],
)
def test_spans_multiple_lines(create_range, start, end, expected):
    range_instance = create_range(start, end)
    assert range_instance.spans_multiple_lines() == expected


def pos(line, char):
    return Position(line=line, character=char)


def rng(start_pos, end_pos):
    return Range(start_position=start_pos, end_position=end_pos)


# Test __lt__ and __gt__
@pytest.mark.parametrize(
    "range1, range2, lt_result, gt_result",
    [
        (rng(pos(1, 1), pos(1, 5)), rng(pos(1, 6), pos(1, 10)), True, False),
        (rng(pos(2, 1), pos(2, 5)), rng(pos(1, 1), pos(1, 10)), False, True),
        (rng(pos(1, 5), pos(1, 10)), rng(pos(1, 5), pos(1, 10)), False, False),
    ],
)
def test_comparison_operators(range1, range2, lt_result, gt_result):
    assert (range1 < range2) == lt_result
    assert (range1 > range2) == gt_result


# Test __repr__
@pytest.mark.parametrize(
    "t_range, expected_repr",
    [
        (
            rng((pos(1, 1)), pos(1, 5)),
            "Range(Position(line=1, character=1), Position(line=1, character=5))",
        ),
    ],
)
def test_repr(t_range, expected_repr):
    assert repr(t_range) == expected_repr


# Test __ior__ (in-place OR, which is union)
@pytest.mark.parametrize(
    "range1, range2, expected",
    [
        (
            rng(pos(1, 1), pos(1, 5)),
            rng(pos(1, 4), pos(1, 10)),
            rng(pos(1, 1), pos(1, 10)),
        ),
    ],
)
def test_inplace_union(range1, range2, expected):
    range1 |= range2
    assert range1 == expected


# Test __iand__ (in-place AND, which is intersection)
@pytest.mark.parametrize(
    "range1, range2, expected",
    [
        (
            rng(pos(1, 1), pos(1, 10)),
            rng(pos(1, 5), pos(1, 15)),
            rng(pos(1, 5), pos(1, 10)),
        ),
    ],
)
def test_inplace_intersection(range1, range2, expected):
    range1 &= range2
    assert range1 == expected


def test_inplace_intersection_err() -> None:
    range1 = rng(pos(1, 1), pos(1, 10))
    range2 = rng(pos(2, 1), pos(2, 10))
    with pytest.raises(ValueError):
        range1 &= range2


# Test __sub__ (subtraction, non-overlapping and partially overlapping cases)
@pytest.mark.parametrize(
    "range1, range2, expected",
    [
        (
            rng(pos(1, 1), pos(1, 10)),
            rng(pos(1, 5), pos(1, 7)),
            [rng(pos(1, 1), pos(1, 5)), rng(pos(1, 7), pos(1, 10))],
        ),
    ],
)
def test_subtraction(range1, range2, expected):
    result = range1 - range2
    assert result == expected


def test_subtraction_without_intersection() -> None:
    range1 = rng(pos(1, 1), pos(1, 10))
    range2 = rng(pos(2, 1), pos(2, 10))
    range3 = range1 - range2
    assert range3[0] == range1


# Test __isub__ (in-place subtraction, results may be empty or multiple ranges)
@pytest.mark.parametrize(
    "range1, range2, expected",
    [
        (
            rng(pos(1, 1), pos(1, 10)),
            rng(pos(1, 5), pos(1, 7)),
            [rng(pos(1, 1), pos(1, 5)), rng(pos(1, 7), pos(1, 10))],
        ),
        (rng(pos(1, 1), pos(1, 10)), rng(pos(1, 1), pos(1, 10)), []),
        (
            rng(pos(1, 1), pos(1, 10)),
            rng(pos(1, 1), pos(1, 5)),
            rng(pos(1, 5), pos(1, 10)),
        ),
    ],
)
def test_inplace_subtraction(range1, range2, expected):
    try:
        range1 -= range2
        assert range1 == expected
    except ValueError as e:
        assert str(e) == "结果为空，无法更新" or str(e) == "差集操作结果为多个区间，无法更新"  # Matching the error message as defined


def test_cursor_repr() -> None:
    cursor_pos = Position(line=1, character=1)
    cursor = Cursor(key="cur", position=cursor_pos)
    assert repr(cursor) == ">cur|1:1<"
