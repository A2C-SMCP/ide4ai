#!/usr/bin/env python3
"""Prepare an isolated ide4ai Inspector UAT run and print its launch manifest."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

INSPECTOR_VERSION = "2.4.0"
MINIMUM_NODE_VERSION = (22, 19, 0)
DEFAULT_CLIENT_PORT = 6274
DEFAULT_SCENARIO = "smoke-dynamic-catalog"


def _repo_root() -> Path:
    root = Path(__file__).resolve().parents[4]
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file() or 'name = "ide4ai"' not in pyproject.read_text(encoding="utf-8"):
        raise SystemExit(f"Not an ide4ai repository: {root}")
    return root


def _require_executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise SystemExit(f"Required executable is missing: {name}")
    return executable


def _node_version(node: str) -> tuple[int, int, int]:
    output = subprocess.check_output([node, "--version"], text=True).strip().removeprefix("v")
    try:
        version = tuple(int(part) for part in output.split(".")[:3])
    except ValueError as exc:
        raise SystemExit(f"Cannot parse Node.js version: {output}") from exc
    if len(version) != 3:
        raise SystemExit(f"Cannot parse Node.js version: {output}")
    return version


def _assert_port_available(port: int) -> None:
    if not 1 <= port <= 65535:
        raise SystemExit(f"Client port must be between 1 and 65535: {port}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise SystemExit(f"Client port is unavailable: 127.0.0.1:{port}") from exc


def _available_scenarios(root: Path) -> tuple[str, ...]:
    scenarios_dir = root / ".agents" / "skills" / "ide4ai-uat" / "references" / "scenarios"
    scenarios = tuple(sorted(path.stem for path in scenarios_dir.glob("*.md") if path.name != "index.md"))
    if DEFAULT_SCENARIO not in scenarios:
        raise SystemExit(f"Default UAT scenario is missing: {scenarios_dir / f'{DEFAULT_SCENARIO}.md'}")
    return scenarios


def _parse_args(available_scenarios: tuple[str, ...], argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-port", type=int, default=DEFAULT_CLIENT_PORT)
    parser.add_argument("--auto-refresh", action="store_true", help="Enable Inspector automatic catalog refresh.")
    parser.add_argument(
        "--scenario",
        choices=available_scenarios,
        default=DEFAULT_SCENARIO,
        help="UAT scenario contract to record in the run manifest.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Create the isolated run at this new or empty directory instead of the system temp directory.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    root = _repo_root()
    args = _parse_args(_available_scenarios(root), argv)
    node = _require_executable("node")
    npx = _require_executable("npx")
    uv = _require_executable("uv")
    version = _node_version(node)
    if version < MINIMUM_NODE_VERSION:
        required = ".".join(str(part) for part in MINIMUM_NODE_VERSION)
        actual = ".".join(str(part) for part in version)
        raise SystemExit(f"Node.js {required} or newer is required; found {actual}")
    _assert_port_available(args.client_port)

    if args.run_dir is None:
        run_dir = Path(tempfile.mkdtemp(prefix="ide4ai-uat-"))
    else:
        run_dir = args.run_dir.expanduser().resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        if any(run_dir.iterdir()):
            raise SystemExit(f"Run directory must be empty: {run_dir}")

    workspace_dir = run_dir / "workspace"
    artifacts_dir = run_dir / "artifacts"
    workspace_dir.mkdir()
    artifacts_dir.mkdir()
    (workspace_dir / "README.md").write_text("# ide4ai UAT workspace\n", encoding="utf-8")

    config_path = run_dir / "inspector-config.json"
    registry_path = run_dir / "projects.json"
    server_config = {
        "mcpServers": {
            "ide4ai-local": {
                "type": "stdio",
                "command": uv,
                "args": [
                    "run",
                    "--group",
                    "py",
                    "ide4ai-mcp",
                    "--transport",
                    "stdio",
                    "--project-registry-path",
                    str(registry_path),
                ],
                "env": {"PYTHONUNBUFFERED": "1"},
                "cwd": str(root),
                "protocolEra": "legacy",
                "autoRefreshOnListChanged": args.auto_refresh,
                "connectionTimeout": 30_000,
                "requestTimeout": 30_000,
            }
        }
    }
    config_path.write_text(json.dumps(server_config, indent=2) + "\n", encoding="utf-8")
    config_path.chmod(0o400)

    token = secrets.token_urlsafe(32)
    manifest = {
        "schema_version": 1,
        "scenario": args.scenario,
        "auto_refresh": args.auto_refresh,
        "run_dir": str(run_dir),
        "workspace_dir": str(workspace_dir),
        "artifacts_dir": str(artifacts_dir),
        "project_registry_path": str(registry_path),
        "inspector_config_path": str(config_path),
        "inspector": {
            "version": INSPECTOR_VERSION,
            "url": f"http://127.0.0.1:{args.client_port}",
            "argv": [
                npx,
                "-y",
                f"@modelcontextprotocol/inspector@{INSPECTOR_VERSION}",
                "--web",
                "--config",
                str(config_path),
            ],
            "env": {
                "HOST": "127.0.0.1",
                "CLIENT_PORT": str(args.client_port),
                "MCP_AUTO_OPEN_ENABLED": "false",
                "MCP_INSPECTOR_API_TOKEN": token,
            },
        },
    }
    manifest_path = run_dir / "run-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
