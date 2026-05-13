"""
execution/run_result.py 单元测试 | Unit tests for execution/run_result.py

对应 Jira AS-32 (Epic A · A6)。
"""

from __future__ import annotations

from ide4ai.environment.terminal.execution.run_result import StepResult


class TestStepResultDefaults:
    def test_minimal_construction(self) -> None:
        r = StepResult(exit_code=0, success=True, output="hello")
        assert r.exit_code == 0
        assert r.success is True
        assert r.output == "hello"
        assert r.truncated is False
        assert r.cwd == ""
        assert r.duration_ms == 0
        assert r.original_length is None
        assert r.extra == {}


class TestStepResultToInfo:
    def test_to_info_contains_all_standard_fields(self) -> None:
        r = StepResult(
            exit_code=0,
            success=True,
            output="done",
            truncated=False,
            cwd="/tmp",
            duration_ms=42,
        )
        info = r.to_info()
        for key in ("exit_code", "success", "output", "truncated", "cwd", "duration_ms", "original_length"):
            assert key in info
        assert info["exit_code"] == 0
        assert info["cwd"] == "/tmp"
        assert info["duration_ms"] == 42

    def test_to_info_flattens_extra(self) -> None:
        r = StepResult(exit_code=1, success=False, output="", extra={"task_id": "abc", "decision": "allow"})
        info = r.to_info()
        assert info["task_id"] == "abc"
        assert info["decision"] == "allow"

    def test_to_info_extra_does_not_overwrite_standard(self) -> None:
        r = StepResult(exit_code=0, success=True, output="", extra={"exit_code": 99})
        info = r.to_info()
        # 标准字段优先
        assert info["exit_code"] == 0
