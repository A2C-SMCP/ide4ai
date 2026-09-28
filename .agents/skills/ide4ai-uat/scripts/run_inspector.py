#!/usr/bin/env python3
"""Replace this process with the Inspector described by a UAT run manifest."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_manifest(path: Path) -> dict[str, object]:
    resolved = path.expanduser().resolve()
    try:
        manifest = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read UAT manifest {resolved}: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise SystemExit(f"Unsupported UAT manifest schema: {manifest.get('schema_version')}")
    if Path(str(manifest.get("run_dir", ""))).resolve() != resolved.parent:
        raise SystemExit("Manifest run_dir does not match the manifest location")
    return manifest


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: run_inspector.py <run-manifest.json>")
    manifest = _load_manifest(Path(sys.argv[1]))
    inspector = manifest.get("inspector")
    if not isinstance(inspector, dict):
        raise SystemExit("Manifest is missing inspector settings")
    argv = inspector.get("argv")
    extra_env = inspector.get("env")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise SystemExit("Manifest inspector.argv must be a non-empty string array")
    if not isinstance(extra_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in extra_env.items()
    ):
        raise SystemExit("Manifest inspector.env must contain only string keys and values")
    env = os.environ.copy()
    env.update(extra_env)
    os.execvpe(argv[0], argv, env)


if __name__ == "__main__":
    main()
