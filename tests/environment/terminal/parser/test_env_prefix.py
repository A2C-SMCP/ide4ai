"""
parser/env_prefix.py 单元测试 | Unit tests for parser/env_prefix.py

对应 Jira AS-27 (Epic A · A1)。
"""

from __future__ import annotations

from ide4ai.environment.terminal.parser.env_prefix import (
    DANGEROUS_ENV_VARS,
    SAFE_ENV_VARS,
    extract_env_prefix,
)


class TestExtractEnvPrefix:
    def test_empty(self) -> None:
        assert extract_env_prefix([]) == ({}, [])

    def test_no_prefix(self) -> None:
        assert extract_env_prefix(["ls", "-la"]) == ({}, ["ls", "-la"])

    def test_single_prefix(self) -> None:
        assert extract_env_prefix(["NODE_ENV=prod", "npm"]) == ({"NODE_ENV": "prod"}, ["npm"])

    def test_multiple_prefix(self) -> None:
        env, rest = extract_env_prefix(["A=1", "B=2", "C=3", "cmd"])
        assert env == {"A": "1", "B": "2", "C": "3"}
        assert rest == ["cmd"]

    def test_empty_value_allowed(self) -> None:
        assert extract_env_prefix(["EMPTY=", "cmd"]) == ({"EMPTY": ""}, ["cmd"])

    def test_equals_in_value(self) -> None:
        """`KEY=a=b` 应当把 `a=b` 作为 value，不进一步切分。"""
        assert extract_env_prefix(["K=a=b", "cmd"]) == ({"K": "a=b"}, ["cmd"])

    def test_invalid_name_not_parsed(self) -> None:
        """`1INVALID=x` 不是合法 env 名（以数字开头），不应被识别。"""
        assert extract_env_prefix(["1INVALID=x", "cmd"]) == ({}, ["1INVALID=x", "cmd"])

    def test_prefix_only(self) -> None:
        env, rest = extract_env_prefix(["NODE_ENV=prod"])
        assert env == {"NODE_ENV": "prod"}
        assert rest == []


class TestConstantSets:
    def test_safe_env_contains_common_behavior_vars(self) -> None:
        assert "NODE_ENV" in SAFE_ENV_VARS
        assert "RUST_LOG" in SAFE_ENV_VARS
        assert "LANG" in SAFE_ENV_VARS

    def test_dangerous_env_contains_path_hijacking(self) -> None:
        assert "PATH" in DANGEROUS_ENV_VARS
        assert "LD_PRELOAD" in DANGEROUS_ENV_VARS
        assert "DYLD_INSERT_LIBRARIES" in DANGEROUS_ENV_VARS
        assert "PYTHONPATH" in DANGEROUS_ENV_VARS
        assert "NODE_OPTIONS" in DANGEROUS_ENV_VARS

    def test_safe_and_dangerous_are_disjoint(self) -> None:
        assert not (SAFE_ENV_VARS & DANGEROUS_ENV_VARS)
