"""
policy/rule.py 单元测试 | Unit tests for policy/rule.py

对应 Jira AS-28 (Epic A · A2)。
"""

from __future__ import annotations

from ide4ai.environment.terminal.policy.rule import BashRule, RuleEffect, RuleKind


class TestBashRuleFactories:
    def test_allow_prefix(self) -> None:
        r = BashRule.allow_prefix("ls", reason="whitelisted")
        assert r.pattern == "ls"
        assert r.kind is RuleKind.PREFIX
        assert r.effect is RuleEffect.ALLOW
        assert r.reason == "whitelisted"

    def test_deny_prefix(self) -> None:
        r = BashRule.deny_prefix("git push")
        assert r.kind is RuleKind.PREFIX
        assert r.effect is RuleEffect.DENY

    def test_allow_exact(self) -> None:
        r = BashRule.allow_exact("pwd")
        assert r.kind is RuleKind.EXACT
        assert r.effect is RuleEffect.ALLOW

    def test_deny_exact(self) -> None:
        r = BashRule.deny_exact("rm -rf /")
        assert r.kind is RuleKind.EXACT
        assert r.effect is RuleEffect.DENY


class TestBashRuleMatches:
    def test_prefix_matches_single_word(self) -> None:
        r = BashRule.allow_prefix("ls")
        assert r.matches("ls", "ls -la /home")

    def test_prefix_matches_two_words(self) -> None:
        r = BashRule.allow_prefix("git commit")
        assert r.matches("git commit", "git commit -m fix")

    def test_prefix_does_not_match_different_command(self) -> None:
        r = BashRule.allow_prefix("ls")
        assert not r.matches("cat", "cat /tmp")

    def test_prefix_does_not_match_substring(self) -> None:
        """`git` 规则不应匹配 `gitk`——要求前缀后接空格或恰等。"""
        r = BashRule.allow_prefix("git")
        assert r.matches("git", "git status")
        assert r.matches("git commit", "git commit")
        assert not r.matches("gitk", "gitk")

    def test_exact_requires_full_match(self) -> None:
        r = BashRule.allow_exact("pwd")
        assert r.matches("pwd", "pwd")
        assert not r.matches("pwd", "pwd /tmp")

    def test_prefix_empty_input(self) -> None:
        r = BashRule.allow_prefix("ls")
        assert not r.matches("", "")
