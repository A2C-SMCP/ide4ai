"""
命令 env 前缀剥离 | Command env-prefix stripping

从命令行开头剥离 `VAR=value` 形式的环境变量赋值，返回 (env_dict, 剩余 tokens)。

Epic A 范围：
- 只剥离、不判断安全性；`SAFE_ENV_VARS` 常量先放着，Epic B 的 policy 层使用；
- 不识别引号（`VAR="a b"` 这种复杂场景留给后续；shlex 已处理基本引号）。
"""

from __future__ import annotations

import re
from typing import Final

__all__ = [
    "DANGEROUS_ENV_VARS",
    "SAFE_ENV_VARS",
    "extract_env_prefix",
]


# 合法 env 赋值形态：`NAME=value` 或 `NAME=`（允许空值）；NAME 只允许字母/数字/下划线 且不以数字开头
_ENV_ASSIGN_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


# 认为"只影响行为、不执行代码、不影响加载路径"的 env 变量白名单。
# Epic A 暂不消费；Epic B 用它判断前缀是否可剥离（可剥离 → 生成前缀规则；否则强制 ask）。
SAFE_ENV_VARS: Final[frozenset[str]] = frozenset(
    {
        "NODE_ENV",
        "GOOS",
        "GOARCH",
        "RUST_LOG",
        "RUST_BACKTRACE",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "TZ",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "CI",
        "DEBUG",
        "VERBOSE",
        "FORCE_COLOR",
        "NO_COLOR",
        "TERM",
        "COLUMNS",
        "LINES",
    }
)


# 能执行代码 / 改变加载路径 / 劫持解释器的 env 变量——永远不能被规则放行。
# Epic A 暂不消费；Epic B 用它把命令强制打到 ask。
DANGEROUS_ENV_VARS: Final[frozenset[str]] = frozenset(
    {
        "PATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONHOME",
        "NODE_PATH",
        "NODE_OPTIONS",
        "GOFLAGS",
        "RUSTFLAGS",
        "SHELL",
        "BASH_ENV",
        "ENV",
        "IFS",
    }
)


def extract_env_prefix(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    """
    从 token 序列开头剥离 `VAR=value` 形式的 env 前缀。

    Args:
        tokens: 命令 token 序列（由 `tokenizer.tokenize` 产出）

    Returns:
        (env_dict, remaining_tokens) —— env_dict 保留原始顺序由 dict（Py3.7+）保证

    Examples:
        >>> extract_env_prefix(["NODE_ENV=prod", "npm", "run", "build"])
        ({'NODE_ENV': 'prod'}, ['npm', 'run', 'build'])
        >>> extract_env_prefix(["ls", "-la"])
        ({}, ['ls', '-la'])
        >>> extract_env_prefix([])
        ({}, [])
    """
    env: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        m = _ENV_ASSIGN_RE.match(tokens[i])
        if m is None:
            break
        env[m.group(1)] = m.group(2)
        i += 1
    return env, tokens[i:]
