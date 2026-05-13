# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Runtime prerequisites

- Python 3.10–3.12 (`.python-version` pins the dev interpreter; `pyproject.toml` requires `>=3.10,<3.13`).
- `uv` for env + dependency management; `uv sync` to install runtime deps, `uv sync --all-groups` to also get `dev` and `py` (pyright) groups.
- `ripgrep` (`rg`) **must** be on PATH — the grep tooling shells out to it and will fail without it.
- `.env` at repo root is auto-loaded by `tests/conftest.py` via `python-dotenv` for test runs; see `.env.example` (proxy vars).

## Common tasks (via poethepoet)

Definitions live in `pyproject.toml` under `[tool.poe.tasks]`. Prefer `uv run poe <task>` in CI-style flows.

| Task | What it runs |
| --- | --- |
| `poe format` / `poe format-check` | `ruff format [--check] ide4ai tests` |
| `poe lint` / `poe lint-fix` | `ruff check [--fix] ide4ai tests` |
| `poe typecheck` | `mypy ide4ai` (strict — see `[tool.mypy]`) |
| `poe test` | `pytest tests` (all, incl. integration) |
| `poe test-unit` | `pytest tests -k 'not integration'` |
| `poe test-integration` | `pytest tests/integration` |
| `poe test-cov` | adds `--cov=ide4ai --cov-report=html --cov-report=term-missing` |
| `poe check` | lint + format-check + typecheck |
| `poe fix` | lint-fix + format |
| `poe pre-commit` | format → lint-fix → typecheck → test → format (sequence) |

Single test: `uv run pytest tests/path/to/test_foo.py::TestClass::test_case -v` or `uv run pytest -k "substring"`. `asyncio_mode = "auto"` is set, so `async def test_*` functions run without `@pytest.mark.asyncio`.

The CI workflow (`.github/workflows/tests.yml`) installs `pyright` as a `uv tool` so `pyright-langserver` is on PATH for LSP-dependent integration tests — replicate locally with `uv tool install pyright==1.1.400` if those tests fail with "pyright not found".

## Versioning

Version lives in both `ide4ai/__init__.py` (`__version__`) and `pyproject.toml` (`version`). Don't hand-edit — use `bump-my-version` driven by `.bumpversion.toml`, which keeps the two in sync, commits, and tags `v{new_version}`. Supported bumps follow PEP 440 pre/post/dev semantics (see the `parse` regex and `serialize` list in `.bumpversion.toml`).

## Architecture

`ide4ai` is a library that presents an IDE-like environment (editor + terminal) as a `gymnasium.Env`, with an MCP server wrapper so AI agents can drive it.

### Core layering

1. **`ide4ai/base.py` — `IDE[TerminalT, WorkspaceT]`** (generic gym.Env, ABC).
   - Holds a single `workspace: WorkspaceT` and a list of `terminals: list[TerminalT]`.
   - `step(action: dict)` validates with `IDEAction`, enforces `CommandFilterConfig` on `terminal` actions, then dispatches to `self.terminal.step(...)` or `self.workspace.step(...)` based on `action.category`.
   - Subclasses implement `init_terminal()`; workspace is constructed in the subclass's `__init__`.

2. **`ide4ai/python_ide/ide.py` — `PythonIDE(IDE[PexpectTerminalEnv, PyWorkspace])`**. Pairs:
   - `PyWorkspace` (`ide4ai/python_ide/workspace.py`) — Monaco-inspired `TextModel`s with pyright LSP wiring, symbol navigation, diagnostics.
   - `PexpectTerminalEnv` (`ide4ai/environment/terminal/pexpect_terminal_env.py`) — persistent pty session with optional `active_venv_cmd`.

3. **`ide4ai/ides.py` — `PyIDESingleton`** via the `IDESingleton` metaclass. **The singleton is keyed only on `project_name`** (`cls.__name__ + project_name`), not on `root_dir` or other args. Inside one process, calling `PyIDESingleton(...)` with the same `project_name` returns the first-created instance and ignores any later arguments. This is load-bearing for the MCP server's lifetime.

### Action schema (`ide4ai/schema.py`)

`IDEAction.category` ∈ `{"terminal", "workspace"}`. For `workspace`, `action_name` must be one of:

- `TEXT_DOCUMENT_ACTIONS` — e.g. `open_file`, `apply_edit`, `save_file`, `close_file`, `read_file`, `find_in_file`, `replace_in_file`, `get_file_symbols`, `get_definition_and_implementation`, `hover`, `insert_cursor`, `delete_cursor`, `clear_cursors`.
- `WORKSPACE_ACTIONS` — `find_in_workspace`, `replace_in_workspace`, `create_file(s)`, `delete_file(s)`, `rename_file`.
- `LSP_ACTIONS` — `restart_lsp`.

For `terminal`, `action_name` is the command; the allow/deny check goes through `CommandFilterConfig` (`ide4ai/environment/terminal/command_filter.py` — see `docs/command_filter_usage.md`).

### MCP server layer

The published entry point is `py-ide4ai-mcp` → `ide4ai.python_ide.a2c_smcp.server:main`. Layout:

- **`ide4ai/a2c_smcp/`** — transport-agnostic base. `BaseMCPServer` (`server.py`) implements stdio / SSE / Streamable-HTTP runloops and calls abstract `_create_ide_instance`, `_register_tools`, `_register_resources`. `config.py` uses `confz` to merge defaults < env vars < CLI flags. Tool base + built-ins (`bash`, `glob`, `grep`, `read`, `edit`, `write`) live in `tools/`; resource base + `window` resource in `resources/`.
- **`ide4ai/python_ide/a2c_smcp/`** — `PythonIDEMCPServer` wires `PyIDESingleton` into `BaseMCPServer` and registers the Python toolset + `WindowResource`. Python-only tools belong under `ide4ai/python_ide/a2c_smcp/tools/`.

When adding a tool: define its input schema in `ide4ai/a2c_smcp/schemas/tools.py` (or the python-specific analogue), subclass `BaseTool`, and register it in the corresponding server's `_register_tools()`. Implement behavior by delegating to `IDE` / `PyWorkspace` / `PexpectTerminalEnv` methods rather than re-implementing filesystem or LSP logic (see `.windsurf/workflows/pyide-mcp.md`). MCP-facing tests live in `tests/integration/a2c_smcp/` and `tests/integration/python_ide/a2c_smcp/`.

### DTOs and LSP

`ide4ai/dtos/` holds Pydantic models mirroring LSP message shapes (`base_protocol`, `commands`, `diagnostics`, `file_resource`, `text_documents`, `workspace_edit`). `ide4ai/environment/workspace/model.py` implements the Monaco-style `TextModel` those DTOs feed into.

## Style and type checking

`ruff` (line-length 120, `py310`, selects E/W/F/I/B/C4/UP; ignores E501, B008, C901). `mypy` is strict: `disallow_untyped_defs`, `disallow_untyped_calls`, `no_implicit_optional`, `warn_unused_ignores`, `strict_equality`. New code needs full annotations. `__init__.py` files are exempt from `F401` so re-exports are fine.
