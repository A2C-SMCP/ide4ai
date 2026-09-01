from __future__ import annotations

import threading
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from ide4ai.a2c_smcp.projects import (
    Project,
    ProjectBusyError,
    ProjectError,
    ProjectHost,
    ProjectLspConfig,
    ProjectRegistry,
    ProjectRuntime,
    create_ide_factory,
)
from ide4ai.ide import IDE


class FakeIDE:
    def __init__(self, project_name: str, *, close_error: bool = False) -> None:
        self.project_name = project_name
        self.closed = False
        self.close_error = close_error
        self.close_attempts = 0

    def close(self) -> None:
        self.close_attempts += 1
        self.closed = True
        if self.close_error:
            raise RuntimeError(f"close failed: {self.project_name}")


class RecordingFactory:
    def __init__(self) -> None:
        self.instances: list[FakeIDE] = []

    def __call__(self, project: Project) -> IDE:
        instance = FakeIDE(project.name)
        self.instances.append(instance)
        return cast(IDE, instance)


def project(name: str, root: Path) -> Project:
    return Project(id=uuid4(), name=name, root_dir=str(root.resolve()))


def test_runtime_loads_lazily_and_can_be_reloaded(tmp_path: Path) -> None:
    factory = RecordingFactory()
    runtime = ProjectRuntime(project("one", tmp_path), factory)

    assert runtime.loaded is False
    with runtime.lease() as first:
        assert first is factory.instances[0]
        assert runtime.loaded is True
        assert runtime.active_calls == 1
    assert runtime.unload() is True
    assert factory.instances[0].closed is True

    with runtime.lease() as second:
        assert second is factory.instances[1]
    assert second is not first


def test_runtime_factory_creates_generic_ide_with_project_lsp_settings(tmp_path: Path) -> None:
    record = Project(
        id=uuid4(),
        name="generic",
        root_dir=str(tmp_path.resolve()),
        lsp=ProjectLspConfig(mode="disabled"),
    )
    runtime = ProjectRuntime(record, create_ide_factory({"render_with_symbols": False}))

    with runtime.lease() as ide:
        assert type(ide) is IDE
        assert ide.project_name == "generic"
        assert ide.root_dir == str(tmp_path.resolve())
        assert ide.workspace.lsp_status.state.value == "disabled"
    assert runtime.unload() is True


def test_runtime_rejects_normal_unload_during_calls_and_force_closes(tmp_path: Path) -> None:
    factory = RecordingFactory()
    runtime = ProjectRuntime(project("one", tmp_path), factory)

    with runtime.lease():
        with pytest.raises(ProjectBusyError, match="active call"):
            runtime.unload()
        assert runtime.unload(force=True) is True
        assert factory.instances[0].closed is True
        with pytest.raises(ProjectBusyError, match="releasing"):
            with runtime.lease():
                pass

    with runtime.lease():
        assert len(factory.instances) == 2


def test_runtime_blocks_new_lease_until_close_finishes(tmp_path: Path) -> None:
    close_started = threading.Event()
    allow_close = threading.Event()

    class BlockingIDE(FakeIDE):
        def close(self) -> None:
            close_started.set()
            assert allow_close.wait(timeout=5)
            super().close()

    instances: list[BlockingIDE] = []

    def factory(record: Project) -> IDE:
        instance = BlockingIDE(record.name)
        instances.append(instance)
        return cast(IDE, instance)

    runtime = ProjectRuntime(project("one", tmp_path), factory)
    with runtime.lease():
        pass
    unload_thread = threading.Thread(target=runtime.unload)
    unload_thread.start()
    assert close_started.wait(timeout=5)

    with pytest.raises(ProjectBusyError, match="releasing"):
        with runtime.lease():
            pass
    assert len(instances) == 1

    allow_close.set()
    unload_thread.join(timeout=5)
    assert not unload_thread.is_alive()
    with runtime.lease():
        assert len(instances) == 2


def test_runtime_retains_failed_close_for_retry(tmp_path: Path) -> None:
    factory = RecordingFactory()
    runtime = ProjectRuntime(project("one", tmp_path), factory)
    with runtime.lease():
        pass
    instance = factory.instances[0]
    instance.close_error = True

    with pytest.raises(RuntimeError, match="close failed"):
        runtime.unload()
    assert runtime.loaded is True
    with pytest.raises(ProjectBusyError, match="releasing"):
        with runtime.lease():
            pass

    instance.close_error = False
    assert runtime.unload() is True
    assert runtime.loaded is False
    assert instance.close_attempts == 2


def test_project_host_selection_switch_and_call_snapshot(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "projects.json")
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = registry.create(name="first", root_dir=first_root)
    second = registry.create(name="second", root_dir=second_root)
    factory = RecordingFactory()
    host = ProjectHost(registry, factory)

    assert host.current_project == first
    assert host.switch_project(first.id) == first
    assert factory.instances == []

    with host.lease_current() as (leased_project, leased_ide):
        assert leased_project == first
        assert leased_ide.project_name == "first"  # type: ignore[attr-defined]
        host.switch_project(second.name)
        assert host.current_project == second
        assert leased_project == first

    with host.lease_current() as (leased_project, _):
        assert leased_project == second


def test_project_host_keeps_exactly_one_selection_and_manages_delete(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "projects.json")
    factory = RecordingFactory()
    host = ProjectHost(registry, factory)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    first = host.create_project(name="first", root_dir=first_root)
    assert host.current_project == first
    second = host.create_project(name="second", root_dir=second_root)
    assert host.current_project == first
    with host.lease_current():
        pass
    assert host.delete_project(first.id) == first
    assert factory.instances[0].closed is True
    assert host.current_project == second


def test_project_host_refuses_busy_delete_without_force(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "projects.json")
    root = tmp_path / "root"
    root.mkdir()
    registered = registry.create(name="busy", root_dir=root)
    factory = RecordingFactory()
    host = ProjectHost(registry, factory)

    with host.lease_current():
        with pytest.raises(ProjectBusyError):
            host.delete_project(registered.id)
        assert registry.find(registered.id) == registered
        assert host.delete_project(registered.id, force=True) == registered
        assert factory.instances[0].closed is True


def test_prepared_delete_blocks_new_leases_until_cancelled(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "projects.json")
    root = tmp_path / "root"
    root.mkdir()
    registered = registry.create(name="reserved", root_dir=root)
    host = ProjectHost(registry, RecordingFactory())

    prepared = host.prepare_delete(registered.id)
    with pytest.raises(ProjectBusyError, match="deletion is in progress"):
        with host.lease_project(registered):
            pass

    host.cancel_delete(prepared)
    with host.lease_project(registered) as (leased, _):
        assert leased == registered


def test_project_host_closes_every_runtime_even_when_one_close_fails(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "projects.json")
    roots = [tmp_path / "first", tmp_path / "second"]
    for root in roots:
        root.mkdir()
    projects = [registry.create(name=root.name, root_dir=root) for root in roots]
    instances: dict[str, FakeIDE] = {}

    def factory(record: Project) -> IDE:
        instance = FakeIDE(record.name, close_error=record.name == "first")
        instances[record.name] = instance
        return cast(IDE, instance)

    host = ProjectHost(registry, factory)
    for record in projects:
        host.switch_project(record.id)
        with host.lease_current():
            pass

    with pytest.raises(ProjectError, match="1 project runtime"):
        host.close()
    assert all(instance.closed for instance in instances.values())
    with pytest.raises(ProjectError, match="closed"):
        host.list_projects()

    instances["first"].close_error = False
    host.close()
    assert instances["first"].close_attempts == 2
    assert instances["second"].close_attempts == 1
