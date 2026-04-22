"""
规则值对象与匹配 | Rule value object & matching

规则有两个正交维度：
- `RuleKind`：`exact` / `prefix` / `wildcard`
- `RuleEffect`：`allow` / `deny`（Epic B 引入 `ask`）

Pattern 语法（借鉴 Claude Code）：
- Exact：`"git status"`（完整命令，整串相等；不关心后续 args）
- Prefix：`"git commit:*"`（前缀 + 任意参数）。`:*` 是尾标识；实际匹配时去除。
- Wildcard：`"npm *:build"`（中间 glob）。Epic A 暂不实现 Wildcard（留占位）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

__all__ = [
    "BashRule",
    "RuleEffect",
    "RuleKind",
    "PREFIX_SUFFIX",
]


class RuleKind(str, Enum):
    EXACT = "exact"
    PREFIX = "prefix"
    WILDCARD = "wildcard"


class RuleEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    # ASK 预留给 Epic B；Epic A 的 Engine 遇到 ASK 规则会抛异常，避免静默放行。
    ASK = "ask"


# Prefix 规则的尾标识：`"git commit:*"` 表示前缀 `git commit` + 任意后续参数。
PREFIX_SUFFIX: Final[str] = ":*"


@dataclass(frozen=True, slots=True)
class BashRule:
    """
    单条 Bash 规则 | A single Bash rule

    Attributes:
        pattern: 规则模式；`exact` 时是完整命令；`prefix` 时是前缀串（不含 `:*`）
        kind: 规则形态
        effect: 规则效果
        reason: 规则说明（被展示给 LLM / 用户）
    """

    pattern: str
    kind: RuleKind
    effect: RuleEffect
    reason: str = ""
    # 额外元数据：规则来源（default / user / project / env-derived 等）。
    source: str = field(default="")

    # —— 工厂方法：构造常见规则 —— #

    @classmethod
    def allow_prefix(cls, prefix: str, reason: str = "", source: str = "") -> BashRule:
        """构造 `prefix` + allow 规则。传入的 prefix 不需要含 `:*`。"""
        return cls(pattern=prefix.rstrip(), kind=RuleKind.PREFIX, effect=RuleEffect.ALLOW, reason=reason, source=source)

    @classmethod
    def deny_prefix(cls, prefix: str, reason: str = "", source: str = "") -> BashRule:
        return cls(pattern=prefix.rstrip(), kind=RuleKind.PREFIX, effect=RuleEffect.DENY, reason=reason, source=source)

    @classmethod
    def allow_exact(cls, cmd: str, reason: str = "", source: str = "") -> BashRule:
        return cls(pattern=cmd.rstrip(), kind=RuleKind.EXACT, effect=RuleEffect.ALLOW, reason=reason, source=source)

    @classmethod
    def deny_exact(cls, cmd: str, reason: str = "", source: str = "") -> BashRule:
        return cls(pattern=cmd.rstrip(), kind=RuleKind.EXACT, effect=RuleEffect.DENY, reason=reason, source=source)

    # —— 匹配逻辑 —— #

    def matches(self, prefix: str, full_command: str) -> bool:
        """
        判断本规则是否匹配给定命令。

        Args:
            prefix: 抽取出的命令前缀（如 `ls` / `git commit`）
            full_command: 完整命令串（用于 exact 匹配）

        Returns:
            是否命中
        """
        if self.kind is RuleKind.EXACT:
            return full_command.strip() == self.pattern
        if self.kind is RuleKind.PREFIX:
            if not prefix:
                return False
            # `git` 规则 → `git commit` 命中（首段相等或首段为前缀）
            return prefix == self.pattern or prefix.startswith(self.pattern + " ")
        # WILDCARD：Epic A 不实现
        return False
