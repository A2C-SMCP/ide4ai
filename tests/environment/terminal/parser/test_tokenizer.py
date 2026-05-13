"""
parser/tokenizer.py 单元测试 | Unit tests for parser/tokenizer.py

对应 Jira AS-27 (Epic A · A1)。
"""

from __future__ import annotations

import pytest

from ide4ai.environment.terminal.parser import (
    CompoundCommand,
    ParsedCommand,
    PipelineCommand,
    parse_command_line,
    tokenize,
)


class TestTokenize:
    """基础分词 | Basic tokenization"""

    def test_empty(self) -> None:
        assert tokenize("") == []

    def test_whitespace_only(self) -> None:
        assert tokenize("   ") == []

    def test_single_word(self) -> None:
        assert tokenize("ls") == ["ls"]

    def test_command_with_flags(self) -> None:
        assert tokenize("ls -la /home") == ["ls", "-la", "/home"]

    def test_quoted_args_preserved_as_single_token(self) -> None:
        assert tokenize('echo "a b c"') == ["echo", "a b c"]

    def test_single_quoted_preserved(self) -> None:
        assert tokenize("echo 'a;b'") == ["echo", "a;b"]

    def test_escape_sequences(self) -> None:
        assert tokenize(r"echo hello\ world") == ["echo", "hello world"]

    def test_operators_as_separate_tokens(self) -> None:
        assert tokenize("cd / && ls") == ["cd", "/", "&&", "ls"]

    def test_pipe_token(self) -> None:
        assert tokenize("a | b | c") == ["a", "|", "b", "|", "c"]

    def test_semicolon_token(self) -> None:
        assert tokenize("echo a ; echo b") == ["echo", "a", ";", "echo", "b"]

    def test_or_operator(self) -> None:
        assert tokenize("a || b") == ["a", "||", "b"]

    def test_unbalanced_quotes_raises(self) -> None:
        with pytest.raises(ValueError, match="Failed to tokenize"):
            tokenize('echo "unclosed')


class TestParseCommandLineLeaf:
    """单条命令解析 | Single-command parsing"""

    def test_empty_returns_empty_parsed(self) -> None:
        p = parse_command_line("")
        assert isinstance(p, ParsedCommand)
        assert p.is_empty

    def test_simple_command(self) -> None:
        p = parse_command_line("ls")
        assert isinstance(p, ParsedCommand)
        assert p.command_name == "ls"
        assert p.subcommand is None
        assert p.args == []
        assert p.env_prefix == {}

    def test_command_with_flags(self) -> None:
        """AS-20 repro：`ls -la /home` 必须解析出 command_name='ls'，而非整串。"""
        p = parse_command_line("ls -la /home")
        assert isinstance(p, ParsedCommand)
        assert p.command_name == "ls"
        assert p.subcommand is None  # `-la` 不像子命令
        assert p.args == ["-la", "/home"]

    def test_command_with_subcommand(self) -> None:
        p = parse_command_line("git commit -m fix")
        assert isinstance(p, ParsedCommand)
        assert p.command_name == "git"
        assert p.subcommand == "commit"
        assert p.args == ["-m", "fix"]

    def test_env_prefix_stripped(self) -> None:
        p = parse_command_line("NODE_ENV=prod npm run build")
        assert isinstance(p, ParsedCommand)
        assert p.command_name == "npm"
        assert p.subcommand == "run"
        assert p.args == ["build"]
        assert p.env_prefix == {"NODE_ENV": "prod"}

    def test_multiple_env_prefix(self) -> None:
        p = parse_command_line("A=1 B=2 echo x")
        assert isinstance(p, ParsedCommand)
        assert p.command_name == "echo"
        assert p.env_prefix == {"A": "1", "B": "2"}

    def test_env_prefix_only_is_empty(self) -> None:
        p = parse_command_line("NODE_ENV=prod")
        assert isinstance(p, ParsedCommand)
        assert p.is_empty
        assert p.env_prefix == {"NODE_ENV": "prod"}

    def test_flag_not_mistaken_for_subcommand(self) -> None:
        p = parse_command_line("ls --all")
        assert isinstance(p, ParsedCommand)
        assert p.subcommand is None
        assert p.args == ["--all"]

    def test_path_not_mistaken_for_subcommand(self) -> None:
        p = parse_command_line("cat /etc/hosts")
        assert isinstance(p, ParsedCommand)
        assert p.subcommand is None

    def test_number_not_mistaken_for_subcommand(self) -> None:
        p = parse_command_line("sleep 10")
        assert isinstance(p, ParsedCommand)
        assert p.subcommand is None

    def test_dotted_token_not_subcommand(self) -> None:
        p = parse_command_line("python script.py")
        assert isinstance(p, ParsedCommand)
        assert p.subcommand is None


class TestParseCommandLinePipeline:
    """管道解析 | Pipeline parsing"""

    def test_simple_pipeline(self) -> None:
        p = parse_command_line("ls | grep x")
        assert isinstance(p, PipelineCommand)
        assert len(p.stages) == 2
        s1, s2 = p.stages
        assert isinstance(s1, ParsedCommand)
        assert isinstance(s2, ParsedCommand)
        assert s1.command_name == "ls"
        assert s2.command_name == "grep"
        assert s2.args == ["x"]

    def test_three_stage_pipeline(self) -> None:
        p = parse_command_line("a | b | c")
        assert isinstance(p, PipelineCommand)
        assert len(p.stages) == 3


class TestParseCommandLineCompound:
    """复合命令解析 | Compound parsing"""

    def test_and_chain(self) -> None:
        p = parse_command_line("cd /tmp && ls")
        assert isinstance(p, CompoundCommand)
        assert p.operators == ["&&"]
        assert len(p.segments) == 2
        s1, s2 = p.segments
        assert isinstance(s1, ParsedCommand)
        assert s1.command_name == "cd"
        assert isinstance(s2, ParsedCommand)
        assert s2.command_name == "ls"

    def test_semicolon_chain(self) -> None:
        p = parse_command_line("echo a ; echo b")
        assert isinstance(p, CompoundCommand)
        assert p.operators == [";"]
        assert len(p.segments) == 2

    def test_mixed_compound_and_pipe(self) -> None:
        """`a | b && c` → Compound([Pipeline([a, b]), c], ["&&"])"""
        p = parse_command_line("a | b && c")
        assert isinstance(p, CompoundCommand)
        assert p.operators == ["&&"]
        assert len(p.segments) == 2
        pipe_seg, leaf_seg = p.segments
        assert isinstance(pipe_seg, PipelineCommand)
        assert len(pipe_seg.stages) == 2
        assert isinstance(leaf_seg, ParsedCommand)
        assert leaf_seg.command_name == "c"

    def test_leading_operator_ignored(self) -> None:
        p = parse_command_line("; echo a")
        assert isinstance(p, ParsedCommand)
        assert p.command_name == "echo"

    def test_or_operator(self) -> None:
        p = parse_command_line("make test || echo failed")
        assert isinstance(p, CompoundCommand)
        assert p.operators == ["||"]
