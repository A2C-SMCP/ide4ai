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
import time
from pathlib import Path

import pytest

from ide4ai.environment.terminal.base import EnvironmentArguments
from ide4ai.environment.terminal.command_filter import CommandFilterConfig
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
        cmd_filter = CommandFilterConfig.from_white_list(
            ["echo", "pwd", "ls", "cat", "python", "python3", "uv", "poetry"]
        )

        env = PexpectTerminalEnv(
            args=args,
            work_dir=temp_work_dir,
            cmd_filter=cmd_filter,
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

        with pytest.raises(ValueError, match="not in whitelist"):
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
        cmd_filter = CommandFilterConfig.from_white_list(["python", "python3", "pip", "which"])

        # 这里演示如何传入虚拟环境激活命令
        # This demonstrates how to pass venv activation command
        # 实际使用时可能是: "source .venv/bin/activate" 或 "uv venv activate"
        # In actual use it might be: "source .venv/bin/activate" or "uv venv activate"

        env = PexpectTerminalEnv(
            args=args,
            work_dir=temp_work_dir_with_venv,
            cmd_filter=cmd_filter,
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
        cmd_filter = CommandFilterConfig.from_white_list(["python", "python3", "which"])

        env = PexpectTerminalEnv(
            args=args,
            work_dir=temp_work_dir_with_venv,
            cmd_filter=cmd_filter,
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
        cmd_filter = CommandFilterConfig.from_white_list(["echo"])

        with pytest.raises(ValueError, match="does not exist"):
            PexpectTerminalEnv(
                args=args,
                work_dir="/nonexistent/directory",
                cmd_filter=cmd_filter,
            )

    def test_command_timeout(self, tmp_path):
        """测试命令超时 | Test command timeout"""
        args = EnvironmentArguments(image_name="local", timeout=2)  # 短超时 | Short timeout
        cmd_filter = CommandFilterConfig.from_white_list(["sleep"])

        env = PexpectTerminalEnv(
            args=args,
            work_dir=str(tmp_path),
            cmd_filter=cmd_filter,
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
        cmd_filter = CommandFilterConfig.from_white_list(["echo"])

        env = PexpectTerminalEnv(
            args=args,
            work_dir=str(tmp_path),
            cmd_filter=cmd_filter,
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


class TestCommandFilterConfig:
    """测试黑白名单功能 | Test blacklist/whitelist functionality"""

    def test_whitelist_mode(self, tmp_path):
        """测试白名单模式 | Test whitelist mode"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        cmd_filter = CommandFilterConfig.from_white_list(["echo", "ls"])

        env = PexpectTerminalEnv(
            args=args,
            work_dir=str(tmp_path),
            cmd_filter=cmd_filter,
        )

        # 白名单中的命令应该成功 | Whitelisted command should succeed
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["test"],
        }
        obs, reward, done, success, _ = env.step(action)
        assert success is True

        # 不在白名单中的命令应该失败 | Non-whitelisted command should fail
        action = {
            "category": "terminal",
            "action_name": "pwd",
            "action_args": [],
        }
        with pytest.raises(ValueError, match="not in whitelist"):
            env.step(action)

        env.close()

    def test_blacklist_mode(self, tmp_path):
        """测试黑名单模式 | Test blacklist mode"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        # 仅使用黑名单,不使用白名单 | Only use blacklist, no whitelist
        cmd_filter = CommandFilterConfig.allow_all_except(["rm", "dd"])

        env = PexpectTerminalEnv(
            args=args,
            work_dir=str(tmp_path),
            cmd_filter=cmd_filter,
        )

        # 不在黑名单中的命令应该成功 | Non-blacklisted command should succeed
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["test"],
        }
        obs, reward, done, success, _ = env.step(action)
        assert success is True

        # 在黑名单中的命令应该失败 | Blacklisted command should fail
        action = {
            "category": "terminal",
            "action_name": "rm",
            "action_args": ["-rf", "/"],
        }
        with pytest.raises(ValueError, match="in blacklist"):
            env.step(action)

        env.close()

    def test_default_blacklist(self, tmp_path):
        """测试默认黑名单 | Test default blacklist"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        # 不指定任何过滤器,使用默认黑名单 | No filter specified, use default blacklist
        env = PexpectTerminalEnv(
            args=args,
            work_dir=str(tmp_path),
        )

        # 普通命令应该成功 | Normal command should succeed
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["test"],
        }
        obs, reward, done, success, _ = env.step(action)
        assert success is True

        # 默认黑名单中的危险命令应该失败 | Dangerous command in default blacklist should fail
        action = {
            "category": "terminal",
            "action_name": "rm",
            "action_args": ["-rf", "/"],
        }
        with pytest.raises(ValueError, match="in blacklist"):
            env.step(action)

        env.close()

    def test_allow_all_mode(self, tmp_path):
        """测试允许所有命令模式(不推荐) | Test allow all mode (not recommended)"""
        args = EnvironmentArguments(image_name="local", timeout=10)
        cmd_filter = CommandFilterConfig.allow_all()

        env = PexpectTerminalEnv(
            args=args,
            work_dir=str(tmp_path),
            cmd_filter=cmd_filter,
        )

        # 任何命令都应该被允许(但可能执行失败) | Any command should be allowed (but may fail to execute)
        action = {
            "category": "terminal",
            "action_name": "echo",
            "action_args": ["test"],
        }
        obs, reward, done, success, _ = env.step(action)
        assert success is True

        env.close()


class TestPexpectTerminalRecovery:
    """超时恢复测试 | Timeout recovery tests

    复现 GitHub Issue #12：一条不返回提示符的交互式 / 前台命令(如 cat 等 stdin、
    或无视 SIGINT 的进程)超时后，持久 shell 被永久毒死，后续每条命令都超时。
    Reproduces GitHub Issue #12: after one interactive/foreground command that
    never returns to the prompt times out, the persistent shell is permanently
    poisoned and every subsequent command also times out.
    """

    @pytest.fixture
    def short_timeout_env(self, tmp_path):
        """超时设置较短的环境，加速复现 | Env with short timeout to speed up reproduction"""
        args = EnvironmentArguments(image_name="local", timeout=3)
        cmd_filter = CommandFilterConfig.from_white_list(["echo", "cat", "python3"])
        env = PexpectTerminalEnv(args=args, work_dir=str(tmp_path), cmd_filter=cmd_filter)
        yield env
        env.close()

    def test_recover_after_cat_blocks_on_stdin(self, short_timeout_env):
        """cat(等 stdin)超时后，后续 echo 必须恢复 | echo must recover after cat times out"""
        env = short_timeout_env

        # 1. echo 正常 | echo works
        obs, _, _, success, _ = env.step(
            {"category": "terminal", "action_name": "echo", "action_args": ["ok1"]},
        )
        assert success is True
        assert "ok1" in obs["obs"]

        # 2. cat 无参等待 stdin → 超时 | cat waits on stdin → times out
        _, _, _, success, info = env.step(
            {"category": "terminal", "action_name": "cat", "action_args": []},
        )
        assert success is False
        assert "timeout" in info["output"].lower()

        # 3. 关键断言：之后的 echo 必须恢复，而不是被永久毒死
        #    Key assertion: the next echo must recover, not be permanently poisoned
        obs, _, _, success, _ = env.step(
            {"category": "terminal", "action_name": "echo", "action_args": ["ok2"]},
        )
        assert success is True, "终端在交互式命令超时后未能自我恢复 | terminal failed to self-recover after timeout"
        assert "ok2" in obs["obs"]

    def test_recover_after_sigint_immune_process(self, short_timeout_env, mocker):
        """无视 SIGINT 的前台进程超时后，仍须通过重建 shell 恢复
        After a SIGINT-immune foreground process times out, recovery must still
        succeed (via hard shell rebuild)."""
        env = short_timeout_env
        # 监视硬重建路径，确保确实走了 _rebuild_shell（而非软恢复意外成功掩盖回归）
        # Spy on the hard-rebuild path to assert it actually fired (not masked by soft recovery).
        rebuild_spy = mocker.spy(env, "_rebuild_shell")

        # 启动一个忽略 SIGINT 并长睡的进程，模拟 vim/top/ssh 等无视 Ctrl-C 的程序
        # Spawn a process that ignores SIGINT and sleeps long, simulating vim/top/ssh
        # 内联代码用单引号包裹成单个 shell 词，避免被空格/分号拆解
        # Wrap the inline code in single quotes so it stays one shell word
        code = "import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);time.sleep(300)"
        _, _, _, success, info = env.step(
            {
                "category": "terminal",
                "action_name": "python3",
                "action_args": ["-c", f"'{code}'"],
            },
        )
        assert success is False
        assert "timeout" in info["output"].lower()
        # 软恢复（Ctrl-C）对无视 SIGINT 的进程必然失败 → 必须落到硬重建
        # Soft recovery (Ctrl-C) must fail for a SIGINT-immune process → hard rebuild path
        assert rebuild_spy.call_count >= 1, "无视 SIGINT 的进程超时未触发硬重建 | hard rebuild path not taken"

        # 之后的 echo 必须恢复 | the next echo must recover
        obs, _, _, success, _ = env.step(
            {"category": "terminal", "action_name": "echo", "action_args": ["recovered"]},
        )
        assert success is True, (
            "无视 SIGINT 的进程超时后终端未恢复 | terminal failed to recover after SIGINT-immune timeout"
        )
        assert "recovered" in obs["obs"]

    def test_per_call_timeout_overrides_env_default(self, tmp_path):
        """per-call timeout 必须真正生效，而非始终用环境默认
        Per-call timeout must actually take effect rather than always using env default.

        复现 Issue #12 次要 #1：请求 timeout 较小却等满 --cmd-timeout。
        """
        import time

        # 环境默认 30s，但本次命令注入 2s 的 per-call 超时
        # Env default is 30s, but this command injects a 2s per-call timeout.
        args = EnvironmentArguments(image_name="local", timeout=30)
        cmd_filter = CommandFilterConfig.from_white_list(["echo", "cat"])
        env = PexpectTerminalEnv(args=args, work_dir=str(tmp_path), cmd_filter=cmd_filter)
        try:
            start = time.monotonic()
            _, _, _, success, info = env.step(
                {
                    "category": "terminal",
                    "action_name": "cat",
                    "action_args": [],
                    "timeout": 2,  # per-call 覆盖：2s 而非 30s | per-call override
                },
            )
            elapsed = time.monotonic() - start

            assert success is False
            # 主断言：文案直证 per-call 2s 生效（而非 30s 默认）
            # Primary assertion: message proves the 2s per-call value took effect (not 30s default).
            assert "2 seconds" in info["output"]
            # 辅助时间断言放宽，避免与恢复链路耗时（Ctrl-C/重建）隐式耦合导致 CI flaky
            # Loose time bound: avoid coupling to recovery-chain latency; still well below 30s default.
            assert elapsed < 25, f"per-call timeout 未生效，等待 {elapsed:.1f}s | per-call timeout ignored"

            # 恢复后续命令仍可用 | subsequent command still works after recovery
            obs, _, _, success, _ = env.step(
                {"category": "terminal", "action_name": "echo", "action_args": ["after"]},
            )
            assert success is True
            assert "after" in obs["obs"]
        finally:
            env.close()


class TestPexpectTerminalMultiline:
    """多行 / heredoc 命令测试 | Multi-line / heredoc command tests

    复现 GitHub Issue #15：持久 shell 用单次 `sendline` + 匹配首个提示符的协议
    隐含「命令是单行」假设。多行命令的每一行都会触发一个提示符，首个提示符匹配后
    剩余行 + 后续提示符残留在 pty 缓冲，导致：多行命令被截断、heredoc 卡满超时、
    退出码探针串位，会话被毒化（后续命令也读到串位数据）。

    Reproduces GitHub Issue #15: the persistent shell protocol (single `sendline`
    matching the first prompt) silently assumes single-line commands. Multi-line /
    heredoc commands desync the prompt-matching protocol, truncating output, hanging
    on heredocs, and poisoning the session for subsequent commands.
    """

    @pytest.fixture
    def env(self, tmp_path):
        """超时较短的环境，heredoc 若卡住能快速暴露 | short timeout so a hang surfaces fast"""
        args = EnvironmentArguments(image_name="local", timeout=6)
        cmd_filter = CommandFilterConfig.from_white_list(["echo", "cat", "python3"])
        env = PexpectTerminalEnv(args=args, work_dir=str(tmp_path), cmd_filter=cmd_filter)
        yield env
        env.close()

    def test_multiline_command_executes_all_lines(self, env):
        """多行命令的每一行都应执行，输出不丢失 | every line of a multi-line command runs"""
        result = env._execute_command("echo a\necho b")

        assert result.success is True, f"多行命令应成功 | multi-line command should succeed: {result.output!r}"
        assert result.exit_code == 0
        assert "a" in result.output and "b" in result.output, (
            f"第二行丢失（协议只支持单行）| second line lost: {result.output!r}"
        )

    def test_heredoc_command_executes_without_hang(self, env):
        """heredoc 应正确执行并及时返回，而非卡满超时 | heredoc runs and returns promptly"""
        start = time.monotonic()
        result = env._execute_command(
            "python3 << 'PYEOF'\nprint('hi')\nPYEOF",
            timeout=6,
        )
        elapsed = time.monotonic() - start

        assert result.success is True, f"heredoc 应成功 | heredoc should succeed: {result.output!r}"
        assert "hi" in result.output, f"heredoc 输出缺失 | heredoc output missing: {result.output!r}"
        # 一个 print('hi') 级别的 heredoc 必须远快于 timeout（不卡满）
        # A trivial heredoc must finish far below the timeout (no full-timeout hang).
        assert elapsed < 5, f"heredoc 卡满超时 | heredoc hung until timeout: {elapsed:.1f}s"

    def test_session_not_desynced_after_multiline(self, env):
        """多行命令后会话不应被毒化，后续单行命令输出仍正确 | no desync poisoning"""
        # 先跑一个会触发 desync 的 heredoc | run a heredoc that would desync the old protocol
        env._execute_command("python3 << 'PYEOF'\nprint('warmup')\nPYEOF", timeout=6)

        # 关键断言：之后的单行命令输出干净、退出码正确，而非读到 stale RC blob
        # Key assertion: the next single-line command is clean, not a stale RC blob.
        result = env._execute_command("echo recovered")
        assert result.success is True
        assert result.exit_code == 0
        assert result.output.strip() == "recovered", (
            f"会话被多行命令毒化 | session poisoned by prior multi-line command: {result.output!r}"
        )

    def test_multiline_preserves_session_state(self, env):
        """多行命令在当前 shell 执行，cd/export 等状态须持久化 | state persists in current shell"""
        # 多行命令内导出变量 | export a var inside a multi-line command
        result = env._execute_command("export ISSUE15_VAR=persisted\necho done")
        assert result.success is True

        # 后续命令应能读到该变量（证明在当前 shell 而非子 shell 执行）
        # A later command must see it (proving execution in the current shell, not a subshell).
        follow = env._execute_command("echo $ISSUE15_VAR")
        assert follow.success is True
        assert "persisted" in follow.output, (
            f"多行命令在子 shell 执行，状态丢失 | state lost (ran in a subshell): {follow.output!r}"
        )

    def test_multiline_failing_command_propagates_exit_code(self, env):
        """多行命令末行失败时退出码须如实传播 | failing last line propagates non-zero exit code"""
        # `eval` 包裹后 `$?` 取最后一行退出码——末行 false 必须得到非零退出码 / success False
        # After eval-wrapping, `$?` is the last line's exit code: a trailing `false` must be non-zero.
        result = env._execute_command("echo ok\nfalse")
        assert result.success is False, f"末行失败应判定失败 | failing last line should fail: {result.output!r}"
        assert result.exit_code != 0, f"退出码应非零 | exit code should be non-zero: {result.exit_code}"

    def test_to_single_line_fold_policy(self, env):
        """`_to_single_line` 折叠策略：仅多行命令被包裹 | only multi-line commands get wrapped"""
        # 单行命令原样透传（零回归）| single-line passes through unchanged
        assert env._to_single_line("echo hi") == "echo hi"
        # 仅含孤立 \r（无 \n）本就是单物理行，不应被包裹（W3：避免 eval $'\r' 退化）
        # A lone-CR command (no \n) is still one physical line — must NOT be wrapped (W3).
        assert env._to_single_line("echo hi\r") == "echo hi\r"
        # 含 \n 的多行命令被折叠成单条 eval+base64 物理行
        # Multi-line (\n) command is folded into one eval+base64 physical line.
        wrapped = env._to_single_line("echo a\necho b")
        assert wrapped.startswith("eval ") and "base64 --decode" in wrapped
        assert "\n" not in wrapped, "折叠结果必须是单物理行 | folded result must be one physical line"


class TestPexpectTerminalPromptDesync:
    """提示符哨兵失同步测试 | Prompt-sentinel desync tests (Jira AS-35)

    复现 AS-35：旧实现 PS1 固定为 `PEXPECT_PROMPT> ` 且以同名字面量做 `expect()` 匹配。
    一旦某条命令的输出里含 `PEXPECT_PROMPT>` 子串，`expect()` 就在输出中间提前匹配 →
    `shell.before` 被截断 → 退出码探针与真实提示符时序错位 → 退出码标记泄漏到下一条命令 →
    整个持久会话永久失同步（后续每条命令都返回上一条的退出码标记，退出码恒为 1）。

    根治：把提示符哨兵改成带实例级随机 nonce 的唯一串（`self._prompt`），命令输出几乎不可能
    撞上，从根上消除提前匹配。

    Reproduces AS-35: the old fixed `PEXPECT_PROMPT> ` sentinel, matched by the same literal,
    made `expect()` match prematurely whenever a command's output contained that substring,
    permanently desyncing the persistent session. Fix: randomize the sentinel per instance.
    """

    @pytest.fixture
    def env(self, tmp_path):
        args = EnvironmentArguments(image_name="local", timeout=8)
        cmd_filter = CommandFilterConfig.from_white_list(["echo", "expr", "true", "false"])
        env = PexpectTerminalEnv(args=args, work_dir=str(tmp_path), cmd_filter=cmd_filter)
        yield env
        env.close()

    def test_prompt_sentinel_is_randomized_per_instance(self, tmp_path):
        """哨兵须含实例级随机 nonce，且非旧固定字面量 | sentinel is randomized, not the old literal"""
        args = EnvironmentArguments(image_name="local", timeout=8)
        cmd_filter = CommandFilterConfig.from_white_list(["echo"])
        e1 = PexpectTerminalEnv(args=args, work_dir=str(tmp_path), cmd_filter=cmd_filter)
        e2 = PexpectTerminalEnv(args=args, work_dir=str(tmp_path), cmd_filter=cmd_filter)
        try:
            assert e1._prompt != "PEXPECT_PROMPT>", "哨兵不应再是旧固定字面量 | must not be the old literal"
            assert e1._prompt != e2._prompt, "不同实例哨兵须不同 | sentinels must differ across instances"
        finally:
            e1.close()
            e2.close()

    def test_output_containing_old_sentinel_does_not_truncate(self, env):
        """输出含旧字面量 `PEXPECT_PROMPT>` 不应触发提前匹配/截断 | no premature match on old literal"""
        result = env._execute_command('echo "some PEXPECT_PROMPT> text"')

        assert result.success is True, f"含旧哨兵子串的命令应成功 | should succeed: {result.output!r}"
        assert result.exit_code == 0
        # 旧实现这里只会得到被截断的 'some'；修复后须拿到完整输出
        # The old impl truncated to 'some'; the fix must return the full line.
        assert result.output.strip() == "some PEXPECT_PROMPT> text", (
            f"输出被提前匹配截断 | output truncated by premature prompt match: {result.output!r}"
        )

    def test_session_not_desynced_after_sentinel_in_output(self, env):
        """触发条件后会话不应被永久毒化，后续命令输出/退出码均正确 | no permanent desync"""
        # 先跑一条会让旧实现失同步的命令 | run the command that desyncs the old impl
        env._execute_command('echo "trap PEXPECT_PROMPT> here"')

        # 关键回归断言：之后的命令不能读到 stale RC blob | next commands must be clean
        r2 = env._execute_command("echo HELLO_AFTER")
        assert r2.success is True and r2.exit_code == 0
        assert r2.output.strip() == "HELLO_AFTER", f"会话被毒化，读到上一条的残留 | session poisoned: {r2.output!r}"

        r3 = env._execute_command("expr 6 \\* 7")
        assert r3.success is True and r3.exit_code == 0
        assert r3.output.strip() == "42", f"会话仍失同步 | still desynced: {r3.output!r}"

    def test_output_containing_sentinel_prefix_does_not_desync(self, env):
        """输出含哨兵公共前缀但非本实例 nonce 时不应误匹配 | shared prefix w/o nonce won't match"""
        # 用一个伪 nonce 拼出形似哨兵的串，验证匹配的是完整唯一哨兵而非公共前缀
        # A fake-nonce sentinel-shaped string must not trigger a match (full unique sentinel only).
        env._execute_command('echo "__IDE4AI_PROMPT_deadbeef__> bait"')
        r = env._execute_command("echo STILL_OK")
        assert r.success is True and r.exit_code == 0
        assert r.output.strip() == "STILL_OK", f"伪哨兵前缀致失同步 | fake-prefix desync: {r.output!r}"


if __name__ == "__main__":
    # 运行测试 | Run tests
    # pytest tests/environment/test_pexpect_terminal.py -v
    pytest.main([__file__, "-v"])
