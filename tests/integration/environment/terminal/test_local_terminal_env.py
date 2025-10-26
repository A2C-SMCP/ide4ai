# filename: local_terminal_env.py
# @Time    : 2024/5/13 10:40
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import os
import tempfile
import time
from pathlib import Path

import pytest
from tfrobot.drive.tool.ides.environment.terminal.base import EnvironmentArguments
from tfrobot.drive.tool.ides.environment.terminal.local_terminal_env import TerminalEnv


# Example test setup
@pytest.fixture
def temp_work_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture
def terminal_env(temp_work_dir):
    args = EnvironmentArguments(
        timeout=10, image_name="test"
    )  # Assuming EnvironmentArguments class exists with a timeout attribute
    white_list = ["echo", "ls"]  # Safe commands
    return TerminalEnv(args, white_list, temp_work_dir)


# Test initialization
def test_initialization(temp_work_dir):
    args = EnvironmentArguments(timeout=10, image_name="test")
    white_list = ["echo", "ls"]
    env = TerminalEnv(args, white_list, temp_work_dir)
    assert env.work_dir == temp_work_dir
    assert env.current_dir == temp_work_dir
    assert set(env.white_list) == {"echo", "ls"}


# Test initialization failure with invalid directory
def test_invalid_directory():
    args = EnvironmentArguments(timeout=10, image_name="test")
    white_list = ["echo", "ls"]
    with pytest.raises(ValueError):
        TerminalEnv(args, white_list, "/invalid/dir")


# Test action construction and white list enforcement
def test_construct_action_whitelist(terminal_env):
    valid_action = {"category": "terminal", "action_name": "echo", "action_args": "hello world"}
    assert terminal_env.construct_action(valid_action)

    invalid_action = {"category": "terminal", "action_name": "rm", "action_args": "-rf /"}
    with pytest.raises(ValueError):
        terminal_env.construct_action(invalid_action)

    invalid_action_2 = {"category": "workspace", "action_name": "ls", "action_args": "-la"}
    with pytest.raises(ValueError):
        terminal_env.construct_action(invalid_action_2)


# Test command execution
@pytest.mark.parametrize("echo_range", range(10))
def test_command_execution(terminal_env, echo_range):
    # Prepare the action dictionary
    action = {"category": "terminal", "action_name": "echo", "action_args": f"hello world{echo_range}"}

    # Execute the step function which should internally call run to execute the echo command
    observation, reward, done, success, info = terminal_env.step(action)

    # The command 'echo' with 'hello world' should produce the output 'hello world\n'
    # Here we check if the output matches what we expect
    assert (
        observation["obs"] == f"hello world{echo_range}\n"
        or observation["obs"] == f"hello world{echo_range}\nCommand Finished\n"
    ), "The observation output is not as expected."

    # Additional checks to confirm that the action was handled correctly
    assert success is True, "The action should be successful."
    assert done is True, "The action should complete."
    assert reward == 100.0, "The expected reward should be 100.0."


def test_command_execute_failed(terminal_env):
    action = {"category": "terminal", "action_name": "ls", "action_args": "/22"}
    observation, reward, done, success, info = terminal_env.step(action)
    assert "No such file or directory" in observation["obs"]
    assert not success
    assert done


def test_command_execution_ls(terminal_env):
    with tempfile.TemporaryDirectory() as tmp_dir:
        new_file = tmp_dir + "/test_for_u.py"
        with open(new_file, "w") as f:
            f.write("print('hello world')")
        # Prepare the action dictionary
        action = {"category": "terminal", "action_name": "ls", "action_args": f"{tmp_dir}"}

        # Execute the step function which should internally call run to execute the echo command
        observation, reward, done, success, info = terminal_env.step(action)

        # The command 'echo' with 'hello world' should produce the output 'hello world\n'
        # Here we check if the output matches what we expect
        assert "test_for_u.py" in observation["obs"], "The observation output is not as expected."

        # Additional checks to confirm that the action was handled correctly
        assert success is True, "The action should be successful."
        assert done is True, "The action should complete."
        assert reward == 100.0, "The expected reward should be 100.0."


def test_run_method(terminal_env):
    # Run the echo command
    pid = terminal_env.run(cmd="echo", args=["hello", "world"])

    # Check if the process ID is a valid integer
    assert isinstance(pid, int), "The process ID should be an integer."

    # Check if the process ID is greater than 0
    assert pid > 0, "The process ID should be greater than 0."

    # sleep 1s to make sure the process is finished
    time.sleep(0.1)
    res, done, success = terminal_env.get_proc_res(pid=pid)
    assert done
    assert "hello world" in res
    assert success


def test_reset_method(terminal_env):
    # Change the current directory to a different directory and then reset
    new_path = os.path.join(terminal_env.work_dir, "subdir")
    os.mkdir(new_path)
    terminal_env.change_dir(path=new_path)
    assert os.path.realpath(terminal_env.current_dir) == os.path.realpath(new_path), (
        "The current directory should have been changed to the new path."
    )

    # Perform the reset operation
    observation, info = terminal_env.reset()
    assert os.path.realpath(terminal_env.current_dir) == os.path.realpath(terminal_env.work_dir), (
        "After reset, the current directory should be the work directory."
    )
    assert observation.obs == "Reset environment", "Observation message should confirm the environment reset."


def test_close_method(terminal_env):
    # Run a command to ensure at least one subprocess is active
    terminal_env.run(cmd="sleep", args=["1"])
    assert len(terminal_env.procs) > 0, "There should be at least one process running."

    # Close the environment
    terminal_env.close()
    assert terminal_env._is_closed, "The environment should be marked as closed."
    for proc in terminal_env.procs.values():
        assert proc.poll() is not None, "All subprocesses should be terminated."


def test_change_dir_valid_subdirectory(terminal_env, temp_work_dir):
    # Create a valid subdirectory in the working directory
    valid_subdir = os.path.join(temp_work_dir, "valid_subdir")
    os.makedirs(valid_subdir)
    terminal_env.change_dir(path=valid_subdir)
    assert os.path.realpath(terminal_env.current_dir) == os.path.realpath(valid_subdir), (
        "The current directory should be the new valid subdirectory."
    )


def test_change_dir_invalid_subdirectory(terminal_env):
    # Attempt to change to an invalid subdirectory
    invalid_subdir = "/invalid/path"
    with pytest.raises(ValueError):
        terminal_env.change_dir(path=invalid_subdir)
    assert terminal_env.current_dir == terminal_env.work_dir, (
        "The current directory should remain the original work directory after a failed change."
    )


def test_change_dir_to_nonexistent_directory(terminal_env):
    # Attempt to change to a non-existent directory
    non_existent_dir = "/this/directory/does/not/exist"
    with pytest.raises(ValueError) as excinfo:
        terminal_env.change_dir(path=non_existent_dir)
    assert "Invalid path" in str(excinfo.value), "Should raise an error for a non-existent directory"


def test_change_dir_to_non_subdirectory(terminal_env, temp_work_dir):
    # Attempt to change to a directory that is not a subdirectory of the work directory
    # Create a directory at the same level as temp_work_dir
    non_subdir = str(Path(temp_work_dir).parent / "another_directory")
    os.makedirs(non_subdir, exist_ok=True)
    with pytest.raises(ValueError) as excinfo:
        terminal_env.change_dir(path=non_subdir)
    assert "not a subdirectory of the working directory" in str(excinfo.value), (
        "Should raise an error for non-subdirectories"
    )


def test_change_dir_to_different_drive(terminal_env):
    # This test is more relevant on Windows where drives can be clearly distinguished
    # For Unix-like systems, this might correspond to changing to a mounted directory that's not part of the current
    # filesystem tree. This test might need to be adjusted based on your specific OS and filesystem structure
    different_drive_path = "/mnt/external_drive"  # Example path for Unix-like systems
    if os.path.exists(different_drive_path):
        with pytest.raises(ValueError) as excinfo:
            terminal_env.change_dir(path=different_drive_path)
        assert "not a subdirectory of the working directory" in str(excinfo.value), (
            "Should raise an error for directories on different drives"
        )
