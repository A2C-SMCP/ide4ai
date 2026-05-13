"""
命令 Tokenizer & 顶层解析器 | Command tokenizer & top-level parser

提供：
1. `tokenize(s)` —— 返回保留 operator 的 token 序列（`&&/||/;/|/&`）；
2. `parse_command_line(s)` —— 返回 `SegmentNode`：`ParsedCommand` /
   `CompoundCommand` / `PipelineCommand`，env_prefix 已剥离。

Epic A 使用 `shlex`（POSIX 模式）作为主力分词器；operator 先用正则占位切分，
然后每段交给 shlex。这不能 100% 覆盖 `bash` 完整语法，但足够本 Epic 的目标
（AS-20 repro `ls -la /home`、`cd / && rm x`、`a | b` 等常见场景）。

Epic D 若引入 `tree-sitter-bash` 可替换本层核心算法，但对外 API 保持兼容。
"""

from __future__ import annotations

import re
import shlex
from typing import Final

from ide4ai.environment.terminal.parser.command_ast import (
    CompoundCommand,
    ParsedCommand,
    PipelineCommand,
    SegmentNode,
)
from ide4ai.environment.terminal.parser.env_prefix import extract_env_prefix
from ide4ai.environment.terminal.parser.wrapper_peel import peel_wrappers

__all__ = [
    "parse_command_line",
    "tokenize",
]


# Compound 操作符（优先级：`;` < `&&` = `||`）。Epic A 不区分短路语义，按出现顺序保留。
_COMPOUND_OPS: Final[tuple[str, ...]] = ("&&", "||", ";")
# 管道操作符
_PIPE_OP: Final[str] = "|"


# 识别 shell operator 的 regex。需要避开引号中的 operator——shlex 会把引号内容保留为单一 token，
# 所以我们先用 shlex 的 `posix=True, punctuation_chars=True` 模式直接分词。
# 参考：https://docs.python.org/3/library/shlex.html#shlex.shlex.punctuation_chars


def tokenize(command_line: str) -> list[str]:
    """
    分词，保留 operator token（`&&/||/;/|/&`）。

    使用 `shlex` 的 `punctuation_chars=True` 模式——能识别引号与转义，同时把
    `&&` / `||` 等视作独立 token。

    Args:
        command_line: 原始 shell 命令行

    Returns:
        token 列表（含 operator）；空输入返回 []

    Raises:
        ValueError: 引号不平衡等 shlex 无法解析的情况

    Examples:
        >>> tokenize("ls -la")
        ['ls', '-la']
        >>> tokenize("cd / && ls")
        ['cd', '/', '&&', 'ls']
        >>> tokenize("a | b | c")
        ['a', '|', 'b', '|', 'c']
        >>> tokenize("echo \\"a;b\\" ; c")
        ['echo', 'a;b', ';', 'c']
    """
    if not command_line or not command_line.strip():
        return []
    lexer = shlex.shlex(command_line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as e:  # 引号不平衡等 | Unbalanced quotes etc.
        raise ValueError(f"Failed to tokenize command: {command_line!r} ({e})") from e
    return tokens


def _split_by_operators(tokens: list[str], operators: tuple[str, ...]) -> tuple[list[list[str]], list[str]]:
    """
    根据给定 operator 集合把 token 序列切片。

    Returns:
        (segments, ops) —— segments[i] / ops[i] / segments[i+1] / ops[i+1] / ...
        空段会被保留（由上层过滤）。
    """
    segments: list[list[str]] = [[]]
    ops: list[str] = []
    for t in tokens:
        if t in operators:
            ops.append(t)
            segments.append([])
        else:
            segments[-1].append(t)
    return segments, ops


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


def parse_command_line(command_line: str) -> SegmentNode:
    """
    解析 shell 命令行为顶层 AST 节点。

    返回值可能是：
    - `ParsedCommand` —— 单条命令（含 env prefix、subcommand、args）
    - `PipelineCommand` —— 纯管道（`a | b`）
    - `CompoundCommand` —— 含 `&&/||/;` 的复合；管道段会作为内部 `PipelineCommand`

    空输入返回 `ParsedCommand(command_name="", raw="")`（`is_empty=True`）。

    Args:
        command_line: 原始 shell 命令行

    Returns:
        顶层 AST 节点

    Raises:
        ValueError: 分词失败（如引号不平衡）
    """
    tokens = tokenize(command_line)
    if not tokens:
        return ParsedCommand(command_name="", raw=command_line)

    # 先按 compound ops 切；剩下是纯 pipeline 或叶子
    compound_segs, compound_ops = _split_by_operators(tokens, _COMPOUND_OPS)
    # 过滤空段（如开头有 `;` 会产生空段）
    filtered_segs: list[list[str]] = []
    filtered_ops: list[str] = []
    for idx, seg in enumerate(compound_segs):
        if seg:
            filtered_segs.append(seg)
            # 前一个 op 保留（除第 0 段外）
            if idx > 0 and idx - 1 < len(compound_ops):
                filtered_ops.append(compound_ops[idx - 1])
    if not filtered_segs:
        return ParsedCommand(command_name="", raw=command_line)

    segment_nodes: list[SegmentNode] = [_parse_segment(seg, command_line) for seg in filtered_segs]

    if len(segment_nodes) == 1:
        return segment_nodes[0]
    return CompoundCommand(segments=segment_nodes, operators=filtered_ops)


def _parse_segment(tokens: list[str], raw: str) -> SegmentNode:
    """
    解析单个 compound 段：可能是 pipeline 或单条命令。
    """
    pipe_segs, _ = _split_by_operators(tokens, (_PIPE_OP,))
    pipe_segs = [s for s in pipe_segs if s]
    if len(pipe_segs) == 1:
        return _parse_leaf(pipe_segs[0], raw)
    stages: list[SegmentNode] = [_parse_leaf(s, raw) for s in pipe_segs]
    return PipelineCommand(stages=stages)
