"""
终端命令解析层 | Terminal command parser layer

把字符串命令抬升成结构化对象（语法树）。
后续 policy / security 层都基于 AST 做判断，避免字符串匹配的陷阱。
"""

from ide4ai.environment.terminal.parser.command_ast import (
    CompoundCommand,
    ParsedCommand,
    PipelineCommand,
    SegmentNode,
)
from ide4ai.environment.terminal.parser.env_prefix import (
    SAFE_ENV_VARS,
    extract_env_prefix,
)
from ide4ai.environment.terminal.parser.tokenizer import (
    parse_command_line,
    tokenize,
)
from ide4ai.environment.terminal.parser.wrapper_peel import peel_wrappers

__all__ = [
    "CompoundCommand",
    "ParsedCommand",
    "PipelineCommand",
    "SAFE_ENV_VARS",
    "SegmentNode",
    "extract_env_prefix",
    "parse_command_line",
    "peel_wrappers",
    "tokenize",
]
