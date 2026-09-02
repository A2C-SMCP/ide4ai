from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import anyio
import pytest
from mcp.types import CallToolResult, ReadResourceResult, Resource, TextContent, TextResourceContents, Tool
from pydantic import AnyUrl

from ide4ai.a2c_smcp.projects import (
    Project,
    ProjectTerminalNotAvailableError,
    ProjectTerminalRuntimeManager,
    ProjectTerminalState,
    TerminalStartOptions,
)
from ide4ai.a2c_smcp.resource_events import ResourceUpdate


@dataclass
class FakeTerminalRuntime:
    project_name: str
    close_failures: int = 0
    closed: bool = False
    calls: list[tuple[str, Mapping[str, object]]] = field(default_factory=list)
    close_calls: int = 0
    resource_listeners: set[Callable[[AnyUrl], None]] = field(default_factory=set)

    def list_tools(self) -> tuple[Tool, ...]:
        if self.closed:
            raise RuntimeError("closed")
        return (
            Tool(
                name="shell_list",
                inputSchema={"type": "object", "additionalProperties": False},
            ),
        )

    def list_resources(self) -> tuple[Resource, ...]:
        if self.closed:
            raise RuntimeError("closed")
        return (Resource(uri=AnyUrl("window://fake/shell-overview"), name="Shell Overview"),)

    def read_resource(self, uri: str | AnyUrl) -> ReadResourceResult:
        if self.closed:
            raise RuntimeError("closed")
        return ReadResourceResult(
            contents=[TextResourceContents(uri=AnyUrl(uri), mimeType="text/markdown", text=self.project_name)]
        )

    def subscribe_resource_updates(self, listener: Callable[[AnyUrl], None]) -> Callable[[], None]:
        self.resource_listeners.add(listener)

        def unsubscribe() -> None:
            self.resource_listeners.discard(listener)

        return unsubscribe

    def emit_resource_update(self) -> None:
        for listener in tuple(self.resource_listeners):
            listener(AnyUrl("window://fake/shell-overview"))

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

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        assert options.cwd == str(Path(record.root_dir))
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
    assert (await manager.start(first, TerminalStartOptions())).changed is True
    assert (await manager.start(first, TerminalStartOptions())).changed is False
    assert [tool.name for tool in manager.list_tools(first)] == ["shell_list"]
    assert manager.list_tools(second) == ()

    result = await manager.call_tool(first, "shell_list", {})
    assert result.structuredContent == {"project": "first", "arguments": {}}
    with pytest.raises(ProjectTerminalNotAvailableError):
        await manager.call_tool(second, "shell_list", {})

    assert (await manager.close(first)).changed is True
    assert (await manager.close(first)).changed is False
    assert created[0].close_calls == 1
    assert manager.state(first) is ProjectTerminalState.CLOSED


@pytest.mark.asyncio
async def test_terminal_resources_delegate_reads_and_project_identified_updates(tmp_path: Path) -> None:
    runtimes: list[FakeTerminalRuntime] = []

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        runtime = FakeTerminalRuntime(record.name)
        runtimes.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)
    updates: list[ResourceUpdate] = []
    unsubscribe = manager.subscribe_resource_updates(updates.append)

    assert manager.list_resources(record) == ()
    await manager.start(record, TerminalStartOptions())
    resources = manager.list_resources(record)
    assert [str(resource.uri) for resource in resources] == ["window://fake/shell-overview"]
    rendered = manager.read_resource(record, resources[0].uri)
    assert isinstance(rendered.contents[0], TextResourceContents)
    assert rendered.contents[0].text == "one"

    runtimes[0].emit_resource_update()
    assert [(update.project, str(update.uri)) for update in updates] == [(record, "window://fake/shell-overview")]
    first_update = updates[0]
    assert manager.is_resource_update_current(first_update) is True
    await manager.close(record)
    assert runtimes[0].resource_listeners == set()
    assert manager.is_resource_update_current(first_update) is False
    assert manager.list_resources(record) == ()

    await manager.start(record, TerminalStartOptions())
    runtimes[1].emit_resource_update()
    assert len(updates) == 2
    assert updates[1].source_id is not first_update.source_id
    assert manager.is_resource_update_current(first_update) is False
    assert manager.is_resource_update_current(updates[1]) is True
    await manager.close(record)

    unsubscribe()
    unsubscribe()


@pytest.mark.asyncio
async def test_start_resolves_project_configuration_and_stale_start_keeps_original(tmp_path: Path) -> None:
    subdirectory = tmp_path / "subdirectory"
    subdirectory.mkdir()
    captured: list[TerminalStartOptions] = []

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        captured.append(options)
        return FakeTerminalRuntime(record.name)

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)
    requested = TerminalStartOptions(
        cwd=str(subdirectory),
        startup_command="export READY=1",
        shell="/bin/bash",
        environment={"FEATURE_FLAG": "enabled"},
        command_timeout_ms=9_000,
        shutdown_grace_ms=500,
        close_timeout_ms=1_500,
    )

    started = await manager.start(record, requested)
    stale = await manager.start(record, TerminalStartOptions(startup_command="export DIFFERENT=1"))

    assert started.changed is True
    assert started.configuration is not None
    assert started.configuration.cwd == str(subdirectory.resolve())
    assert started.configuration.public_summary() == {
        "cwd": str(subdirectory.resolve()),
        "shell": "/bin/bash",
        "startup_command_configured": True,
        "environment_override_count": 1,
        "command_timeout_ms": 9_000,
        "shutdown_grace_ms": 500,
        "close_timeout_ms": 1_500,
    }
    assert stale.changed is False
    assert stale.configuration == started.configuration
    assert captured == [started.configuration]
    await manager.close(record)


@pytest.mark.asyncio
async def test_start_rejects_cwd_outside_project_before_runtime_creation(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    created = False

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        nonlocal created
        created = True
        return FakeTerminalRuntime(record.name)

    manager = ProjectTerminalRuntimeManager(factory)

    with pytest.raises(ValueError, match="within the current project root"):
        await manager.start(project("one", root), TerminalStartOptions(cwd=str(outside)))

    assert created is False


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"shutdown_grace_ms": 60_001}, "shutdown_grace_ms must be between 1 and 60000"),
        ({"close_timeout_ms": 60_001}, "close_timeout_ms must be between 1 and 60000"),
    ],
)
def test_start_options_reject_unbounded_close_deadlines(arguments: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TerminalStartOptions(**arguments)


@pytest.mark.asyncio
async def test_concurrent_enable_creates_one_runtime(tmp_path: Path) -> None:
    entered = 0
    release = anyio.Event()

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        nonlocal entered
        entered += 1
        await release.wait()
        return FakeTerminalRuntime(record.name)

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)

    async def enable() -> bool:
        return (await manager.start(record, TerminalStartOptions())).changed

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

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)
    await manager.start(record, TerminalStartOptions())

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await manager.close(record)
    assert manager.state(record) is ProjectTerminalState.FAILED
    assert manager.list_tools(record) == ()
    with pytest.raises(RuntimeError, match="cleanup must succeed"):
        await manager.start(record, TerminalStartOptions())

    assert (await manager.close(record)).changed is True
    assert runtime.close_calls == 2
    assert manager.state(record) is ProjectTerminalState.CLOSED


@pytest.mark.asyncio
async def test_failed_initialization_exposes_no_tools_and_can_retry(tmp_path: Path) -> None:
    attempts = 0

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("shell probe failed")
        return FakeTerminalRuntime(record.name)

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)

    with pytest.raises(RuntimeError, match="shell probe failed"):
        await manager.start(record, TerminalStartOptions())
    assert manager.state(record) is ProjectTerminalState.FAILED
    assert manager.failure(record) == "shell probe failed"
    assert manager.list_tools(record) == ()

    assert (await manager.start(record, TerminalStartOptions())).changed is True
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

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        runtime = BlockingCloseRuntime(record.name)
        created.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    record = project("one", tmp_path)
    await manager.start(record, TerminalStartOptions())
    enable_error: Exception | None = None

    async def remove() -> None:
        await manager.remove(record)

    async def reopen() -> None:
        nonlocal enable_error
        try:
            await manager.start(record, TerminalStartOptions())
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

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        runtime = BlockingCloseRuntime(record.name)
        created.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    first = project("first", tmp_path)
    second = project("second", tmp_path)
    await manager.start(first, TerminalStartOptions())
    waiting_error: Exception | None = None

    async def shutdown() -> None:
        await manager.aclose_all()

    async def reopen() -> None:
        nonlocal waiting_error
        try:
            await manager.start(first, TerminalStartOptions())
        except Exception as exc:
            waiting_error = exc

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(shutdown)
        await close_entered.wait()
        tasks.start_soon(reopen)
        await anyio.sleep(0)
        with pytest.raises(ProjectTerminalNotAvailableError, match="shutdown"):
            await manager.start(second, TerminalStartOptions())
        release_close.set()

    assert isinstance(waiting_error, ProjectTerminalNotAvailableError)
    assert len(created) == 1
    assert created[0].closed is True
    assert manager.has_live_runtimes is False


@pytest.mark.asyncio
async def test_cancelled_scope_still_closes_all_project_runtimes(tmp_path: Path) -> None:
    created: list[FakeTerminalRuntime] = []

    async def factory(record: Project, options: TerminalStartOptions) -> FakeTerminalRuntime:
        runtime = FakeTerminalRuntime(record.name)
        created.append(runtime)
        return runtime

    manager = ProjectTerminalRuntimeManager(factory)
    first = project("first", tmp_path)
    second = project("second", tmp_path)
    await manager.start(first, TerminalStartOptions())
    await manager.start(second, TerminalStartOptions())

    with anyio.CancelScope() as scope:
        scope.cancel()
        await manager.aclose_all()

    assert [runtime.closed for runtime in created] == [True, True]
    assert manager.has_live_runtimes is False
