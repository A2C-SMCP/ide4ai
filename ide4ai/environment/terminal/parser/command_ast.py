"""
命令语法树定义 | Command AST definitions

核心约定（见 AS-20 评论的"数据模型"结论）：
- 一行 shell 不是字符串，是可能嵌套的 `SegmentNode`；
- 叶子节点 `ParsedCommand` 带 env_prefix / wrappers / command_name / subcommand / args；
- `CompoundCommand` 用 `&&/||/;` 连接多段；`PipelineCommand` 用 `|` 连接。

Epic A 只需要字段占位 + 简单构造；Epic B 的 security 层会在此基础上做递归 peel。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "CompoundCommand",
    "ParsedCommand",
    "PipelineCommand",
    "SegmentNode",
]


@dataclass(slots=True)
class ParsedCommand:
    """
    单条命令的结构化表示 | Structured representation of a single command

    Attributes:
        command_name: 主命令名（剥离 env / wrappers 后）| Main command name (after env/wrapper peel)
        subcommand: 子命令（第二个 token，如 `git commit` 的 `commit`）；可能为 None
        args: 剩余参数（不含 command/subcommand 本身）
        env_prefix: 开头剥离的 `VAR=value`（如 `NODE_ENV=prod npm run`）；key=变量名
        wrappers: 被剥离的包装器链（如 `env`, `sudo`, `timeout`）；Epic A 暂留空
        raw: 原始（未剥离）的命令字符串；用于调试与错误提示
    """

    command_name: str
    subcommand: str | None = None
    args: list[str] = field(default_factory=list)
    env_prefix: dict[str, str] = field(default_factory=dict)
    wrappers: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def is_empty(self) -> bool:
        """空命令（纯 env prefix 或空输入）| Empty command (only env prefix or empty input)"""
        return not self.command_name


@dataclass(slots=True)
class CompoundCommand:
    """
    复合命令：用 `&&/||/;` 连接多段 | Compound command joined by `&&/||/;`

    Attributes:
        segments: 顺序排列的段（ParsedCommand / PipelineCommand / 子 Compound）
        operators: 段间操作符（长度 = len(segments) - 1；取值 `&&` / `||` / `;`）
    """

    segments: list[SegmentNode]
    operators: list[str]


@dataclass(slots=True)
class PipelineCommand:
    """
    管道命令：用 `|` 连接多段 | Pipeline command joined by `|`

    Attributes:
        stages: 管道各阶段（通常都是 ParsedCommand）
    """

    stages: list[SegmentNode]


# 语法树节点的 Union 类型别名 | Union alias for AST nodes.
SegmentNode = ParsedCommand | CompoundCommand | PipelineCommand
