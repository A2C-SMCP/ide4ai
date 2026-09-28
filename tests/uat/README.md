# Inspector Web UAT

From the repository root:

```bash
uv sync --group py
npm ci --prefix tests/uat
node tests/uat/run.mjs
node tests/uat/run.mjs terminal-test-loop
node tests/uat/run.mjs smoke-dynamic-catalog --auto-refresh
```

Requires Node >=22.19, `uv`, Python, and Google Chrome. The launcher uses installed
Chrome by default; set `UAT_BROWSER_CHANNEL=chromium` after installing the pinned
Playwright browser with `cd tests/uat && npx playwright install chromium` to use
bundled Chromium. Inspector is pinned at 2.4.0 and Playwright at 1.63.0.

Each invocation creates a new isolated workspace and registry, chooses an available
loopback port, and starts Inspector using a read-only `--config`. The only MCP client
is the Inspector Web UI. Playwright drives all project/tool/resource operations.
`inspector-page.mjs` owns all UI selectors; `scenarios.mjs` contains assertions and
business steps. Add scenarios there using the same Page Object and no custom process,
connection, screenshot, or cleanup machinery. The remaining six scenario contracts
in `.agents/skills/ide4ai-uat/references/scenarios/` are executed through the Skill and
Playwright; they have not been converted into deterministic Node scenarios.

The default smoke observes list-changed notifications and explicit refresh.
`--auto-refresh` validates Inspector `protocolEra=legacy` with
`autoRefreshOnListChanged=true`. The Terminal scenario validates all seven Shell
tools, cwd, command exit code/output, Shell Overview, and bounded close. Resource
Templates are not implemented by ide4ai: the Inspector may show a combined warning,
so `resources/list`, `resources/read` and `resources/templates/list` must be evaluated
separately. The first two must succeed; Templates `Method not found` is expected.

Artifacts stay in the printed run directory: screenshots, Playwright trace,
Inspector/stdio log, final UI snapshot, and JSON/Markdown report with replay command.
Replay always creates a new isolated run. Initial failures remain FAIL; no automatic
retry turns them into PASS. An explicit full rerun after a transient failure should
be reported as FLAKY together with both run directories. Missing environment is
BLOCKED. Assertion/behavior failures are product failures; startup/connect failures
are environment/Inspector failures. Timeouts retain their stage for diagnosis and
are not automatically called selector drift.

On success, failure, SIGINT or SIGTERM, the runner disconnects through the UI when
possible, stops its Inspector process group, closes the browser, and watches captured
descendant PIDs (including Shells with separate process groups) using macOS/BSD
`kqueue` or Linux `pidfd` exit events. Cleanup has an 8-second grace period and a
12-second observation deadline; remaining processes receive SIGKILL. Forced cleanup
during normal execution is a failure, while interrupted runs record forced PIDs. No workspace or evidence is deleted.

To test failure evidence and cleanup with a live Shell:

```bash
node tests/uat/run.mjs terminal-test-loop --inject-failure
```

This intentionally exits nonzero with FAIL; `cleanup.surviving_pids` must be empty
and `failure.png` plus `trace.zip` must exist. It is a framework self-test, not a
product acceptance result. Interrupt the same entry point to verify interruption
cleanup and a BLOCKED report. Pytest remains the fast unit/integration regression
layer; Web UAT supplements it and is invoked explicitly, outside `poe test`.

Run the reproducible assertion-failure and SIGTERM cleanup self-tests with
`node --test tests/uat/lifecycle.test.mjs`. Both use an actual Inspector session and
a live Shell; their expected FAIL/BLOCKED reports are separate from product PASS runs.
