# Multi-project and Terminal acceptance

## Delivered contract

The current implementation persists one server-owned current project. Creating the
first project selects it; additional registrations preserve the selection. On restart
the selection is restored; old metadata without a valid selection chooses the first
project in deterministic name order. `project_switch` changes that selection.
Registrations are shared persistent metadata; IDE, LSP, Terminal and Shell processes
are owned by each server and are not restored across restarts.

This supersedes the original #23/#26 wording about session-local, unselected
multi-project startup. The Terminal names in that early description are also
superseded by the explicit `terminal_start` and `terminal_close` contract delivered
in #24. Both are target-state operations, not toggles. Project names are public
identifiers; UUIDs remain internal and appear in workspace resource URIs.

## Acceptance mapping

| Requirement (#23 / #26) | Evidence |
| --- | --- |
| Persistent immutable registrations; create/list/switch/delete; unique current project | `tests/a2c_smcp/projects/test_registry.py`, `test_runtime.py`; real stdio `test_stdio_catalog_changes_and_stale_tool_error` |
| Lazy project IDE/LSP, retained state and isolation between two real projects | `tests/integration/lsp/test_project_runtime_isolation.py`: two actual Pyright processes, symbol queries, concurrent switch during a lease, unloading one while preserving the other, final process/thread cleanup |
| Dynamic tool/resource discovery, listChanged capabilities and stale calls | `tests/a2c_smcp/test_dynamic_catalog.py`; real stdio catalog test; Inspector smoke in both manual and automatic refresh modes |
| Independent per-project Terminal Runtime and Shells | `test_stdio_tfbash_runtimes_are_isolated_per_project`, `tests/a2c_smcp/projects/test_terminal.py` |
| Runtime shutdown with active Shell; bounded terminate/kill | `test_stdio_terminal_close_force_kills_running_shell_after_grace_period` |
| Multiple Shells and resource update subscription | `test_stdio_shell_overview_resource_follows_terminal_and_streams_updates`; terminal manager and catalog tests |
| Busy/force behavior, concurrent lifecycle changes, deletion rollback | `test_runtime.py`, `test_terminal.py`, `test_dynamic_catalog.py` |
| Request-start project snapshot during switch | `test_tool_binding_keeps_request_start_project_snapshot`, `test_unload_binding_keeps_request_start_project_snapshot`; real LSP lease/switch integration |
| Shell Overview list/read/subscribe/updated/disappear; stale events/URIs | Real stdio resource test; `test_resource_update_hub_filters_old_projects_and_unsubscribed_sessions` |
| Inspector compatibility and cleanup, including failure with a live Shell | `tests/uat/run.mjs`, centralized Page Object, smoke and Terminal scenarios; `--inject-failure` self-test |
| Full quality gate | `uv run --group py poe check`, `uv run --group py poe test` |

Install the locked Python LSP dependency with `uv sync --group py`; otherwise a
system `pyright-langserver` can shadow the intended version and fail diagnostics
acceptance. The Docker Pyright tests are optional: absence or a non-Pyright endpoint
is skipped with a reason; a positively identified Pyright's protocol/lifecycle errors
fail. Real local Pyright TCP-bridge and project integration tests run regardless.

Inspector setup, replay, evidence and extension instructions: [UAT README](../tests/uat/README.md).
