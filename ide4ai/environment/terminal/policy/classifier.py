"""
命令前缀抽取 | Command prefix extraction

从 `ParsedCommand` 中抽取用于规则匹配的前缀：
- `get_simple_command_prefix(parsed)` —— 若第二 token 像子命令，返回 `"cmd subcmd"`；否则 None
- `get_first_word_prefix(parsed)` —— 兜底：返回 `cmd`

这两函数合起来实现"从命令结构化对象 → 可用于规则 key 的字符串"。

Epic B 会在此引入危险 env / 裸 shell 的拒绝逻辑。
"""

from __future__ import annotations

from ide4ai.environment.terminal.parser.command_ast import ParsedCommand

__all__ = [
    "get_first_word_prefix",
    "get_simple_command_prefix",
]


def get_first_word_prefix(parsed: ParsedCommand) -> str | None:
    """
    返回 `command_name` 本身作为兜底前缀；空命令返回 None。

    Args:
        parsed: 解析过的命令

    Returns:
        首词前缀 | First-word prefix

    Examples:
        >>> from ide4ai.environment.terminal.parser.tokenizer import parse_command_line
        >>> p = parse_command_line("ls -la")
        >>> get_first_word_prefix(p)  # type: ignore[arg-type]
        'ls'
    """
    if parsed.is_empty:
        return None
    return parsed.command_name


def get_simple_command_prefix(parsed: ParsedCommand) -> str | None:
    """
    若 `parsed.subcommand` 存在（tokenizer 已判过 "像子命令"），返回 `"cmd subcmd"`；
    否则返回 None。

    注意：Epic B 会补充"含危险 env 时禁止生成前缀规则"的逻辑——那时会返回 None 以强制走 ask。

    Args:
        parsed: 解析过的命令

    Returns:
        两段前缀或 None

    Examples:
        >>> from ide4ai.environment.terminal.parser.tokenizer import parse_command_line
        >>> p = parse_command_line("git commit -m x")
        >>> get_simple_command_prefix(p)  # type: ignore[arg-type]
        'git commit'
        >>> p2 = parse_command_line("ls -la")
        >>> get_simple_command_prefix(p2)  # type: ignore[arg-type]
        # None
    """
    if parsed.is_empty:
        return None
    if parsed.subcommand:
        return f"{parsed.command_name} {parsed.subcommand}"
    return None


def extract_prefix(parsed: ParsedCommand) -> str | None:
    """
    综合：先 simple（两段）再 fallback 一段。仅供内部使用。
    """
    return get_simple_command_prefix(parsed) or get_first_word_prefix(parsed)
