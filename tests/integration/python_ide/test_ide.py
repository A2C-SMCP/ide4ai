# filename: test_ide.py
# @Time    : 2024/5/13 14:39
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import pytest

from ai_ide.exceptions import IDEExecutionError


def test_initialization(python_ide):
    assert python_ide.root_dir
    assert python_ide.project_name == "ai_editor_for_test"
    assert "echo" in python_ide.cmd_white_list


def test_construct_action_valid(python_ide):
    action = {"category": "terminal", "action_name": "echo", "action_args": "Hello word"}
    ide_action = python_ide.construct_action(action)
    assert ide_action.action_name == "echo"


def test_construct_action_invalid(python_ide):
    action = {"category": "terminal", "action_name": "rm", "action_args": ["important_file"]}
    with pytest.raises(IDEExecutionError):
        python_ide.construct_action(action)


def test_step_terminal_command(python_ide):
    action = {"category": "terminal", "action_name": "echo", "action_args": "Test"}
    observation, reward, done, success, info = python_ide.step(action)
    # Assert the expected results based on your environment's logic
    assert "Test" in observation["obs"]
    assert done


def test_reset(python_ide):
    observation, info = python_ide.reset()
    assert observation.obs == "Reset IDE successfully"


def test_render(python_ide):
    render_output = python_ide.render()
    assert "IDE Content" in render_output
