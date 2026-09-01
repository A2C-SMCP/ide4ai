from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import anyio
import pytest
from mcp.types import CallToolResult, TextContent, Tool

from ide4ai.a2c_smcp.projects import (
    Project,
    ProjectTerminalNotAvailableError,
    ProjectTerminalRuntimeManager,
    ProjectTerminalState,
)


@dataclass
class FakeTerminalRuntime:
    project_name: str
    close_failures: int = 0
    closed: bool = False
    calls: list[tuple[str, Mapping[str, object]]] = field(default_factory=list)
    close_calls: int = 0

    def list_tools(self) -> tuple[Tool, ...]:
        if self.closed:
            raise RuntimeError("closed")
        return (
            Tool(
                name="shell_list",
                inputSchema={"type": "object", "additionalProperties": False},
            ),
        )

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object] | None = None,
    ) -> CallToolResult:
        if self.closed:
            raise RuntimeError("closed")
        captured = dict(arguments or {})
        self.calls.append((name, captured))
        return CallToolResult(
            content=[TextContent(type="text", text=self.project_name)],
            structuredContent={"project": self.project_name, "arguments": captured},
        )

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("cleanup failed")
        self.closed = True


def project(name: str, root: Path) -> Project:
    return Project(id=uuid4(), name=name, root_dir=str(root.resolve()))


@pytest.mark.asyncio
async def test_terminal_runtime_is_project_scoped_and_idempotent(tmp_path: Path) -> None:
    created: list[FakeTerminalRuntime] = []

    async def factory(record: Project) -> FakeTerminalRuntime:
        runtime = FakeTerminalRuntime(record.name)
        created.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = project("first", first_root)
    second = project("second", second_root)

    assert manager.state(first) is ProjectTerminalState.CLOSED
    assert manager.list_tools(first) == ()
    assert await manager.set_enabled(first, enabled=True) is True
    assert await manager.set_enabled(first, enabled=True) is False
    assert [tool.name for tool in manager.list_tools(first)] == ["shell_list"]
    assert manager.list_tools(second) == ()

    result = await manager.call_tool(first, "shell_list", {})
    assert result.structuredContent == {"project": "first", "arguments": {}}
    with pytest.raises(ProjectTerminalNotAvailableError):
        await manager.call_tool(second, "shell_list", {})

    assert await manager.set_enabled(first, enabled=False) is True
    assert await manager.set_enabled(first, enabled=False) is False
    assert created[0].close_calls == 1
    assert manager.state(first) is ProjectTerminalState.CLOSED


@pytest.mark.asyncio
async def test_concurrent_enable_creates_one_runtime(tmp_path: Path) -> None:
    entered = 0
    release = anyio.Event()

    async def factory(record: Project) -> FakeTerminalRuntime:
        nonlocal entered
        entered += 1
        await release.wait()
        return FakeTerminalRuntime(record.name)

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)

    async def enable() -> bool:
        return await manager.set_enabled(record, enabled=True)

    outcomes: list[bool] = []

    async def collect() -> None:
        outcomes.append(await enable())

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(collect)
        tasks.start_soon(collect)
        await anyio.sleep(0)
        release.set()

    assert entered == 1
    assert sorted(outcomes) == [False, True]
    await manager.aclose_all()


@pytest.mark.asyncio
async def test_failed_close_is_retryable_and_blocks_reopen(tmp_path: Path) -> None:
    runtime = FakeTerminalRuntime("one", close_failures=1)

    async def factory(record: Project) -> FakeTerminalRuntime:
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)
    await manager.set_enabled(record, enabled=True)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await manager.set_enabled(record, enabled=False)
    assert manager.state(record) is ProjectTerminalState.FAILED
    assert manager.list_tools(record) == ()
    with pytest.raises(RuntimeError, match="cleanup must succeed"):
        await manager.set_enabled(record, enabled=True)

    assert await manager.set_enabled(record, enabled=False) is False
    assert runtime.close_calls == 2
    assert manager.state(record) is ProjectTerminalState.CLOSED


@pytest.mark.asyncio
async def test_failed_initialization_exposes_no_tools_and_can_retry(tmp_path: Path) -> None:
    attempts = 0

    async def factory(record: Project) -> FakeTerminalRuntime:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("shell probe failed")
        return FakeTerminalRuntime(record.name)

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)

    with pytest.raises(RuntimeError, match="shell probe failed"):
        await manager.set_enabled(record, enabled=True)
    assert manager.state(record) is ProjectTerminalState.FAILED
    assert manager.failure(record) == "shell probe failed"
    assert manager.list_tools(record) == ()

    assert await manager.set_enabled(record, enabled=True) is True
    assert manager.state(record) is ProjectTerminalState.OPEN
    assert [tool.name for tool in manager.list_tools(record)] == ["shell_list"]
    await manager.aclose_all()


@pytest.mark.asyncio
async def test_remove_retires_entry_so_waiting_enable_cannot_reopen(tmp_path: Path) -> None:
    close_entered = anyio.Event()
    release_close = anyio.Event()
    created: list[FakeTerminalRuntime] = []

    class BlockingCloseRuntime(FakeTerminalRuntime):
        async def aclose(self) -> None:
            close_entered.set()
            await release_close.wait()
            await super().aclose()

    async def factory(record: Project) -> FakeTerminalRuntime:
        runtime = BlockingCloseRuntime(record.name)
        created.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)
    await manager.set_enabled(record, enabled=True)
    enable_error: Exception | None = None

    async def remove() -> None:
        await manager.remove(record)

    async def reopen() -> None:
        nonlocal enable_error
        try:
            await manager.set_enabled(record, enabled=True)
        except Exception as exc:
            enable_error = exc

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(remove)
        await close_entered.wait()
        tasks.start_soon(reopen)
        await anyio.sleep(0)
        release_close.set()

    assert isinstance(enable_error, ProjectTerminalNotAvailableError)
    assert len(created) == 1
    assert created[0].closed is True
    assert manager.state(record) is ProjectTerminalState.CLOSED
    assert manager.has_live_runtimes is False
    await manager.aclose_all()


@pytest.mark.asyncio
async def test_shutdown_tombstone_prevents_waiting_or_new_project_enable(tmp_path: Path) -> None:
    close_entered = anyio.Event()
    release_close = anyio.Event()
    created: list[FakeTerminalRuntime] = []

    class BlockingCloseRuntime(FakeTerminalRuntime):
        async def aclose(self) -> None:
            close_entered.set()
            await release_close.wait()
            await super().aclose()

    async def factory(record: Project) -> FakeTerminalRuntime:
        runtime = BlockingCloseRuntime(record.name)
        created.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    first = project("first", tmp_path)
    second = project("second", tmp_path)
    await manager.set_enabled(first, enabled=True)
    waiting_error: Exception | None = None

    async def shutdown() -> None:
        await manager.aclose_all()

    async def reopen() -> None:
        nonlocal waiting_error
        try:
            await manager.set_enabled(first, enabled=True)
        except Exception as exc:
            waiting_error = exc

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(shutdown)
        await close_entered.wait()
        tasks.start_soon(reopen)
        await anyio.sleep(0)
        with pytest.raises(ProjectTerminalNotAvailableError, match="shutdown"):
            await manager.set_enabled(second, enabled=True)
        release_close.set()

    assert isinstance(waiting_error, ProjectTerminalNotAvailableError)
    assert len(created) == 1
    assert created[0].closed is True
    assert manager.has_live_runtimes is False


@pytest.mark.asyncio
async def test_cancelled_scope_still_closes_all_project_runtimes(tmp_path: Path) -> None:
    created: list[FakeTerminalRuntime] = []

    async def factory(record: Project) -> FakeTerminalRuntime:
        runtime = FakeTerminalRuntime(record.name)
        created.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    first = project("first", tmp_path)
    second = project("second", tmp_path)
    await manager.set_enabled(first, enabled=True)
    await manager.set_enabled(second, enabled=True)

    with anyio.CancelScope() as scope:
        scope.cancel()
        await manager.aclose_all()

    assert [runtime.closed for runtime in created] == [True, True]
    assert manager.has_live_runtimes is False
