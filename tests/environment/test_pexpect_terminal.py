# filename: test_pexpect_terminal.py
# @Time    : 2025/10/28 18:26
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
PexpectTerminalEnv 测试用例 | Test cases for PexpectTerminalEnv

演示如何使用基于 pexpect 的终端环境,特别是虚拟环境激活功能
Demonstrates how to use pexpect-based terminal environment, especially virtual environment activation
"""

import os
import tempfile
from pathlib import Path

import pytest

from ide4ai.environment.terminal.base import EnvironmentArguments
from ide4ai.environment.terminal.pexpect_terminal_env import PexpectTerminalEnv


class TestPexpectTerminalEnv:
    """PexpectTerminalEnv 测试类 | Test class for PexpectTerminalEnv"""

    @pytest.fixture
    def temp_work_dir(self):
        """创建临时工作目录 | Create temporary working directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def basic_env(self, temp_work_dir):
        """创建基础测试环境 | Create basic test environment"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        white_list = ["echo", "pwd", "ls", "cat", "python", "python3", "uv", "poetry"]

        env = PexpectTerminalEnv(
            args=args,
            white_list=white_list,
            work_dir=temp_work_dir,
        )

        yield env
        env.close()

    def test_basic_command_execution(self, basic_env):
        """测试基本命令执行 | Test basic command execution"""
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["Hello, World!"],
        }

        obs, reward, done, success, _ = basic_env.step(action)

        assert success is True
        assert done is True
        assert reward == 100.0
        assert "Hello, World!" in obs["obs"]

    def test_persistent_session(self, basic_env):
        """测试持久会话 - 环境变量在命令间保持 | Test persistent session - env vars persist across commands"""
        # 设置环境变量 | Set environment variable
        action1 = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["export TEST_VAR=hello"],
        }
        basic_env.step(action1)

        # 使用 set_env_var 方法设置 | Use set_env_var method
        success = basic_env.set_env_var("TEST_VAR", "hello")
        assert success is True

        # 验证环境变量仍然存在 | Verify environment variable still exists
        value = basic_env.get_env_var("TEST_VAR")
        assert value == "hello"

    def test_change_directory(self, basic_env, temp_work_dir):
        """测试目录切换 | Test directory change"""
        # 创建子目录 | Create subdirectory
        subdir = Path(temp_work_dir) / "subdir"
        subdir.mkdir()

        # 切换目录 | Change directory
        output, success = basic_env.change_dir(path=str(subdir))

        assert success is True
        assert basic_env.current_dir == str(subdir.resolve())

    def test_command_not_in_whitelist(self, basic_env):
        """测试不在白名单中的命令 | Test command not in whitelist"""
        action = {
            "category": "terminal",
            "action_name": "rm",  # 不在白名单中 | Not in whitelist
            "action_args": ["-rf", "/"],
        }

        with pytest.raises(ValueError, match="not in white list"):
            basic_env.step(action)

    def test_render(self, basic_env):
        """测试渲染功能 | Test render functionality"""
        # 执行一些命令 | Execute some commands
        basic_env.step(
            {
                "category": "terminal",
                "action_name": "echo",
                "action_args": ["test1"],
            },
        )
        basic_env.step(
            {
                "category": "terminal",
                "action_name": "echo",
                "action_args": ["test2"],
            },
        )

        # 渲染 | Render
        output = basic_env.render()

        assert "test1" in output
        assert "test2" in output

    def test_reset(self, basic_env):
        """测试重置功能 | Test reset functionality"""
        # 执行命令 | Execute command
        basic_env.step(
            {
                "category": "terminal",
                "action_name": "echo",
                "action_args": ["before reset"],
            },
        )

        # 重置 | Reset
        obs, info = basic_env.reset()

        assert "Reset environment successfully" in obs.obs
        assert len(basic_env._command_history) == 0


class TestPexpectTerminalEnvWithVenv:
    """测试虚拟环境功能 | Test virtual environment functionality"""

    @pytest.fixture
    def temp_work_dir_with_venv(self):
        """创建带虚拟环境的临时工作目录 | Create temporary working directory with venv"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 注意: 这里只是演示,实际测试中可能需要真实创建虚拟环境
            # Note: This is just a demo, actual tests may need to create real venv
            yield tmpdir

    def test_init_with_venv_command(self, temp_work_dir_with_venv):
        """测试使用虚拟环境初始化命令 | Test initialization with venv command"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        white_list = ["python", "python3", "pip", "which"]

        # 这里演示如何传入虚拟环境激活命令
        # This demonstrates how to pass venv activation command
        # 实际使用时可能是: "source .venv/bin/activate" 或 "uv venv activate"
        # In actual use it might be: "source .venv/bin/activate" or "uv venv activate"

        env = PexpectTerminalEnv(
            args=args,
            white_list=white_list,
            work_dir=temp_work_dir_with_venv,
            active_venv_cmd=None,  # 如果有虚拟环境,这里传入激活命令 | Pass activation command if venv exists
        )

        # 验证环境已初始化 | Verify environment is initialized
        assert env.shell.isalive()

        env.close()

    @pytest.mark.skipif(
        not os.path.exists("/usr/bin/python3"),
        reason="Python3 not available",
    )
    def test_python_version_in_venv(self, temp_work_dir_with_venv):
        """测试在虚拟环境中检查 Python 版本 | Test checking Python version in venv"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        white_list = ["python", "python3", "which"]

        env = PexpectTerminalEnv(
            args=args,
            white_list=white_list,
            work_dir=temp_work_dir_with_venv,
        )

        # 检查 Python 版本 | Check Python version
        action = {
            "category": "terminal",
            "action_name": "python3",
            "action_args": ["--version"],
        }

        obs, reward, done, success, _ = env.step(action)

        assert success is True
        assert "Python" in obs["obs"]

        env.close()


class TestPexpectTerminalEnvEdgeCases:
    """边缘情况测试 | Edge case tests"""

    def test_invalid_work_dir(self):
        """测试无效工作目录 | Test invalid working directory"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        white_list = ["echo"]

        with pytest.raises(ValueError, match="does not exist"):
            PexpectTerminalEnv(
                args=args,
                white_list=white_list,
                work_dir="/nonexistent/directory",
            )

    def test_command_timeout(self, tmp_path):
        """测试命令超时 | Test command timeout"""
        args = EnvironmentArguments(image_name="local", timeout=2)  # 短超时 | Short timeout
        white_list = ["sleep"]

        env = PexpectTerminalEnv(
            args=args,
            white_list=white_list,
            work_dir=str(tmp_path),
        )

        # 执行一个会超时的命令 | Execute a command that will timeout
        action = {
            "category": "terminal",
            "action_name": "sleep",
            "action_args": ["10"],  # 睡眠 10 秒,但超时是 2 秒 | Sleep 10s but timeout is 2s
        }

        obs, reward, done, success, _ = env.step(action)

        assert success is False
        assert "timeout" in obs["obs"].lower()

        env.close()

    def test_close_already_closed(self, tmp_path):
        """测试关闭已关闭的环境 | Test closing already closed environment"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        white_list = ["echo"]

        env = PexpectTerminalEnv(
            args=args,
            white_list=white_list,
            work_dir=str(tmp_path),
        )

        env.close()

        # 再次关闭不应该报错 | Closing again should not raise error
        env.close()

        # 但是使用已关闭的环境应该报错 | But using closed environment should raise error
        with pytest.raises(ValueError, match="closed"):
            env.step(
                {
                    "category": "terminal",
                    "action_name": "echo",
                    "action_args": ["test"],
                },
            )


if __name__ == "__main__":
    # 运行测试 | Run tests
    # pytest tests/environment/test_pexpect_terminal.py -v
    pytest.main([__file__, "-v"])
