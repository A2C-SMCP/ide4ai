# filename: test_schema.py
# @Time    : 2024/4/16 19:29
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import json

import pytest
from pydantic import ValidationError

from ide4ai.environment.workspace.schema import Position, Range
from ide4ai.schema import ACTION_NAME_MAP, IDEAction, IDEObs


def test_ide_obs_created_at() -> None:
    """
    Test the IDE observation created_at field.
    Returns:

    """
    with pytest.raises(ValidationError):
        IDEObs(created_at="test")
    obs = IDEObs(created_at="2024-04-16 19:29:00")
    assert obs.created_at == "2024-04-16 19:29:00"


def test_position_validate() -> None:
    pos = Position(-1, -1)
    assert pos


def test_range_validate() -> None:
    """
    Test the IDE observation obs field.
    Returns:

    """
    start_pos = Position(-1, -1)
    end_pos = Position(1, 1)
    with pytest.raises(ValidationError):
        Range(start_position=start_pos, end_position=end_pos)
    start_pos = Position(1, 1)
    t_range = Range(start_position=start_pos, end_position=end_pos)
    assert t_range


def test_ide_action_initialization():
    # Test with integer mappings
    action1 = IDEAction(category=0, action_name=0)  # type: ignore
    assert action1.category == "terminal"
    assert action1.action_name == ACTION_NAME_MAP[0]

    # Test with string inputs
    action2 = IDEAction(category="workspace", action_name="save_file")
    assert action2.category == "workspace"
    assert action2.action_name == "save_file"

    # Test for exceptions with invalid inputs
    with pytest.raises(ValidationError):
        IDEAction(category="invalid_category", action_name="nonexistent_action")  # type: ignore

    with pytest.raises(KeyError):
        IDEAction(category=999, action_name=999)  # type: ignore


def test_ide_action_model_validation():
    action_dict = {
        "category": 0,
        "action_name": 0,
        "action_args": json.dumps({"key": "value"}),
    }
    action = IDEAction.model_validate(action_dict)
    assert action.category == "terminal"
    assert action.action_name == ACTION_NAME_MAP[0]
    assert action.action_args == {"key": "value"}
