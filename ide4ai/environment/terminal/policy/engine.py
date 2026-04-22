"""
策略引擎 | Policy engine

给定一组 `BashRule` 和一个 `ParsedCommand`，决定 allow / deny / ask。

查找顺序（Epic A）：
1. 抽取前缀（simple 两段，兜底一段）；
2. 先查所有 `deny` 规则，任一命中 → deny；
3. 再查所有 `allow` 规则，任一命中 → allow；
4. 都没命中 → **默认 deny（严格模式）**；Epic B 会改默认为 ask。

Epic A 不支持 `RuleEffect.ASK` 的规则本身；若规则集合里有 ASK 规则会抛异常，
避免静默错过。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ide4ai.environment.terminal.parser.command_ast import ParsedCommand
from ide4ai.environment.terminal.policy.classifier import (
    get_first_word_prefix,
    get_simple_command_prefix,
)
from ide4ai.environment.terminal.policy.rule import BashRule, RuleEffect

__all__ = [
    "PolicyDecision",
    "PolicyEngine",
]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """
    策略引擎的决策输出 | Policy engine decision output

    Attributes:
        effect: allow / deny（Epic B 引入 ask）
        reason: 决策原因（给 LLM / 审计日志看的）
        matched_rule: 命中的规则（None 表示未命中 → 走默认效果）
        suggested_rule: 被拒绝时，建议用户加入 allow 的规则 pattern（未实现 → None）
    """

    effect: RuleEffect
    reason: str
    matched_rule: BashRule | None = None
    suggested_rule: str | None = None


class PolicyEngine:
    """
    规则集合的顶层查询入口。

    - `decide(parsed)` —— 对一个 `ParsedCommand` 做决策
    - 规则集合在构造时冻结；要替换需新建实例（方便线程安全与缓存）

    Epic A 只支持叶子命令；Compound/Pipeline 的逐段判决放到 Epic B。
    """

    def __init__(self, rules: Iterable[BashRule], *, default_effect: RuleEffect = RuleEffect.DENY) -> None:
        self._rules: list[BashRule] = []
        for r in rules:
            if r.effect is RuleEffect.ASK:
                # Epic A 不支持 ASK 规则；阻止静默错过。
                raise NotImplementedError("ASK rules are reserved for Epic B; do not use in Epic A.")
            self._rules.append(r)
        if default_effect is RuleEffect.ASK:
            raise NotImplementedError("default_effect=ASK is reserved for Epic B.")
        self._default_effect = default_effect

    @property
    def rules(self) -> list[BashRule]:
        return list(self._rules)

    @property
    def default_effect(self) -> RuleEffect:
        return self._default_effect

    def decide(self, parsed: ParsedCommand) -> PolicyDecision:
        """
        对单条 `ParsedCommand` 做策略决策。

        Args:
            parsed: 已解析的命令 AST 节点

        Returns:
            PolicyDecision
        """
        if parsed.is_empty:
            return PolicyDecision(
                effect=self._default_effect,
                reason="Empty command (no command name)",
                matched_rule=None,
            )

        simple_prefix = get_simple_command_prefix(parsed) or ""
        first_prefix = get_first_word_prefix(parsed) or ""
        full_command = self._reconstruct_full_command(parsed)

        # 规则匹配时用"更精确的前缀"试一次；否则用一段前缀。
        # `git commit -m fix` 同时匹配 `git commit:*` 和 `git:*`——前者优先（更具体）。

        # 先查 deny：精确前缀 > 一段前缀 > exact
        deny_hit = self._find_match(full_command, simple_prefix, first_prefix, effect=RuleEffect.DENY)
        if deny_hit is not None:
            return PolicyDecision(
                effect=RuleEffect.DENY,
                reason=deny_hit.reason or f"Command matches deny rule: {deny_hit.pattern}",
                matched_rule=deny_hit,
            )

        allow_hit = self._find_match(full_command, simple_prefix, first_prefix, effect=RuleEffect.ALLOW)
        if allow_hit is not None:
            return PolicyDecision(
                effect=RuleEffect.ALLOW,
                reason=allow_hit.reason or f"Command matches allow rule: {allow_hit.pattern}",
                matched_rule=allow_hit,
            )

        # 默认效果
        return PolicyDecision(
            effect=self._default_effect,
            reason=f"No rule matches '{full_command}'",
            matched_rule=None,
            # Epic B 会在此给出 suggested_rule；Epic A 先空。
        )

    # —— 内部实现 —— #

    def _find_match(
        self,
        full_command: str,
        simple_prefix: str,
        first_prefix: str,
        *,
        effect: RuleEffect,
    ) -> BashRule | None:
        # 优先级：exact > 两段前缀 > 一段前缀。在同等优先级内按规则出现顺序。
        for rule in self._rules:
            if rule.effect is not effect:
                continue
            if rule.matches(simple_prefix or first_prefix, full_command):
                return rule
        # fallback：只有一段前缀命中的规则
        if simple_prefix and first_prefix and simple_prefix != first_prefix:
            for rule in self._rules:
                if rule.effect is not effect:
                    continue
                if rule.matches(first_prefix, full_command):
                    return rule
        return None

    @staticmethod
    def _reconstruct_full_command(parsed: ParsedCommand) -> str:
        """
        重建完整命令串用于 exact 匹配。不含 env_prefix 与 wrappers——
        规则书写者关心的是"真实执行的命令"。
        """
        parts: list[str] = [parsed.command_name]
        if parsed.subcommand:
            parts.append(parsed.subcommand)
        parts.extend(parsed.args)
        return " ".join(parts)
