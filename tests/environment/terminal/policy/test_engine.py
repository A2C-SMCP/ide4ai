"""
policy/engine.py 单元测试 | Unit tests for policy/engine.py

对应 Jira AS-28 (Epic A · A2)。
"""

from __future__ import annotations

import pytest

from ide4ai.environment.terminal.parser import parse_command_line
from ide4ai.environment.terminal.parser.command_ast import ParsedCommand
from ide4ai.environment.terminal.policy.engine import PolicyEngine
from ide4ai.environment.terminal.policy.rule import BashRule, RuleEffect


def _leaf(cmd: str) -> ParsedCommand:
    node = parse_command_line(cmd)
    assert isinstance(node, ParsedCommand)
    return node


class TestPolicyEngineAllowDeny:
    def test_allow_prefix_hits(self) -> None:
        """AS-20 的核心修复：带参数命令不应再被误拦截。"""
        engine = PolicyEngine(rules=[BashRule.allow_prefix("ls")])
        d = engine.decide(_leaf("ls -la /home"))
        assert d.effect is RuleEffect.ALLOW
        assert d.matched_rule is not None
        assert d.matched_rule.pattern == "ls"

    def test_no_match_defaults_to_deny(self) -> None:
        engine = PolicyEngine(rules=[BashRule.allow_prefix("ls")])
        d = engine.decide(_leaf("cat /etc/hosts"))
        assert d.effect is RuleEffect.DENY
        assert d.matched_rule is None

    def test_exact_match(self) -> None:
        engine = PolicyEngine(rules=[BashRule.allow_exact("pwd")])
        assert engine.decide(_leaf("pwd")).effect is RuleEffect.ALLOW
        assert engine.decide(_leaf("pwd /tmp")).effect is RuleEffect.DENY

    def test_deny_overrides_allow(self) -> None:
        """同时有 `git:*` allow 和 `git push:*` deny → `git push` 拒绝。"""
        engine = PolicyEngine(
            rules=[
                BashRule.allow_prefix("git"),
                BashRule.deny_prefix("git push"),
            ]
        )
        assert engine.decide(_leaf("git status")).effect is RuleEffect.ALLOW
        assert engine.decide(_leaf("git push origin main")).effect is RuleEffect.DENY

    def test_two_word_prefix_rule(self) -> None:
        """`git commit:*` allow → `git commit -m x` 放行、`git push` 不放行。"""
        engine = PolicyEngine(rules=[BashRule.allow_prefix("git commit")])
        assert engine.decide(_leaf("git commit -m x")).effect is RuleEffect.ALLOW
        # `git push` 不匹配 `git commit`
        assert engine.decide(_leaf("git push")).effect is RuleEffect.DENY

    def test_empty_command_denied_by_default(self) -> None:
        engine = PolicyEngine(rules=[BashRule.allow_prefix("ls")])
        d = engine.decide(_leaf(""))
        assert d.effect is RuleEffect.DENY

    def test_custom_default_effect_allow(self) -> None:
        engine = PolicyEngine(rules=[], default_effect=RuleEffect.ALLOW)
        assert engine.decide(_leaf("anything")).effect is RuleEffect.ALLOW

    def test_ask_rules_raise_in_epic_a(self) -> None:
        """Epic A 拒绝 ASK 规则，避免静默放行。"""
        with pytest.raises(NotImplementedError):
            PolicyEngine(rules=[BashRule(pattern="p", kind=BashRule.allow_prefix("p").kind, effect=RuleEffect.ASK)])

    def test_ask_default_raises_in_epic_a(self) -> None:
        with pytest.raises(NotImplementedError):
            PolicyEngine(rules=[], default_effect=RuleEffect.ASK)

    def test_multiple_allow_rules_first_match_wins(self) -> None:
        engine = PolicyEngine(
            rules=[
                BashRule.allow_prefix("ls", reason="first"),
                BashRule.allow_prefix("ls", reason="second"),
            ]
        )
        d = engine.decide(_leaf("ls"))
        assert d.effect is RuleEffect.ALLOW
        assert d.matched_rule is not None
        assert d.matched_rule.reason == "first"

    def test_gitk_not_matched_by_git_rule(self) -> None:
        """`git` 规则不应匹配 `gitk`（避免前缀误匹配）。"""
        engine = PolicyEngine(rules=[BashRule.allow_prefix("git")])
        # `gitk` 不在规则里 → default deny
        d = engine.decide(_leaf("gitk"))
        assert d.effect is RuleEffect.DENY
