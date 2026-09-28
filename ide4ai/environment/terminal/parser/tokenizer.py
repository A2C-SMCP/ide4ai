"""Bash syntax-tree adapter for the existing terminal policy AST.

The parser retains quoting, statement boundaries, redirects and substitutions.
Syntax errors fail closed; no fallback treats unparsed shell text as one command.
"""

from __future__ import annotations

import re
import shlex
from typing import Final

import tree_sitter_bash
from tree_sitter import Language, Node, Parser

from ide4ai.environment.terminal.parser.command_ast import (
    CompoundCommand,
    ParsedCommand,
    PipelineCommand,
    SegmentNode,
)
from ide4ai.environment.terminal.parser.env_prefix import extract_env_prefix
from ide4ai.environment.terminal.parser.wrapper_peel import peel_wrappers

__all__ = ["parse_command_line", "tokenize"]
_LANGUAGE = Language(tree_sitter_bash.language())


def _syntax(command: str) -> Node:
    root = Parser(_LANGUAGE).parse(command.encode("utf-8")).root_node
    if root.has_error:
        raise ValueError("Failed to tokenize Bash command: invalid or unsupported syntax")
    return root


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8")


def _word(node: Node) -> str:
    text = _text(node)
    if node.type == "raw_string":
        return text[1:-1]

    # Shell removes escaped physical newlines before word splitting, except
    # inside single quotes. Apply that rule to syntax leaves, preserving quotes.
    def continuation(child: Node) -> str:
        if child.type == "raw_string":
            return _text(child)
        if not child.children:
            return _text(child).replace("\\\n", "")
        source = _text(child)
        encoded = source.encode()
        result = b""
        start = child.start_byte
        for part in child.children:
            result += encoded[start - child.start_byte : part.start_byte - child.start_byte].replace(b"\\\n", b"")
            result += continuation(part).encode()
            start = part.end_byte
        result += encoded[start - child.start_byte :].replace(b"\\\n", b"")
        return result.decode()

    text = continuation(node)
    try:
        words = shlex.split(text, comments=False, posix=True)
    except ValueError as exc:
        raise ValueError("Failed to tokenize Bash word") from exc
    return " ".join(words)


def tokenize(command_line: str) -> list[str]:
    """Compatibility token view; policy parsing uses the syntax tree directly."""
    root = _syntax(command_line)
    words: list[str] = []

    def visit(node: Node) -> None:
        if node.type in {"word", "number", "string", "raw_string", "concatenation", "variable_assignment"}:
            words.append(_word(node))
        elif node.type not in {"comment", "heredoc_body", "heredoc_start", "heredoc_end"}:
            if not node.children and _text(node) in {"&&", "||", ";", "|", "&"}:
                words.append(_text(node))
            for child in node.children:
                visit(child)

    visit(root)
    return words


def _parse_leaf(tokens: list[str], raw: str) -> ParsedCommand:
    """
    把一段已无 operator 的 token 序列构造成 `ParsedCommand`。

    - 先剥 env prefix；再 stub peel wrappers（Epic A 无动作）；
    - 第一个剩余 token 作为 command_name；若第二个 token 长得像子命令（全小写字母/数字/连字符），
      则视为 subcommand，其余为 args；否则无 subcommand，全部剩余作为 args。
    """
    env, rest = extract_env_prefix(tokens)
    wrappers, rest = peel_wrappers(rest)
    if not rest:
        return ParsedCommand(command_name="", env_prefix=env, wrappers=wrappers, raw=raw)
    command_name = rest[0]
    args_start = 1
    subcommand: str | None = None
    if len(rest) >= 2 and _looks_like_subcommand(rest[1]):
        subcommand = rest[1]
        args_start = 2
    return ParsedCommand(
        command_name=command_name,
        subcommand=subcommand,
        args=list(rest[args_start:]),
        env_prefix=env,
        wrappers=wrappers,
        raw=raw,
    )


_SUBCOMMAND_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# 允许被识别为子命令的最小长度。1-2 字符 token 往往是 grep 搜索模式、单字母 flag、
# `sed s/...` 的脚本参数等；放宽容易误把 `grep x` 识成 `grep.x` 子命令。
_MIN_SUBCOMMAND_LEN: Final[int] = 3


def _looks_like_subcommand(tok: str) -> bool:
    """
    判断 token 是否 "长得像子命令"（全小写字母/数字/连字符，不含点/斜杠/下划线），
    且长度 >= 3（避开 `grep x` / `sed s` / `docker ps` 这类歧义）。

    排除 flag（`-la`）、路径（`/tmp`、`./foo`）、文件（`file.txt`）、数字（`133`）、
    极短 token（`x`、`ps`）。
    """
    return len(tok) >= _MIN_SUBCOMMAND_LEN and bool(_SUBCOMMAND_RE.match(tok))


def _combine(nodes: list[SegmentNode], operators: list[str] | None = None) -> SegmentNode:
    if not nodes:
        return ParsedCommand(command_name="", raw="")
    if len(nodes) == 1:
        return nodes[0]
    return CompoundCommand(segments=nodes, operators=operators or [";"] * (len(nodes) - 1))


def _nested_commands(node: Node) -> list[SegmentNode]:
    result: list[SegmentNode] = []
    if node.type == "heredoc_redirect":
        delimiter = next(child for child in node.named_children if child.type == "heredoc_start")
        body = next((child for child in node.named_children if child.type == "heredoc_body"), None)
        quoted = any(character in _text(delimiter) for character in "\\\"'")
        # tree-sitter-bash 0.25 does not represent backtick substitutions in
        # heredoc bodies. Reject unmodeled execution rather than treating it as data.
        if not quoted and body is not None and re.search(r"(?<!\\)(?:\\\\)*`", _text(body)):
            raise ValueError("Backtick expansion in an unquoted heredoc cannot be checked")
    for child in node.named_children:
        if child.type in {"command_substitution", "process_substitution"}:
            result.append(_adapt(child))
        else:
            result.extend(_nested_commands(child))
    return result


def _adapt(node: Node) -> SegmentNode:
    if node.type == "comment":
        return _combine([])
    if node.type == "command":
        name = node.child_by_field_name("name")
        if name is None or any(
            child.type not in {"word", "raw_string", "string", "concatenation", "string_content"}
            for child in _descendants(name)
        ):
            raise ValueError("Dynamic command names cannot be checked by the command filter")
        tokens = [_word(child) for child in node.named_children if child.type == "variable_assignment"]
        tokens.append(_word(name))
        tokens.extend(_word(child) for child in node.children_by_field_name("argument"))
        return _combine([_parse_leaf(tokens, _text(node)), *_nested_commands(node)])
    if node.type == "variable_assignment":
        return _combine([_parse_leaf([_word(node)], _text(node)), *_nested_commands(node)])
    if node.type == "redirected_statement":
        body = node.child_by_field_name("body")
        nodes = [_adapt(body)] if body is not None else []
        for child in node.named_children:
            if child != body:
                nodes.extend(_nested_commands(child))
        return _combine(nodes)
    if node.type in {
        "program",
        "list",
        "pipeline",
        "subshell",
        "compound_statement",
        "command_substitution",
        "process_substitution",
    }:
        nodes = [_adapt(child) for child in node.named_children if child.type != "comment"]
        if node.type == "pipeline" and len(nodes) > 1:
            return PipelineCommand(stages=nodes)
        operators = [_text(child) for child in node.children if _text(child) in {"&&", "||", ";", "&"}]
        return _combine(nodes, operators if len(operators) == len(nodes) - 1 else None)
    raise ValueError(f"Unsupported Bash syntax for command filtering: {node.type}")


def _descendants(node: Node) -> list[Node]:
    return [child for item in node.named_children for child in [item, *_descendants(item)]]


def parse_command_line(command_line: str) -> SegmentNode:
    """Return policy nodes for every executable command, including substitutions.

    Heredoc bodies remain data; executable substitutions in unquoted bodies are
    checked. Unsupported control flow and malformed trees are rejected, never
    silently flattened. This compatibility filter is not a shell sandbox.
    """
    return _adapt(_syntax(command_line))
