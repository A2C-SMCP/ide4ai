# filename: test_python_ide_venv.py
# @Time    : 2025/10/28 18:54
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 PythonIDE 的虚拟环境功能 | Test PythonIDE virtual environment functionality
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from ide4ai.environment.terminal import PexpectTerminalEnv
from ide4ai.python_ide.ide import PythonIDE


class TestPythonIDEVenv:
    """测试 PythonIDE 虚拟环境功能 | Test PythonIDE virtual environment functionality"""

    @pytest.fixture
    def temp_project_dir(self):
        """创建临时项目目录 | Create temporary project directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_python_ide_without_venv(self, temp_project_dir):
        """测试不使用虚拟环境的 PythonIDE | Test PythonIDE without virtual environment"""
        ide = PythonIDE(
            cmd_white_list=["echo", "python", "python3"],
            root_dir=temp_project_dir,
            project_name="test_project",
            cmd_time_out=10,
        )

        # 验证终端可以正常工作 | Verify terminal works normally
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["Hello without venv"],
        }

        obs, reward, done, success, _ = ide.step(action)

        assert success is True
        assert "Hello without venv" in obs["obs"]
        assert ide.terminal.venv_activated is False
        assert ide.terminal.venv_activation_error is None

        ide.close()

    def test_python_ide_with_valid_venv(self, temp_project_dir):
        """测试使用有效虚拟环境的 PythonIDE | Test PythonIDE with valid virtual environment"""
        # 创建虚拟环境 | Create virtual environment
        venv_path = Path(temp_project_dir) / ".venv"

        result = subprocess.run(
            ["python3", "-m", "venv", str(venv_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip(f"无法创建虚拟环境 | Cannot create venv: {result.stderr}")

        # 使用虚拟环境初始化 IDE | Initialize IDE with virtual environment
        ide = PythonIDE(
            cmd_white_list=["echo", "python", "python3", "which"],
            root_dir=temp_project_dir,
            project_name="test_project",
            cmd_time_out=10,
            active_venv_cmd=f"source {venv_path}/bin/activate",
        )

        # 验证虚拟环境已激活 | Verify virtual environment is activated
        assert isinstance(ide.terminal, PexpectTerminalEnv)
        assert ide.terminal.venv_activated is True
        assert ide.terminal.venv_activation_error is None

        # 检查 Python 路径 | Check Python path
        action = {
            "category": "terminal",
            "action_name": "which",
            "action_args": ["python"],
        }

        obs, reward, done, success, _ = ide.step(action)

        assert success is True
        # Python 路径应该在虚拟环境中 | Python path should be in venv
        assert ".venv" in obs["obs"] or "venv" in obs["obs"]

        ide.close()

    def test_python_ide_with_invalid_venv_command(self, temp_project_dir):
        """测试使用无效虚拟环境命令的 PythonIDE | Test PythonIDE with invalid venv command"""
        # 使用不存在的虚拟环境路径 | Use non-existent venv path
        ide = PythonIDE(
            cmd_white_list=["echo", "python"],
            root_dir=temp_project_dir,
            project_name="test_project",
            cmd_time_out=10,
            active_venv_cmd="source /nonexistent/venv/bin/activate",
        )

        # 虚拟环境激活应该失败,但 IDE 应该正常工作 | Venv activation should fail, but IDE should work
        assert ide.terminal.venv_activated is False
        assert ide.terminal.venv_activation_error is not None

        # 终端应该仍然可以执行命令 | Terminal should still be able to execute commands
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["Hello even with failed venv"],
        }

        obs, reward, done, success, _ = ide.step(action)

        assert success is True
        assert "Hello even with failed venv" in obs["obs"]

        ide.close()

    def test_python_ide_with_wrong_venv_syntax(self, temp_project_dir):
        """测试使用错误语法的虚拟环境命令 | Test PythonIDE with wrong venv command syntax"""
        # 使用错误的命令语法 | Use wrong command syntax
        ide = PythonIDE(
            cmd_white_list=["echo", "ls"],
            root_dir=temp_project_dir,
            project_name="test_project",
            cmd_time_out=10,
            active_venv_cmd="this is not a valid command",
        )

        # 虚拟环境激活应该失败 | Venv activation should fail
        assert ide.terminal.venv_activated is False

        # 但终端应该仍然可用 | But terminal should still be usable
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["Terminal still works"],
        }

        obs, reward, done, success, _ = ide.step(action)

        assert success is True
        assert "Terminal still works" in obs["obs"]

        ide.close()

    def test_python_ide_venv_persistent_across_commands(self, temp_project_dir):
        """测试虚拟环境在多个命令间保持激活 | Test venv stays activated across commands"""
        # 创建虚拟环境 | Create virtual environment
        venv_path = Path(temp_project_dir) / ".venv"

        result = subprocess.run(
            ["python3", "-m", "venv", str(venv_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip(f"无法创建虚拟环境 | Cannot create venv: {result.stderr}")

        ide = PythonIDE(
            cmd_white_list=["echo", "python3", "which"],
            root_dir=temp_project_dir,
            project_name="test_project",
            cmd_time_out=10,
            active_venv_cmd=f"source {venv_path}/bin/activate",
        )

        # 执行多个命令 | Execute multiple commands
        for _ in range(3):
            action = {
                "category": "terminal",
                "action_name": "which",
                "action_args": ["python"],
            }

            obs, reward, done, success, _ = ide.step(action)

            assert success is True
            # 每次都应该在虚拟环境中 | Should be in venv every time
            assert ".venv" in obs["obs"] or "venv" in obs["obs"]

        ide.close()

    def test_python_ide_reset_with_venv(self, temp_project_dir):
        """测试重置后虚拟环境仍然激活 | Test venv remains activated after reset"""
        # 创建虚拟环境 | Create virtual environment
        venv_path = Path(temp_project_dir) / ".venv"

        result = subprocess.run(
            ["python3", "-m", "venv", str(venv_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip(f"无法创建虚拟环境 | Cannot create venv: {result.stderr}")

        ide = PythonIDE(
            cmd_white_list=["echo", "which"],
            root_dir=temp_project_dir,
            project_name="test_project",
            cmd_time_out=10,
            active_venv_cmd=f"source {venv_path}/bin/activate",
        )

        # 执行命令 | Execute command
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["Before reset"],
        }
        ide.step(action)

        # 重置 IDE | Reset IDE
        obs, info = ide.reset()

        assert "Reset IDE successfully" in obs.obs

        # 虚拟环境应该仍然激活 | Venv should still be activated
        assert ide.terminal.venv_activated is True

        # 执行命令验证 | Execute command to verify
        action = {
            "category": "terminal",
            "action_name": "which",
            "action_args": ["python"],
        }

        obs_dict, reward, done, success, _ = ide.step(action)

        assert success is True
        assert ".venv" in obs_dict["obs"] or "venv" in obs_dict["obs"]

        ide.close()

    def test_python_ide_venv_status_accessible(self, temp_project_dir):
        """测试可以访问虚拟环境状态 | Test venv status is accessible"""
        ide = PythonIDE(
            cmd_white_list=["echo"],
            root_dir=temp_project_dir,
            project_name="test_project",
            cmd_time_out=10,
            active_venv_cmd="source /nonexistent/venv/bin/activate",
        )

        # 应该可以访问虚拟环境状态 | Should be able to access venv status
        assert hasattr(ide.terminal, "venv_activated")
        assert hasattr(ide.terminal, "venv_activation_error")
        assert hasattr(ide.terminal, "active_venv_cmd")

        assert ide.terminal.venv_activated is False
        assert ide.terminal.venv_activation_error is not None
        assert ide.terminal.active_venv_cmd == "source /nonexistent/venv/bin/activate"

        ide.close()
