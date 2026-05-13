# filename: command_filter.py
# @Time    : 2025/11/01 19:21
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
命令过滤配置（兼容 shim）| Command filter configuration (compat shim)

Epic A (AS-29) 起，`CommandFilterConfig` 的匹配逻辑内部委托给
`policy.PolicyEngine`，旧 API `from_white_list` / `is_allowed` /
`get_rejection_reason` 保持向后兼容，但：

- `is_allowed(command)` 现在会用 parser 抬升 `command` 成 `ParsedCommand`，
  再走 PolicyEngine —— 这正是 AS-20 的直接修复：`"ls -la /home"` 按 `ls` 前缀
  命中 allow 规则，不再因整串不在白名单而拒绝；
- 同时黑名单也改成 PolicyEngine 的 deny 规则（优先级：deny > allow）；
- 每个实例首次使用时 emit 一条 `DeprecationWarning`，建议迁移到 `PolicyEngine`。

此模块本身的对外 API 保持不变，tests 与下游调用无需一次性改动。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

from ide4ai.environment.terminal.parser.command_ast import (
    CompoundCommand,
    ParsedCommand,
    PipelineCommand,
    SegmentNode,
)
from ide4ai.environment.terminal.parser.tokenizer import parse_command_line
from ide4ai.environment.terminal.policy.engine import PolicyDecision, PolicyEngine
from ide4ai.environment.terminal.policy.rule import BashRule, RuleEffect

# 默认危险命令黑名单 | Default dangerous command blacklist
DEFAULT_BLACK_LIST = [
    "rm",  # 删除文件 | Delete files
    "rmdir",  # 删除目录 | Delete directories
    "dd",  # 磁盘操作 | Disk operations
    "mkfs",  # 格式化文件系统 | Format filesystem
    "format",  # 格式化 | Format
    "fdisk",  # 磁盘分区 | Disk partition
    "parted",  # 磁盘分区 | Disk partition
    "shutdown",  # 关机 | Shutdown
    "reboot",  # 重启 | Reboot
    "halt",  # 停机 | Halt
    "poweroff",  # 关机 | Power off
    "init",  # 系统初始化 | System init
    "telinit",  # 运行级别切换 | Run level switch
]

# 迁移建议：将来新代码请直接用 PolicyEngine（见 ide4ai.environment.terminal.policy）
_DEPRECATION_MESSAGE = (
    "CommandFilterConfig is scheduled for deprecation: "
    "please migrate to ide4ai.environment.terminal.policy.PolicyEngine. "
    "See Jira AS-29 (Epic A · A3) for background."
)


@dataclass
class CommandFilterConfig:
    """
    命令过滤配置（兼容 shim）| Command filter configuration (compat shim)

    保留字段与字段语义不变；`is_allowed` / `get_rejection_reason` 会懒惰构造一个
    `PolicyEngine` 并委托过去。首次调用 emit `DeprecationWarning`。

    Attributes:
        white_list: 白名单（每项视为 Prefix allow 规则）| Whitelist (each entry → Prefix allow rule)
        black_list: 黑名单（每项视为 Prefix deny 规则）| Blacklist (each entry → Prefix deny rule)
    """

    white_list: list[str] | None = None
    black_list: list[str] | None = field(default_factory=lambda: DEFAULT_BLACK_LIST.copy())

    # 内部缓存：首次调用时构造，避免每次 is_allowed 都重建引擎。
    _engine: PolicyEngine | None = field(default=None, init=False, repr=False, compare=False)
    _warned: bool = field(default=False, init=False, repr=False, compare=False)

    # —— 公共 API（保持向后兼容） —— #

    def is_allowed(self, command: str) -> bool:
        """
        判断命令是否允许执行 | Check if command is allowed to execute

        Args:
            command: 要检查的命令。可以是单个 token（如 `"ls"`）或完整命令行
                     （如 `"ls -la /home"`）。
                     The command (single token or full command line).

        Returns:
            是否允许执行 | Whether execution is allowed
        """
        self._emit_deprecation_once()
        decision = self._decide(command)
        return decision.effect is RuleEffect.ALLOW

    def get_rejection_reason(self, command: str) -> str:
        """
        获取命令被拒绝的原因 | Get reason why command was rejected

        Args:
            command: 被拒绝的命令 | Rejected command

        Returns:
            拒绝原因 | Rejection reason
        """
        self._emit_deprecation_once()
        decision = self._decide(command)
        if decision.effect is RuleEffect.ALLOW:
            return ""
        # 兼容既有异常消息格式：旧实现针对 white_list/black_list 有两种措辞
        if self.white_list is not None and decision.matched_rule is None:
            return f"Command '{command}' not in whitelist"
        if self.black_list is not None and decision.matched_rule is not None:
            return f"Command '{command}' is in blacklist (dangerous command)"
        if decision.reason:
            return decision.reason
        return f"Command '{command}' is not allowed"

    # —— 工厂方法 —— #

    @classmethod
    def from_white_list(cls, white_list: list[str]) -> CommandFilterConfig:
        """从白名单创建配置 | Create config from whitelist"""
        return cls(white_list=list(white_list), black_list=None)

    @classmethod
    def allow_all_except(cls, black_list: list[str] | None = None) -> CommandFilterConfig:
        """创建仅使用黑名单的配置 | Create config with only blacklist"""
        if black_list is None:
            black_list = DEFAULT_BLACK_LIST.copy()
        return cls(white_list=None, black_list=list(black_list))

    @classmethod
    def allow_all(cls) -> CommandFilterConfig:
        """创建允许所有命令的配置 | Create config allowing all commands"""
        return cls(white_list=None, black_list=None)

    # —— 内部实现 —— #

    def _emit_deprecation_once(self) -> None:
        if not self._warned:
            warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=3)
            self._warned = True

    def _decide(self, command: str) -> PolicyDecision:
        """把命令抬升成 AST 并查规则引擎；失败则回退到最宽松 deny。"""
        try:
            node: SegmentNode = parse_command_line(command)
        except ValueError:
            # 引号不平衡等 → 拒绝
            return PolicyDecision(
                effect=RuleEffect.DENY,
                reason=f"Failed to parse command: {command!r}",
            )

        # 复合/管道命令：任一段 deny → 整体 deny；全部 allow → allow；
        # 否则按最不宽松段来。Epic A 只实现叶子判决 + 复合命令逐段；完整复合逻辑 Epic B 完善。
        return self._decide_any_node(node, command)

    def _decide_any_node(self, node: SegmentNode, command: str) -> PolicyDecision:
        engine = self._get_engine()

        if isinstance(node, ParsedCommand):
            return engine.decide(node)

        if isinstance(node, CompoundCommand):
            segments: list[SegmentNode] = list(node.segments)
        elif isinstance(node, PipelineCommand):
            segments = list(node.stages)
        else:
            # 未知节点类型 → 拒绝（类型系统保证不会到这里；防御性代码）
            return PolicyDecision(
                effect=RuleEffect.DENY,
                reason=f"Unknown AST node for command: {command!r}",
            )

        last_allow: PolicyDecision | None = None
        for seg in segments:
            d = self._decide_any_node(seg, command)
            if d.effect is RuleEffect.DENY:
                return d
            last_allow = d
        return last_allow or PolicyDecision(
            effect=engine.default_effect,
            reason="Empty compound command",
        )

    def _get_engine(self) -> PolicyEngine:
        if self._engine is None:
            self._engine = self._build_engine()
        return self._engine

    def _build_engine(self) -> PolicyEngine:
        rules: list[BashRule] = []
        # 黑名单 → Prefix deny
        if self.black_list is not None:
            for c in self.black_list:
                rules.append(BashRule.deny_prefix(c, reason=f"'{c}' is in blacklist (dangerous command)"))

        # 白名单 → Prefix allow；默认效果取决于是否有白名单
        if self.white_list is not None:
            for c in self.white_list:
                rules.append(BashRule.allow_prefix(c, reason=f"'{c}' is whitelisted"))
            default = RuleEffect.DENY  # 白名单模式 → 无命中默认拒绝
        else:
            default = RuleEffect.ALLOW  # 黑名单模式 → 无命中默认放行

        return PolicyEngine(rules=rules, default_effect=default)
