from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

import pytest
from filelock import FileLock
from pydantic import ValidationError

from ide4ai.a2c_smcp.projects import (
    ProjectConflictError,
    ProjectLspConfig,
    ProjectNotFoundError,
    ProjectRegistry,
    ProjectRegistryError,
)
from ide4ai.a2c_smcp.projects.models import ProjectRegistryDocument


def _create_project_in_process(registry_path: str, name: str, root_dir: str) -> str:
    return ProjectRegistry(registry_path).create(name=name, root_dir=root_dir).name


def test_registry_persists_versioned_immutable_projects(tmp_path: Path) -> None:
    registry_path = tmp_path / "config" / "projects.json"
    project_root = tmp_path / "workspace"
    project_root.mkdir()
    registry = ProjectRegistry(registry_path)

    project = registry.create(
        name=" backend ",
        root_dir=project_root,
        lsp=ProjectLspConfig(mode="explicit", language_id="python"),
    )

    assert project.name == "backend"
    assert project.root_dir == str(project_root.resolve())
    assert ProjectRegistry(registry_path).list() == (project,)
    persisted = json.loads(registry_path.read_text(encoding="utf-8"))
    assert persisted["version"] == 2
    assert persisted["current_project_id"] == str(project.id)
    assert registry_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValidationError):
        project.name = "changed"  # type: ignore[misc]


def test_registry_rejects_name_and_canonical_root_conflicts(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    registry = ProjectRegistry(tmp_path / "projects.json")
    registry.create(name="Example", root_dir=first_root)

    with pytest.raises(ProjectConflictError, match="name"):
        registry.create(name="example", root_dir=second_root)
    with pytest.raises(ProjectConflictError, match="root"):
        registry.create(name="alias", root_dir=first_root / ".")


def test_registry_rejects_case_alias_of_same_root_on_case_insensitive_filesystem(tmp_path: Path) -> None:
    project_root = tmp_path / "CaseSensitiveName"
    alias_root = project_root.with_name(project_root.name.swapcase())
    project_root.mkdir()
    if not alias_root.exists():
        pytest.skip("filesystem is case-sensitive")
    registry = ProjectRegistry(tmp_path / "projects.json")
    registry.create(name="original", root_dir=project_root)

    with pytest.raises(ProjectConflictError, match="root"):
        registry.create(name="alias", root_dir=alias_root)


def test_registry_distinguishes_uuid_objects_from_uuid_shaped_names(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    registry = ProjectRegistry(tmp_path / "projects.json")
    first = registry.create(name="first", root_dir=first_root)
    uuid_named = registry.create(name=str(first.id), root_dir=second_root)

    assert registry.find(first.id) == first
    assert registry.find(uuid_named.name) == uuid_named
    assert registry.delete(uuid_named.name) == uuid_named
    assert registry.find(first.id) == first


def test_registry_delete_never_touches_project_contents(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir()
    sentinel = project_root / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    registry = ProjectRegistry(tmp_path / "projects.json")
    project = registry.create(name="workspace", root_dir=project_root)

    assert registry.delete(project.id) == project
    assert sentinel.read_text(encoding="utf-8") == "keep"
    with pytest.raises(ProjectNotFoundError):
        registry.find(project.id)


def test_registry_rejects_missing_roots_and_invalid_documents(tmp_path: Path) -> None:
    registry_path = tmp_path / "projects.json"
    registry = ProjectRegistry(registry_path)
    with pytest.raises(FileNotFoundError):
        registry.create(name="missing", root_dir=tmp_path / "missing")

    registry_path.write_text('{"version": 3, "projects": []}', encoding="utf-8")
    with pytest.raises(ProjectRegistryError, match="Cannot migrate"):
        ProjectRegistry(registry_path)


def test_registry_persists_and_reassigns_current_project(tmp_path: Path) -> None:
    registry_path = tmp_path / "projects.json"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    registry = ProjectRegistry(registry_path)

    first = registry.create(name="first", root_dir=first_root)
    second = registry.create(name="second", root_dir=second_root)
    assert registry.current() == first

    registry.select(second.name)
    assert ProjectRegistry(registry_path).current() == second

    registry.delete(second.id)
    assert ProjectRegistry(registry_path).current() == first

    registry.delete(first.id)
    assert ProjectRegistry(registry_path).current() is None


def test_registry_migrates_v1_and_selects_first_sorted_project(tmp_path: Path) -> None:
    registry_path = tmp_path / "projects.json"
    alpha_root = tmp_path / "alpha"
    zulu_root = tmp_path / "zulu"
    alpha_root.mkdir()
    zulu_root.mkdir()
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "projects": [
                    {
                        "id": "5c4d1aa6-f21a-4247-af97-8662b0f12725",
                        "name": "Zulu",
                        "root_dir": str(zulu_root),
                    },
                    {
                        "id": "44c274e9-2910-4836-ae86-f446d0f9d920",
                        "name": "alpha",
                        "root_dir": str(alpha_root),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    registry = ProjectRegistry(registry_path)

    assert registry.current() is not None
    assert registry.current().name == "alpha"  # type: ignore[union-attr]
    persisted = json.loads(registry_path.read_text(encoding="utf-8"))
    assert persisted["version"] == 2
    assert persisted["current_project_id"] == "44c274e9-2910-4836-ae86-f446d0f9d920"


def test_registry_checks_for_v1_only_after_acquiring_file_lock(tmp_path: Path) -> None:
    registry_path = tmp_path / "projects.json"
    legacy_payload = {
        "version": 1,
        "projects": [
            {
                "id": "44c274e9-2910-4836-ae86-f446d0f9d920",
                "name": "legacy",
                "root_dir": str(tmp_path),
            }
        ],
    }
    writer_lock = FileLock(f"{registry_path}.lock")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with writer_lock:
            constructing = executor.submit(ProjectRegistry, registry_path)
            with pytest.raises(FutureTimeoutError):
                constructing.result(timeout=0.2)
            registry_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
        registry = constructing.result(timeout=2)
    assert registry.current() is not None
    assert registry.current().name == "legacy"  # type: ignore[union-attr]
    assert json.loads(registry_path.read_text(encoding="utf-8"))["version"] == 2


def test_project_rejects_noncanonical_absolute_root(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="normalized"):
        ProjectRegistryDocument.model_validate(
            {
                "projects": [
                    {
                        "id": "44c274e9-2910-4836-ae86-f446d0f9d920",
                        "name": "invalid",
                        "root_dir": f"{tmp_path}/child/..",
                    }
                ]
            }
        )


def test_project_metadata_rejects_project_types_and_invalid_selection(tmp_path: Path) -> None:
    project = {
        "id": "44c274e9-2910-4836-ae86-f446d0f9d920",
        "name": "plain-project",
        "root_dir": str(tmp_path),
    }
    with pytest.raises(ValidationError, match="type"):
        ProjectRegistryDocument.model_validate(
            {
                "projects": [{**project, "type": "stdio"}],
                "current_project_id": project["id"],
            }
        )
    with pytest.raises(ValidationError, match="current_project_id"):
        ProjectRegistryDocument.model_validate({"projects": [project], "current_project_id": None})


def test_registry_rejects_documents_with_duplicate_project_identity(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    shared_id = "44c274e9-2910-4836-ae86-f446d0f9d920"
    other_id = "5c4d1aa6-f21a-4247-af97-8662b0f12725"
    cases = (
        (
            {"id": shared_id, "name": "first", "root_dir": str(first_root)},
            {"id": shared_id, "name": "second", "root_dir": str(second_root)},
        ),
        (
            {"id": shared_id, "name": "Same", "root_dir": str(first_root)},
            {"id": other_id, "name": "same", "root_dir": str(second_root)},
        ),
        (
            {"id": shared_id, "name": "first", "root_dir": str(first_root)},
            {"id": other_id, "name": "second", "root_dir": str(first_root)},
        ),
    )
    for index, projects in enumerate(cases):
        registry_path = tmp_path / f"projects-{index}.json"
        registry_path.write_text(json.dumps({"version": 1, "projects": projects}), encoding="utf-8")

        with pytest.raises(ProjectRegistryError, match="duplicate project"):
            ProjectRegistry(registry_path).list()


def test_registry_serializes_concurrent_writers_without_lost_updates(tmp_path: Path) -> None:
    registry_path = tmp_path / "projects.json"
    roots = []
    for index in range(12):
        root = tmp_path / f"root-{index}"
        root.mkdir()
        roots.append(root)

    def create(index: int) -> None:
        ProjectRegistry(registry_path).create(name=f"project-{index}", root_dir=roots[index])

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(create, range(len(roots))))

    projects = ProjectRegistry(registry_path).list()
    assert len(projects) == len(roots)
    assert {project.name for project in projects} == {f"project-{index}" for index in range(len(roots))}


def test_registry_file_lock_coordinates_processes(tmp_path: Path) -> None:
    registry_path = tmp_path / "projects.json"
    roots = [tmp_path / f"process-root-{index}" for index in range(4)]
    for root in roots:
        root.mkdir()

    with ProcessPoolExecutor(max_workers=4) as executor:
        names = list(
            executor.map(
                _create_project_in_process,
                [str(registry_path)] * len(roots),
                [f"process-{index}" for index in range(len(roots))],
                [str(root) for root in roots],
            )
        )

    assert set(names) == {f"process-{index}" for index in range(len(roots))}
    assert len(ProjectRegistry(registry_path).list()) == len(roots)


def test_project_lsp_configuration_validates_and_builds_runtime_values() -> None:
    config = ProjectLspConfig(
        mode="explicit",
        language_id="rust",
        server_command=("rust-analyzer",),
        file_extensions=(".rs",),
        root_markers=("Cargo.toml",),
    )

    assert config.to_settings().language_id == "rust"
    assert next(profile for profile in config.to_profiles() if profile.language_id == "rust").server.command == (
        "rust-analyzer",
    )
    with pytest.raises(ValidationError):
        ProjectLspConfig(mode="explicit")
