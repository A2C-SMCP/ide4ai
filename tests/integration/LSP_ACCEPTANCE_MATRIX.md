# Workspace/LSP Acceptance Matrix

This matrix maps every parent issue #17 acceptance criterion to automated evidence. The cross-boundary suite is
`tests/integration/test_multilanguage_e2e.py`; lower-level suites remain responsible for protocol edge cases.

| Parent #17 acceptance criterion | Automated evidence |
| --- | --- |
| IDE and Workspace do not depend on language-specific subclasses | `tests/test_public_api.py::test_public_ide_uses_injected_extensible_profile`; `test_generic_mcp_fake_language_starts_and_closes` |
| LspManager owns detection, startup, restart, close, and status | `test_fake_second_language_auto_lazy_start_and_graceful_close`; `test_fake_language_crash_restarts_once_and_reload_resets_state` |
| auto, explicit, and disabled modes; one fixed primary language/session | `test_workspace_selection_modes_ties_no_match_and_reload` |
| Only primary-language documents or semantic calls start LSP; Glob/Grep/Terminal do not | `test_real_pyright_public_workspace_auto_start_and_close`; `test_fake_second_language_auto_lazy_start_and_graceful_close`; `test_generic_mcp_missing_lsp_keeps_file_search_and_terminal_working` |
| File, search, and terminal capabilities survive missing/start-failed LSP | `test_generic_mcp_missing_lsp_keeps_file_search_and_terminal_working`; `tests/test_public_api.py::test_public_ide_render_degrades_without_lsp` |
| Production Pyright plus a fake second language | `test_real_pyright_public_workspace_auto_start_and_close`; `test_fake_second_language_auto_lazy_start_and_graceful_close` |
| Language-neutral public API and MCP CLI, without Python compatibility facade | `tests/test_public_api.py::test_public_api_exposes_only_language_neutral_types`; `tests/test_public_api.py::test_distribution_exposes_only_generic_mcp_cli`; `test_generic_mcp_fake_language_starts_and_closes` |
| Unit, integration, and MCP regressions pass | `uv run pytest -q`; `uv run pytest tests/lsp tests/python_ide/test_workspace_lsp.py tests/integration/lsp tests/integration/test_multilanguage_e2e.py tests/test_public_api.py -q` |

## Issue #22 coverage

| Required scenario | Automated evidence |
| --- | --- |
| Real Pyright selection, startup, and close | `test_real_pyright_public_workspace_auto_start_and_close` |
| Fake second-language selection, startup, and close | `test_fake_second_language_auto_lazy_start_and_graceful_close`; `test_generic_mcp_fake_language_starts_and_closes` |
| auto, explicit, disabled, tie, and no-match selection | `test_workspace_selection_modes_ties_no_match_and_reload` |
| Lazy start, crash, one automatic restart, reload, unavailable degradation | `test_fake_language_crash_restarts_once_and_reload_resets_state`; `test_generic_mcp_missing_lsp_keeps_file_search_and_terminal_working` |
| Generic MCP entry and non-LSP file/search/terminal behavior | `test_generic_mcp_missing_lsp_keeps_file_search_and_terminal_working` |

The #22 diff is intentionally limited to tests, fixtures, and test documentation. It must not modify production code.
