"""
CommandFilterConfig shim（AS-29 A3）单元测试

确认旧 API 行为不变 + AS-20 的根因被修复：带参数命令不再被误拦截。
"""

from __future__ import annotations

import warnings

import pytest

from ide4ai.environment.terminal.command_filter import (
    DEFAULT_BLACK_LIST,
    CommandFilterConfig,
)


class TestAS20RootFixViaShim:
    """AS-20 根因修复：带参数命令应通过白名单校验"""

    def test_bare_command_allowed(self) -> None:
        cfg = CommandFilterConfig.from_white_list(["ls", "pwd"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("ls") is True

    def test_command_with_args_allowed_as_single_string(self) -> None:
        """AS-20 repro 的核心：`"ls -la /home"` 当作整串传入也应通过。"""
        cfg = CommandFilterConfig.from_white_list(["ls", "pwd"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("ls -la /home") is True

    def test_non_whitelisted_command_rejected(self) -> None:
        cfg = CommandFilterConfig.from_white_list(["ls"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("cat /etc/hosts") is False

    def test_subcommand_prefix_supported(self) -> None:
        """旧白名单是单 token 语义；`"git"` 应放行 `git commit -m x`。"""
        cfg = CommandFilterConfig.from_white_list(["git"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("git commit -m fix") is True


class TestBacklistCompat:
    def test_default_blacklist_blocks_rm(self) -> None:
        cfg = CommandFilterConfig.allow_all_except()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("rm -rf /") is False

    def test_default_blacklist_allows_unlisted(self) -> None:
        cfg = CommandFilterConfig.allow_all_except()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("echo hello") is True

    def test_allow_all(self) -> None:
        cfg = CommandFilterConfig.allow_all()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("anything_goes") is True

    def test_custom_blacklist(self) -> None:
        cfg = CommandFilterConfig.allow_all_except(["dangerous"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("dangerous") is False
            assert cfg.is_allowed("echo") is True

    def test_default_black_list_still_exported(self) -> None:
        """下游代码 import DEFAULT_BLACK_LIST 的兼容性。"""
        assert "rm" in DEFAULT_BLACK_LIST
        assert "dd" in DEFAULT_BLACK_LIST


class TestRejectionReason:
    def test_whitelist_miss_reason(self) -> None:
        cfg = CommandFilterConfig.from_white_list(["ls"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            reason = cfg.get_rejection_reason("cat")
        assert "not in whitelist" in reason

    def test_blacklist_hit_reason(self) -> None:
        cfg = CommandFilterConfig.allow_all_except(["rm"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            reason = cfg.get_rejection_reason("rm -rf /")
        assert "blacklist" in reason


class TestDeprecationWarning:
    def test_emitted_once_per_instance(self) -> None:
        cfg = CommandFilterConfig.from_white_list(["ls"])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            cfg.is_allowed("ls")
            cfg.is_allowed("ls -la")
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) == 1

    def test_from_whitelist_defers_warning_until_use(self) -> None:
        """构造本身不 warn；只在 is_allowed/get_rejection_reason 首次调用时 warn。"""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            cfg = CommandFilterConfig.from_white_list(["ls"])
            assert not any(issubclass(w.category, DeprecationWarning) for w in caught)
            cfg.is_allowed("ls")
            assert any(issubclass(w.category, DeprecationWarning) for w in caught)


class TestCompoundCommand:
    def test_compound_any_deny_denied(self) -> None:
        """`cd /; rm -rf /` —— rm 被默认黑名单拒 → 整条拒。"""
        cfg = CommandFilterConfig.allow_all_except()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("cd /; rm -rf /") is False

    def test_compound_all_allowed(self) -> None:
        cfg = CommandFilterConfig.allow_all_except()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("echo a && echo b") is True


class TestMalformedInput:
    def test_unbalanced_quotes_rejected(self) -> None:
        cfg = CommandFilterConfig.allow_all()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            # shlex 解析失败 → 拒绝
            assert cfg.is_allowed('echo "unclosed') is False

    def test_empty_string_rejected_in_whitelist_mode(self) -> None:
        cfg = CommandFilterConfig.from_white_list(["ls"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert cfg.is_allowed("") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
