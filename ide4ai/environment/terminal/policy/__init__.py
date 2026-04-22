"""
终端命令策略层 | Terminal command policy layer

在 parser 产出的 AST 之上做规则匹配，决定命令是 allow / deny / ask（Epic A 仅 allow/deny，
ask 在 Epic B 引入）。

模块划分：
- `rule.py` —— `BashRule`：规则的值对象与工厂方法
- `classifier.py` —— 从 `ParsedCommand` 抽取前缀（用于规则匹配）
- `engine.py` —— `PolicyEngine`：规则集合的顶层查询入口，返回 `PolicyDecision`
"""

from ide4ai.environment.terminal.policy.classifier import (
    get_first_word_prefix,
    get_simple_command_prefix,
)
from ide4ai.environment.terminal.policy.engine import (
    PolicyDecision,
    PolicyEngine,
)
from ide4ai.environment.terminal.policy.rule import (
    BashRule,
    RuleEffect,
    RuleKind,
)

__all__ = [
    "BashRule",
    "PolicyDecision",
    "PolicyEngine",
    "RuleEffect",
    "RuleKind",
    "get_first_word_prefix",
    "get_simple_command_prefix",
]
