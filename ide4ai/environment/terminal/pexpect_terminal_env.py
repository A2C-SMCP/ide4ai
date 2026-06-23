# filename: pexpect_terminal_env.py
# @Time    : 2025/10/28 18:26
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
基于 pexpect 的终端环境实现 | Terminal environment implementation based on pexpect

相比于 local_terminal_env.py 的优势:
1. 持久会话 - 维持一个持久的 shell 进程,保持环境变量和状态
2. 虚拟环境支持 - 可以在初始化时激活虚拟环境,后续命令都在该环境中执行
3. 交互式支持 - 支持需要用户输入的命令
4. 真实 shell 行为 - cd、export 等内置命令正常工作
"""

import base64
import os
import re
import time
import uuid
from typing import Any, ClassVar, cast

import gymnasium as gym
import pexpect
from loguru import logger
from typing_extensions import SupportsFloat

from ide4ai.environment.terminal.base import BaseTerminalEnv, EnvironmentArguments
from ide4ai.environment.terminal.command_filter import CommandFilterConfig
from ide4ai.environment.terminal.execution.run_result import StepResult
from ide4ai.environment.terminal.semantics.output_pipeline import clean_output
from ide4ai.schema import IDEAction, IDEObs


class PexpectTerminalEnv(BaseTerminalEnv):
    """
    基于 pexpect 的终端环境 | Terminal environment based on pexpect

    使用持久的 shell 会话来执行命令,支持虚拟环境激活和状态保持
    Uses persistent shell session to execute commands, supports virtual environment activation and state persistence

    Attributes:
        name (str): 环境名称 | Environment name
        cmd_filter (CommandFilterConfig): 命令过滤配置(黑白名单) | Command filter configuration (blacklist/whitelist)
        work_dir (str): 工作目录 | Working directory
        active_venv_cmd (str | None): 虚拟环境初始化命令 | Virtual environment initialization command
        shell (pexpect.spawn): 持久的 shell 进程 | Persistent shell process
    """

    name: ClassVar[str] = "PexpectTerminalEnv"
    metadata: dict[str, Any] = {"render_modes": ["ansi"]}

    # Shell 提示符模式 | Shell prompt pattern
    PROMPT_PATTERN = r"[\$#>]\s*$"

    # AS-20 同源 Bug #2 修复：退出码用独立定界符抽取，不再 regex 扫输出
    # A 可变的标签避免串扰（如用户命令意外含 "__IDE4AI_RC_"）；每实例生成一次。
    _RC_TAG: ClassVar[str] = "IDE4AI_RC"  # 用于调试/错误提示；实际定界符在 __init__ 注入随机后缀

    def __init__(
        self,
        args: EnvironmentArguments,
        work_dir: str,
        cmd_filter: CommandFilterConfig | None = None,
        active_venv_cmd: str | None = None,
        shell: str = "/bin/bash",
    ) -> None:
        """
        初始化 pexpect 终端环境 | Initialize pexpect terminal environment

        Args:
            args: 环境参数 | Environment arguments
            work_dir: 工作目录 | Working directory
            cmd_filter: 命令过滤配置(黑白名单) | Command filter configuration (blacklist/whitelist)
            active_venv_cmd: 虚拟环境初始化命令,例如 "source .venv/bin/activate" 或 "uv venv activate"
                      Virtual environment initialization command, e.g., "source .venv/bin/activate" or "uv venv activate"
            shell: Shell 程序路径 | Shell program path
        """
        super().__init__()
        self.args = args

        # 处理命令过滤配置 | Handle command filter config
        if cmd_filter is not None:
            self.cmd_filter = cmd_filter
        else:
            # 默认使用黑名单模式 | Default to blacklist mode
            self.cmd_filter = CommandFilterConfig.allow_all_except()

        self.active_venv_cmd = active_venv_cmd
        self.shell_path = shell

        # 验证工作目录 | Validate working directory
        if os.path.exists(work_dir) and os.path.isdir(work_dir):
            self.work_dir = self.current_dir = os.path.expanduser(work_dir)
        else:
            raise ValueError(f"Work directory {work_dir} does not exist")

        # 状态标志 | State flags
        self._is_closing = False
        self._is_closed = False
        # 超时设置 | Timeout settings
        self.timeout = self.args.timeout

        # 命令历史记录 | Command history
        self._command_history: list[dict[str, str]] = []

        # 虚拟环境激活状态 | Virtual environment activation status
        self.venv_activated = False
        self.venv_activation_error: str | None = None

        # 退出码定界符：实例级随机后缀，避免命令输出中碰巧出现同名串
        # Exit-code delimiter: per-instance random suffix to avoid collisions in command output
        rc_nonce = uuid.uuid4().hex[:8]
        self._rc_start = f"__{self._RC_TAG}_{rc_nonce}_"
        self._rc_end = f"_{self._RC_TAG}_{rc_nonce}__"
        self._rc_pattern: re.Pattern[str] = re.compile(
            re.escape(self._rc_start) + r"(-?\d+)" + re.escape(self._rc_end),
        )

        # 提示符哨兵：实例级随机后缀，根治 AS-35。
        # 旧实现 PS1 固定为 "PEXPECT_PROMPT> " 且以同名字面量做 expect 匹配，一旦某条命令的
        # 输出里含 "PEXPECT_PROMPT>" 子串，expect() 就在输出中间提前匹配 → shell.before 被截断
        # → 退出码探针与真实提示符时序错位 → 退出码标记泄漏到下一条命令 → 整个持久会话永久失同步。
        # 与退出码定界符同源思路：把哨兵改成带随机 nonce 的唯一串，命令输出几乎不可能撞上。
        #
        # Per-instance prompt sentinel: root-fix for AS-35. The old PS1 was a fixed
        # "PEXPECT_PROMPT> " matched by the same literal, so any command whose output contained
        # that substring made expect() match prematurely and permanently desynced the session.
        # Randomizing the sentinel (same idea as the exit-code delimiter) makes a collision with
        # real command output effectively impossible.
        prompt_nonce = uuid.uuid4().hex[:8]
        self._prompt = f"__IDE4AI_PROMPT_{prompt_nonce}__>"
        self._prompt_re = re.escape(self._prompt)

        # 初始化持久 shell 会话 | Initialize persistent shell session
        self._init_shell()

        # Gym spaces
        self.action_space = gym.spaces.Dict(
            {
                "category": gym.spaces.Discrete(2),
                "action_name": gym.spaces.Text(100),
                "action_args": gym.spaces.Text(1000),
            },
        )
        self.observation_space = gym.spaces.Dict(
            {
                "created_at": gym.spaces.Text(100),
                "obs": gym.spaces.Text(100000),
            },
        )

    def _init_shell(self) -> None:
        """
        初始化持久的 shell 会话 | Initialize persistent shell session

        启动一个 shell 进程并进行必要的配置:
        1. 在工作目录中启动 shell
        2. 设置 PS1 提示符以便识别命令完成
        3. 如果指定了虚拟环境,激活它

        Start a shell process and perform necessary configuration:
        1. Start shell in working directory
        2. Set PS1 prompt for command completion detection
        3. Activate virtual environment if specified
        """
        try:
            # 启动 shell 进程,直接在工作目录中启动 | Start shell process directly in working directory
            self.shell = pexpect.spawn(
                self.shell_path,
                encoding="utf-8",
                echo=False,
                timeout=self.timeout,
                cwd=self.work_dir,
                # use_poll=True：pexpect 默认内部用 select.select()，fd≥1024 时会抛
                # ValueError: filedescriptor out of range（TFROB-588 同源风险）；
                # 切到 poll() 规避 FD_SETSIZE(1024) 上限。
                use_poll=True,
            )

            # 设置实例级唯一提示符以便于匹配（AS-35：随机 nonce 杜绝输出子串提前匹配）
            # Set a per-instance unique prompt (AS-35: random nonce prevents premature substring match)
            self.shell.sendline(f'export PS1="{self._prompt} "')
            self.shell.expect(self._prompt_re, timeout=5)

            # 激活虚拟环境(如果指定) | Activate virtual environment (if specified)
            if self.active_venv_cmd:
                try:
                    self.shell.sendline(self.active_venv_cmd)
                    index = self.shell.expect(
                        [self._prompt_re, pexpect.TIMEOUT, pexpect.EOF],
                        timeout=10,
                    )

                    if index == 0:
                        # 检查命令退出码 | Check command exit code
                        self.shell.sendline("echo $?")
                        self.shell.expect(self._prompt_re, timeout=5)
                        exit_code_output = self.shell.before or ""

                        # 提取退出码 | Extract exit code
                        exit_code_match = re.search(r"(\d+)", exit_code_output)
                        exit_code = int(exit_code_match.group(1)) if exit_code_match else 1

                        if exit_code == 0:
                            # 退出码为0,激活成功 | Exit code is 0, activation successful
                            self.venv_activated = True
                            logger.info(f"虚拟环境激活成功 | Virtual environment activated: {self.active_venv_cmd}")
                        else:
                            # 退出码非0,激活失败 | Exit code is non-zero, activation failed
                            self.venv_activated = False
                            self.venv_activation_error = (
                                f"虚拟环境激活命令返回非零退出码: {exit_code} | "
                                f"Venv activation command returned non-zero exit code: {exit_code}"
                            )
                            logger.warning(
                                f"虚拟环境激活失败: {self.venv_activation_error} | "
                                f"Virtual environment activation failed: {self.venv_activation_error}",
                            )
                    else:
                        # 激活超时或失败 | Activation timeout or failed
                        self.venv_activated = False
                        self.venv_activation_error = "虚拟环境激活超时 | Virtual environment activation timeout"
                        logger.warning(
                            f"虚拟环境激活失败: {self.venv_activation_error} | "
                            f"Virtual environment activation failed: {self.venv_activation_error}",
                        )

                except (pexpect.TIMEOUT, pexpect.EOF) as venv_error:
                    # 虚拟环境激活失败,但不影响 shell 初始化 | Venv activation failed, but don't fail shell init
                    self.venv_activated = False
                    self.venv_activation_error = str(venv_error)
                    logger.warning(
                        f"虚拟环境激活失败: {venv_error} | Virtual environment activation failed: {venv_error}",
                    )

        except (pexpect.ExceptionPexpect, OSError) as e:
            # 含 spawn 失败（如 shell 路径不可执行）、PS1 expect 超时/EOF。
            # 统一包成 RuntimeError：__init__ 时直接暴露；rebuild 时由 _execute_command
            # 外层 except 兜成错误 StepResult，保证「永不被毒死」在极端失败下仍不崩溃。
            # Covers spawn failures + PS1 expect TIMEOUT/EOF, wrapped uniformly so rebuild
            # degrades to a safe error StepResult instead of leaking an uncaught exception.
            raise RuntimeError(f"Failed to initialize shell: {e}") from e

    def construct_action(self, action: dict) -> IDEAction:
        """
        构建 IDEAction 对象 | Construct IDEAction object

        Args:
            action: 动作字典 | Action dictionary

        Returns:
            IDEAction 对象 | IDEAction object

        Raises:
            ValueError: 如果动作不合法 | If action is invalid
        """
        ide_action = IDEAction.model_validate(action)

        if ide_action.category != "terminal":
            raise ValueError(f"Unsupported action category: {ide_action.category}")

        if not self.cmd_filter.is_allowed(ide_action.action_name):
            reason = self.cmd_filter.get_rejection_reason(ide_action.action_name)
            raise ValueError(reason)

        if not isinstance(ide_action.action_args, (list, str)):
            raise ValueError(
                f"Unsupported action arguments: {ide_action.action_args}, args should be str or list[str]",
            )

        return ide_action

    def step(self, action: dict) -> tuple[dict, SupportsFloat, bool, bool, dict[str, Any]]:
        """
        执行一个动作 | Execute an action

        Args:
            action: 动作字典,包含 category, action_name, action_args
                   Action dictionary containing category, action_name, action_args

        Returns:
            观察、奖励、是否结束、是否成功、额外信息
            Observation, reward, done, success, extra info

        Notes:
            自 Epic A 起 `info` 由 `StepResult.to_info()` 填充，字段包括
            `exit_code / success / output / truncated / cwd / duration_ms`；
            修复 AS-20 同源 Bug #3。
        """
        self._assert_not_closed()

        # 构建并验证动作 | Construct and validate action
        terminal_action = self.construct_action(action)
        cmd = terminal_action.action_name
        args = (
            [terminal_action.action_args]
            if isinstance(terminal_action.action_args, str)
            else terminal_action.action_args
        )

        # 构建完整命令 | Build complete command
        full_command = f"{cmd} {' '.join(cast(list[str], args))}" if args else cmd

        # per-call 超时（秒）：由上层（如 BashTool）经 action dict 注入；IDEAction 默认忽略额外
        # 字段，故无需改 schema。未提供时回退到环境默认 self.timeout。
        # Per-call timeout (seconds): injected by callers (e.g. BashTool) via the action dict;
        # IDEAction ignores extra fields, so no schema change needed. Falls back to self.timeout.
        per_call_timeout = action.get("timeout")

        # 执行命令 | Execute command
        start = time.monotonic()
        result = self._execute_command(full_command, timeout=per_call_timeout)
        result.duration_ms = int((time.monotonic() - start) * 1000)

        # 记录命令历史 | Record command history
        self._command_history.append(
            {
                "command": full_command,
                "output": result.output,
                "success": str(result.success),
            },
        )

        # 返回观察结果 | Return observation
        obs = IDEObs(obs=result.output)
        reward = 100.0 if result.success else 0.0
        done = True  # 命令执行完成 | Command execution completed

        return obs.model_dump(), reward, done, result.success, result.to_info()

    def _execute_command(self, command: str, timeout: float | None = None) -> StepResult:
        """
        在持久 shell 会话中执行命令 | Execute command in persistent shell session

        AS-20 同源 Bug #2 修复：退出码通过独立定界符 `__IDE4AI_RC_<nonce>_<n>_..._`
        精确抽取，避免输出中的数字（含 OSC-133 里的 `133`）被 regex 误匹配。

        Issue #12 修复：命令超时（不回提示符的交互式 / 前台进程）后调用
        `_recover_after_timeout()` 中断卡住的进程并重新同步到提示符，失败则重建 shell；
        EOF（shell 已死）则直接重建。避免一条命令把整个持久会话永久毒死。

        Args:
            command: 要执行的命令 | Command to execute
            timeout: 本次命令的超时（秒）；None 时回退到环境默认 self.timeout
                     Per-call timeout in seconds; falls back to self.timeout when None

        Returns:
            结构化执行结果 | Structured StepResult
        """
        # per-call 超时优先，未提供或非正数则回退环境默认（与 bash.py 的 falsy 拦截口径一致）
        # Per-call timeout wins; non-positive/None falls back to env default (matches bash.py).
        effective_timeout = timeout if (timeout is not None and timeout > 0) else self.timeout
        try:
            # 发送命令 | Send command
            # Issue #15：多行 / heredoc 命令折叠为单条物理行后再发送，使持久 shell 只产生一个
            # 提示符，与「匹配首个提示符 = 命令完成」的协议及 #12 超时/恢复逻辑保持一致。
            # Issue #15: collapse multi-line / heredoc commands into a single physical line so
            # the persistent shell emits exactly one prompt, keeping the "first prompt = done"
            # protocol (and #12 recovery) intact.
            self.shell.sendline(self._to_single_line(command))

            # 等待命令完成 | Wait for command completion
            index = self.shell.expect(
                [self._prompt_re, pexpect.TIMEOUT, pexpect.EOF],
                timeout=effective_timeout,
            )

            if index == 0:
                raw_output = self.shell.before or ""

                # 精确抽取退出码：用独立定界符协议
                self.shell.sendline(f'echo "{self._rc_start}$?{self._rc_end}"')
                self.shell.expect(self._prompt_re, timeout=5)
                rc_blob = self.shell.before or ""
                exit_code = self._extract_exit_code(rc_blob)

                cleaned = self._clean_output(raw_output)
                cwd = self.current_dir  # 快照当前缓存的 cwd

                return StepResult(
                    exit_code=exit_code,
                    success=exit_code == 0,
                    output=cleaned,
                    truncated=False,  # 截断发生在 MCP 层；此处始终 False
                    cwd=cwd,
                    duration_ms=0,  # 由调用方填充
                )

            elif index == 1:
                # Issue #12：超时后恢复终端，避免被卡住的前台进程永久毒死后续命令
                # Issue #12: recover the terminal so a stuck foreground process can't
                # permanently poison every subsequent command.
                self._recover_after_timeout()
                return StepResult(
                    exit_code=-1,
                    success=False,
                    output=f"Command timeout after {effective_timeout:g} seconds",
                    cwd=self.current_dir,
                )

            else:
                # shell 进程已死（EOF）：重建以保证下一条命令可用
                # Shell process died (EOF): rebuild so the next command works.
                self._rebuild_shell()
                return StepResult(
                    exit_code=-1,
                    success=False,
                    output="Shell process terminated unexpectedly",
                    cwd=self.current_dir,
                )

        except Exception as e:
            return StepResult(
                exit_code=-1,
                success=False,
                output=f"Error executing command: {str(e)}",
                cwd=self.current_dir,
            )

    def _recover_after_timeout(self) -> None:
        """
        命令超时后恢复终端 | Recover terminal after a command times out (Issue #12)

        分两级，保证「至多重建一次、先关后建」，进程内始终至多一个 shell 实例：
        1. 软恢复：对**现有** shell 连发 Ctrl-C（SIGINT），短等提示符回归。响应 SIGINT 的
           前台进程（cat / sleep / head 等）会被中断，shell 回到提示符——**复用同一实例**，
           cwd/env 全部保留，不重建。
        2. 硬恢复：Ctrl-C 拉不回提示符（vim / top / ssh 等无视 SIGINT）→ `_rebuild_shell()`
           先 force-kill 旧实例再 spawn 新实例。

        Two-tier, guaranteeing at most one rebuild and at most one live shell at a time:
        1. Soft: send Ctrl-C (SIGINT) to the existing shell, briefly wait for the prompt.
           SIGINT-responsive processes die and the same shell instance is reused.
        2. Hard: if Ctrl-C can't restore the prompt, rebuild the shell (kill old, spawn new).
        """
        try:
            # 最多两次 Ctrl-C：覆盖部分需要二次中断才退出的场景
            # Up to two Ctrl-C: some programs need a second interrupt to bail out.
            for _ in range(2):
                self.shell.sendintr()
                index = self.shell.expect(
                    [self._prompt_re, pexpect.TIMEOUT, pexpect.EOF],
                    timeout=2,
                )
                if index == 0:
                    logger.debug("命令超时后经 Ctrl-C 软恢复成功 | recovered via Ctrl-C")
                    return
                if index == 2:
                    break  # shell 已死，转硬恢复 | shell dead, fall through to rebuild
        except (pexpect.ExceptionPexpect, OSError) as e:
            logger.warning(f"Ctrl-C 软恢复失败，转重建 shell | soft recovery failed, rebuilding: {e}")

        # 硬恢复：重建 shell | Hard recovery: rebuild shell
        self._rebuild_shell()

    def _rebuild_shell(self) -> None:
        """
        重建持久 shell 会话 | Rebuild the persistent shell session (Issue #12)

        先 force-kill 旧实例（SIGKILL 整个进程组，连带杀掉卡住的前台进程），再复用
        `_init_shell()` spawn 一个新实例覆盖 `self.shell`，最后 best-effort 恢复到超时前的
        工作目录。任何时刻只保留一个 shell 实例，不会堆积。

        First force-kill the old instance (SIGKILL to the whole process group, taking the
        stuck foreground process with it), then reuse `_init_shell()` to spawn a fresh one,
        and best-effort restore the previous working directory.
        """
        prev_dir = self.current_dir
        try:
            if hasattr(self, "shell") and self.shell.isalive():
                self.shell.close(force=True)
        except (pexpect.ExceptionPexpect, OSError) as e:
            logger.warning(f"重建 shell 时关闭旧进程异常（忽略）| error closing old shell (ignored): {e}")

        # 复用既有初始化逻辑（spawn + PS1 + venv 激活）| Reuse existing init (spawn + PS1 + venv)
        self._init_shell()

        # best-effort 恢复 cwd | best-effort restore cwd
        real_work_dir = os.path.realpath(self.work_dir)
        if prev_dir and os.path.realpath(prev_dir) != real_work_dir:
            try:
                self.shell.sendline(f'cd "{prev_dir}"')
                self.shell.expect(self._prompt_re, timeout=5)
                self.current_dir = prev_dir
            except (pexpect.ExceptionPexpect, OSError) as e:
                logger.warning(f"重建后恢复工作目录失败，回退到 work_dir | failed to restore cwd: {e}")
                self.current_dir = self.work_dir
        else:
            self.current_dir = self.work_dir

    @staticmethod
    def _to_single_line(command: str) -> str:
        """
        把可能含换行的命令折叠为单条物理行 | Collapse a possibly multi-line command to one line

        Issue #15 根治：持久 shell 用「单次 sendline + 匹配首个提示符」探测命令完成，隐含
        「命令是单行」假设。多行 / heredoc 命令的每一行都会触发一个提示符，首个提示符匹配
        后剩余行 + 后续提示符残留在 pty 缓冲，导致截断 / 卡满超时 / 退出码探针串位、会话毒化。

        修复：单行命令原样返回（零回归）；含换行的命令 base64 编码后包成单条物理行，经
        `eval "$(... | base64 --decode)"` 在**当前 shell 上下文**执行——只产生一个提示符，
        且 cd/export 等状态正常持久化、stdin 仍连到 pty（交互式命令行为不变）。

        - base64 输出仅含 `[A-Za-z0-9+/=]`，单引号包裹绝对安全，无任何转义/引号冲突。
        - `--decode` 长选项在 GNU coreutils 与 macOS/BSD base64 上均可用，比 `-d`/`-D` 更可移植。
        - 仅按 `\n` 触发折叠：含 `\n` 的命令才是真正的多物理行；不含 `\n`（哪怕有孤立 `\r`）
          本就是单物理行，原样透传即可，避免对退化输入做无谓包裹。

        Root-fix for Issue #15: single-line commands pass through unchanged (zero regression);
        commands containing a newline are base64-encoded and wrapped into one physical line run
        via `eval "$(... | base64 --decode)"` in the *current shell*, so the persistent shell
        emits exactly one prompt while cd/export state persists and stdin stays on the pty.

        Args:
            command: 原始命令（可能多行）| The original (possibly multi-line) command

        Returns:
            单条物理行命令 | A single physical-line command
        """
        if "\n" not in command:
            return command

        blob = base64.b64encode(command.encode("utf-8")).decode("ascii")
        return f"eval \"$(printf '%s' '{blob}' | base64 --decode)\""

    def _extract_exit_code(self, rc_blob: str) -> int:
        """
        从 `echo "__...<rc>__"` 的输出里抽退出码；找不到返回 1。

        Args:
            rc_blob: shell.before 的原始内容

        Returns:
            退出码 | Exit code
        """
        m = self._rc_pattern.search(rc_blob)
        if m is None:
            logger.warning(f"Failed to extract exit code from: {rc_blob!r}")
            return 1
        return int(m.group(1))

    @staticmethod
    def _clean_output(output: str) -> str:
        """
        清理命令输出 | Clean command output

        自 Epic A 起委托给 `semantics.output_pipeline.clean_output`，分阶段剥离
        CSI → OSC → OSC-133 → 归一化，修复 AS-20 同源 Bug #1。
        """
        return clean_output(output or "")

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[IDEObs, dict[str, Any]]:
        """
        重置环境 | Reset environment

        重新初始化 shell 会话,清除命令历史
        Reinitialize shell session, clear command history

        Args:
            seed: 随机种子 | Random seed
            options: 额外选项 | Additional options

        Returns:
            观察结果和额外信息 | Observation and extra info
        """
        self._assert_not_closed()

        # 关闭现有 shell | Close existing shell
        if hasattr(self, "shell") and self.shell.isalive():
            self.shell.close()

        # 清空命令历史 | Clear command history
        self._command_history.clear()

        # 重新初始化 shell | Reinitialize shell
        self._init_shell()

        return IDEObs(obs="Reset environment successfully"), {}

    def render(self) -> str:  # type: ignore[override]
        """
        渲染当前环境状态 | Render current environment state

        返回最近的命令历史
        Return recent command history

        Returns:
            渲染结果 | Render result
        """
        self._assert_not_closed()

        if not self._command_history:
            return f"$ (cwd: {self.current_dir})"

        # 渲染最近 3 条命令 | Render last 3 commands
        # 展示用中性提示符，避免泄漏内部随机哨兵（AS-35）| neutral display prompt, no internal sentinel
        render_frames = []
        for entry in self._command_history[-3:]:
            render_frames.append(
                f"$ {entry['command']}\n{entry['output']}",
            )

        return "\n\n".join(render_frames)

    def close(self) -> None:
        """
        关闭环境 | Close environment

        终止 shell 进程并清理资源
        Terminate shell process and clean up resources
        """
        if self._is_closed or self._is_closing:
            return

        self._is_closing = True

        try:
            if hasattr(self, "shell") and self.shell.isalive():
                # 尝试优雅退出 | Try graceful exit
                self.shell.sendline("exit")
                time.sleep(0.5)

                # 如果还活着,强制终止 | Force terminate if still alive
                if self.shell.isalive():
                    self.shell.close(force=True)
        except Exception as e:
            # 忽略关闭时的错误 | Ignore errors during close
            logger.error(f"关闭PexpectTerminal时发生异常: {e}")
        finally:
            self._command_history.clear()
            self._is_closed = True
            self._is_closing = False

    def _assert_not_closed(self) -> bool:
        """
        断言环境未关闭 | Assert environment is not closed

        Returns:
            如果环境未关闭返回 True | True if environment is not closed

        Raises:
            ValueError: 如果环境已关闭 | If environment is closed
        """
        if self._is_closed:
            raise ValueError("Environment is closed.")
        return True

    def change_dir(self, *, path: str) -> tuple[str, bool]:
        """
        更改当前目录 | Change current directory

        使用 cd 命令在持久 shell 中切换目录
        Use cd command to change directory in persistent shell

        Args:
            path: 目标目录路径 | Target directory path

        Returns:
            输出信息和是否成功 | Output message and success status
        """
        self._assert_not_closed()

        # 展开路径 | Expand path
        path = os.path.expanduser(path)

        # 验证路径是否在工作目录内 | Validate path is within working directory
        real_path = os.path.realpath(path)
        real_work_dir = os.path.realpath(self.work_dir)

        try:
            common_path = os.path.commonpath([real_path, real_work_dir])
            if common_path != real_work_dir:
                return f"Path {path} is not a subdirectory of {self.work_dir}", False
        except ValueError:
            return f"Path {path} is not a subdirectory of {self.work_dir}", False

        # 执行 cd 命令 | Execute cd command
        result = self._execute_command(f'cd "{path}"')

        if result.success:
            self.current_dir = real_path
            return f"Changed directory to {path}", True
        else:
            return f"Failed to change directory: {result.output}", False

    def get_env_var(self, var_name: str) -> str | None:
        """
        获取环境变量 | Get environment variable

        Args:
            var_name: 环境变量名 | Environment variable name

        Returns:
            环境变量值,如果不存在返回 None | Environment variable value, None if not exists
        """
        self._assert_not_closed()

        result = self._execute_command(f'echo "${var_name}"')

        if result.success and result.output:
            return result.output.strip()
        return None

    def set_env_var(self, var_name: str, value: str) -> bool:
        """
        设置环境变量 | Set environment variable

        Args:
            var_name: 环境变量名 | Environment variable name
            value: 环境变量值 | Environment variable value

        Returns:
            是否成功 | Success status
        """
        self._assert_not_closed()

        result = self._execute_command(f'export {var_name}="{value}"')
        return result.success
