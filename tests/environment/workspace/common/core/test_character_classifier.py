# filename: test_character_classifier.py
# @Time    : 2024/5/6 17:55
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import pytest

from ai_ide.environment.workspace.common.core.character_classifier import (
    CharacterClassifier,
)


def test_initialization():
    cc = CharacterClassifier(0)
    assert cc.default_value == 0
    assert all(x == 0 for x in cc.ascii_map), "ASCII map should be initialized with the default value"
    assert cc.map == {}, "Map should be empty upon initialization"


def test_set_and_get_ascii_values():
    cc = CharacterClassifier(0)
    cc.set(65, 255)  # Set ASCII value for 'A'
    assert cc.get(65) == 255, "Should get the set value for ASCII characters"


def test_set_and_get_non_ascii_values():
    cc = CharacterClassifier(0)
    cc.set(300, 12)  # Set value for a non-ASCII char code
    assert cc.get(300) == 12, "Should get the set value for non-ASCII characters"


def test_get_default_value():
    cc = CharacterClassifier(0)
    assert cc.get(500) == 0, "Should return default value for unset codes"


def test_clear_functionality():
    cc = CharacterClassifier(100)
    cc.set(65, 200)  # Set ASCII
    cc.set(300, 25)  # Set non-ASCII
    cc.clear()
    assert cc.get(65) == 100, "ASCII values should be reset to default after clear"
    assert cc.get(300) == 100, "Non-ASCII values should return default after clear"
    assert all(x == 100 for x in cc.ascii_map), "All ASCII map values should be reset to default"


def test_to_uint8_boundaries():
    cc = CharacterClassifier(0)
    assert cc.to_uint8(256) == 0, "256 should wrap around to 0"
    assert cc.to_uint8(257) == 1, "257 should wrap around to 1"
    assert cc.to_uint8(-1) == 255, "-1 should wrap around to 255"


@pytest.mark.parametrize("cinput,expected", [(0, 0), (255, 255), (256, 0), (257, 1), (-1, 255), (1023, 255)])
def test_to_uint8_parametrized(cinput, expected):
    assert CharacterClassifier.to_uint8(cinput) == expected, "to_uint8 should handle wrap-around correctly"


# To run tests, use the pytest framework:
# Install pytest if not already installed:
# pip install pytest
# Run tests:
# pytest path_to_test_file.py
