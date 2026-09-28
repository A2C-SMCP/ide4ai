from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PREPARE_RUN_PATH = REPO_ROOT / ".agents" / "skills" / "ide4ai-uat" / "scripts" / "prepare_run.py"
SCENARIOS_DIR = REPO_ROOT / ".agents" / "skills" / "ide4ai-uat" / "references" / "scenarios"
REQUIRED_SCENARIOS = {
    "smoke-dynamic-catalog",
    "project-code-edit-loop",
    "terminal-test-loop",
    "multi-project-switch",
    "restart-persistence",
    "terminal-resource-updates",
    "lsp-python-workflow",
    "project-guardrails",
}


def _load_prepare_run() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ide4ai_uat_prepare_run", PREPARE_RUN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_available_scenarios_include_required_contracts_but_not_index() -> None:
    prepare_run = _load_prepare_run()

    scenarios = set(prepare_run._available_scenarios(REPO_ROOT))

    assert REQUIRED_SCENARIOS <= scenarios
    assert "index" not in scenarios


def test_scenario_index_matches_contract_files() -> None:
    prepare_run = _load_prepare_run()
    discovered = set(prepare_run._available_scenarios(REPO_ROOT))
    index = (SCENARIOS_DIR / "index.md").read_text(encoding="utf-8")
    indexed = {line.split("`", maxsplit=2)[1] for line in index.splitlines() if line.startswith("| `")}

    assert indexed == discovered


@pytest.mark.parametrize("scenario", sorted(REQUIRED_SCENARIOS))
def test_required_scenario_contract_has_standard_sections(scenario: str) -> None:
    contract = (SCENARIOS_DIR / f"{scenario}.md").read_text(encoding="utf-8")

    assert contract.startswith(f"# {scenario}\n")
    assert "\n## 目标\n" in contract
    assert "\n## 前置状态\n" in contract
    assert "\n## 步骤与断言\n" in contract
    assert "\n## 非目标\n" in contract


def test_parse_args_defaults_to_smoke_scenario() -> None:
    prepare_run = _load_prepare_run()

    args = prepare_run._parse_args(("project-code-edit-loop", "smoke-dynamic-catalog"), [])

    assert args.scenario == "smoke-dynamic-catalog"


def test_parse_args_accepts_discovered_scenario() -> None:
    prepare_run = _load_prepare_run()

    args = prepare_run._parse_args(
        ("project-code-edit-loop", "smoke-dynamic-catalog"),
        ["--scenario", "project-code-edit-loop"],
    )

    assert args.scenario == "project-code-edit-loop"


@pytest.mark.parametrize("scenario", ["unknown", "../smoke-dynamic-catalog", "index"])
def test_parse_args_rejects_unknown_or_non_contract_scenario(scenario: str) -> None:
    prepare_run = _load_prepare_run()

    with pytest.raises(SystemExit):
        prepare_run._parse_args(
            ("project-code-edit-loop", "smoke-dynamic-catalog"),
            ["--scenario", scenario],
        )


def test_main_records_selected_scenario_in_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepare_run = _load_prepare_run()
    run_dir = tmp_path / "run"
    monkeypatch.setattr(prepare_run, "_require_executable", lambda name: f"/test-bin/{name}")
    monkeypatch.setattr(prepare_run, "_node_version", lambda node: (22, 19, 0))
    monkeypatch.setattr(prepare_run, "_assert_port_available", lambda port: None)

    prepare_run.main(
        [
            "--scenario",
            "project-code-edit-loop",
            "--run-dir",
            str(run_dir),
            "--client-port",
            "6288",
        ]
    )

    printed_manifest = json.loads(capsys.readouterr().out)
    saved_manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    assert printed_manifest["scenario"] == "project-code-edit-loop"
    assert saved_manifest["scenario"] == "project-code-edit-loop"
