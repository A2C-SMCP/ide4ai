# filename: test_word_character_classifier.py
# @Time    : 2024/5/7 10:16
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
# 测试 WordCharacterClassifier 的初始化和基本功能

from tfrobot.drive.tool.ides.environment.workspace.common.core.word_character_classifier import (
    WordCharacterClassifier,
    get_map_for_word_separators,
)


def test_initialization():
    classifier = WordCharacterClassifier(",", ["en"])
    assert classifier.default_value == 0
    assert classifier.get(ord(",")) == 2  # WordSeparator
    assert classifier.get(32) == 1  # Space
    assert classifier.get(9) == 1  # Tab


# 测试 find_prev_word_before_or_at_offset 和 find_next_word_at_or_after_offset
def test_word_finding():
    classifier = WordCharacterClassifier(",", ["en"])
    test_line = "hello, world"
    prev_word = classifier.find_prev_word_before_or_at_offset(test_line, 3)
    next_word = classifier.find_next_word_at_or_after_offset(test_line, 7)
    assert prev_word == "hello"
    assert next_word == "world"


# 测试 get_map_for_word_separators 缓存功能
def test_word_classifier_cache():
    classifier1 = get_map_for_word_separators(",", ["en"])
    classifier2 = get_map_for_word_separators(",", ["en"])
    classifier3 = get_map_for_word_separators(";", ["en"])
    assert classifier1 is classifier2  # 应该从缓存中返回相同的实例
    assert classifier1 is not classifier3  # 不同的分隔符应该返回不同的实例


# 测试 Segmenter 缺失的情况
def test_no_segmenter():
    classifier = WordCharacterClassifier(",", [])
    assert classifier._segmenter is None
    prev_word = classifier.find_prev_word_before_or_at_offset("hello, world", 7)
    next_word = classifier.find_next_word_at_or_after_offset("hello, world", 7)
    assert prev_word is None
    assert next_word is None
