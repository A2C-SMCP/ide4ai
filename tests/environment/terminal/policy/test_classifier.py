"""
policy/classifier.py 单元测试 | Unit tests for policy/classifier.py

对应 Jira AS-28 (Epic A · A2)。
"""

from __future__ import annotations

from ide4ai.environment.terminal.parser import parse_command_line
from ide4ai.environment.terminal.parser.command_ast import ParsedCommand
from ide4ai.environment.terminal.policy.classifier import (
    extract_prefix,
    get_first_word_prefix,
    get_simple_command_prefix,
)


def _leaf(cmd: str) -> ParsedCommand:
    node = parse_command_line(cmd)
    assert isinstance(node, ParsedCommand)
    return node


class TestGetFirstWordPrefix:
    def test_simple(self) -> None:
        assert get_first_word_prefix(_leaf("ls -la")) == "ls"

    def test_empty(self) -> None:
        assert get_first_word_prefix(_leaf("")) is None

    def test_env_only(self) -> None:
        assert get_first_word_prefix(_leaf("NODE_ENV=prod")) is None


class TestGetSimpleCommandPrefix:
    def test_with_subcommand(self) -> None:
        assert get_simple_command_prefix(_leaf("git commit -m x")) == "git commit"

    def test_no_subcommand_returns_none(self) -> None:
        assert get_simple_command_prefix(_leaf("ls -la")) is None

    def test_empty(self) -> None:
        assert get_simple_command_prefix(_leaf("")) is None

    def test_grep_x_no_subcommand(self) -> None:
        """`grep x`：`x` 太短不被当作 subcommand。"""
        assert get_simple_command_prefix(_leaf("grep x")) is None


class TestExtractPrefix:
    def test_prefers_two_word_prefix(self) -> None:
        assert extract_prefix(_leaf("git commit -m x")) == "git commit"

    def test_falls_back_to_first_word(self) -> None:
        assert extract_prefix(_leaf("ls -la")) == "ls"

    def test_empty_is_none(self) -> None:
        assert extract_prefix(_leaf("")) is None
