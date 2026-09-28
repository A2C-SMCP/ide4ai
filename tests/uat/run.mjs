/** Single UAT entry point: isolated Inspector, browser, assertions and evidence. */
import { spawn, execFileSync } from "node:child_process";
import { writeFileSync, createWriteStream, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import { createServer } from "node:net";
import { chromium } from "playwright";
import { InspectorPage } from "./inspector-page.mjs";
import { watchProcesses } from "./process-exit.mjs";
import { scenarios } from "./scenarios.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const args = process.argv.slice(2);
const name = args[0] || "smoke-dynamic-catalog";
if (!scenarios[name]) throw new Error(`Unknown executable scenario: ${name}`);
const portServer = createServer();
await new Promise((resolve) => portServer.listen(0, "127.0.0.1", resolve));
const port = portServer.address().port;
await new Promise((resolve) => portServer.close(resolve));
const prepare = [
  ".agents/skills/ide4ai-uat/scripts/prepare_run.py",
  "--scenario",
  name,
  "--client-port",
  String(port),
];
if (args.includes("--auto-refresh")) prepare.push("--auto-refresh");
const manifest = JSON.parse(
  execFileSync("python3", prepare, { cwd: root, encoding: "utf8" }),
);
manifest.inject_failure = args.includes("--inject-failure");
const report = {
  scenario: name,
  status: "BLOCKED",
  failureCategory: null,
  run_dir: manifest.run_dir,
  screenshots: [],
  cleanup: {},
};
console.log(`UAT ${name}: ${manifest.run_dir}`);
const log = createWriteStream(`${manifest.artifacts_dir}/inspector.log`);
let inspector, browser, context, page, ui;
let tracingStarted = false;
let interruptionAction = Promise.resolve();
let tracked = [];
let interrupted = false,
  closing = false;
function checkInterrupted() {
  if (interrupted) throw new Error("UAT interrupted");
}
for (const event of ["SIGINT", "SIGTERM"])
  process.once(event, () => {
    interrupted = true;
    if (closing) return;
    if (inspector)
      tracked = [...new Set([...tracked, ...ownedProcesses(inspector.pid)])];
    if (page)
      interruptionAction = page.close().catch((error) => {
        report.interruptionError = String(error);
      });
    else if (inspector) signal(-inspector.pid, "SIGINT");
  });
const processes = () =>
  execFileSync("ps", ["-axo", "pid=,ppid=,pgid="], { encoding: "utf8" })
    .trim()
    .split("\n")
    .map((line) => line.trim().split(/\s+/).map(Number));
function ownedProcesses(pid) {
  const rows = processes(),
    owned = new Set([pid]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const [id, parent, group] of rows)
      if (!owned.has(id) && (owned.has(parent) || group === pid)) {
        owned.add(id);
        changed = true;
      }
  }
  return [...owned];
}
function signal(pid, value) {
  try {
    process.kill(pid, value);
  } catch (error) {
    if (error.code !== "ESRCH") throw error;
  }
}
async function stop() {
  if (!inspector) return;
  let observer;
  try {
    observer = await watchProcesses(tracked);
  } catch (error) {
    signal(-inspector.pid, "SIGKILL");
    for (const pid of tracked) signal(pid, "SIGKILL");
    throw error;
  }
  const forced = [];
  const deadline = setTimeout(() => {
    for (const pid of observer.pending) {
      forced.push(pid);
      signal(pid, "SIGKILL");
    }
  }, 8000);
  try {
    const ended = inspector.exitCode !== null || inspector.signalCode !== null;
    let exitTimer;
    const exited = ended
      ? Promise.resolve()
      : new Promise((resolve, reject) => {
          inspector.once("exit", () => {
            clearTimeout(exitTimer);
            resolve();
          });
          exitTimer = setTimeout(
            () => reject(new Error("Inspector exit deadline exceeded")),
            14000,
          );
        });
    exited.catch(() => {});
    if (interrupted) for (const pid of observer.pending) signal(pid, "SIGTERM");
    if (!ended) signal(-inspector.pid, "SIGINT");
    const survivors = await observer.done;
    report.cleanup.surviving_pids = survivors;
    report.cleanup.forced_pids = forced;
    if (survivors.length) {
      for (const pid of survivors) signal(pid, "SIGKILL");
      throw new Error(`Inspector descendants survived shutdown: ${survivors}`);
    }
    await exited;
    if (forced.length && !interrupted)
      throw new Error(`Graceful cleanup exceeded its deadline: ${forced}`);
  } catch (error) {
    signal(-inspector.pid, "SIGKILL");
    for (const pid of observer.pending) signal(pid, "SIGKILL");
    throw error;
  } finally {
    clearTimeout(deadline);
  }
}

try {
  inspector = spawn(
    manifest.inspector.argv[0],
    manifest.inspector.argv.slice(1),
    {
      cwd: root,
      env: { ...process.env, ...manifest.inspector.env },
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  const ready = new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(
      () => reject(new Error("Inspector startup deadline exceeded")),
      45000,
    );
    const read = (data) => {
      output += data.toString();
      if (output.includes(manifest.inspector.url)) {
        clearTimeout(timer);
        resolve();
      }
    };
    inspector.stdout.on("data", read);
    inspector.stderr.on("data", read);
    inspector.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    inspector.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Inspector exited during startup: ${code}`));
    });
  });
  inspector.stdout.pipe(log, { end: false });
  inspector.stderr.pipe(log, { end: false });
  await ready;
  checkInterrupted();
  browser = await chromium.launch({
    headless: true,
    handleSIGINT: false,
    handleSIGTERM: false,
    handleSIGHUP: false,
    channel: process.env.UAT_BROWSER_CHANNEL || "chrome",
  });
  checkInterrupted();
  context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  checkInterrupted();
  await context.tracing.start({
    screenshots: true,
    snapshots: true,
    sources: true,
  });
  tracingStarted = true;
  page = await context.newPage();
  checkInterrupted();
  page.setDefaultTimeout(15000);
  ui = new InspectorPage(page, manifest.artifacts_dir);
  report.failureCategory = "inspector-compatibility";
  await ui.connect(manifest.inspector.url);
  report.failureCategory = "product";
  await scenarios[name](ui, manifest);
  checkInterrupted();
  if (args.includes("--inject-failure"))
    throw new Error("Intentional failure to verify UAT evidence and cleanup");
  report.status = "PASS";
  report.failureCategory = null;
} catch (error) {
  report.status = report.failureCategory ? "FAIL" : "BLOCKED";
  report.failureCategory = interrupted
    ? "interrupted"
    : error.uatCategory || report.failureCategory || "environment";
  if (interrupted) report.status = "BLOCKED";
  report.error = error.stack;
  if (page)
    await page
      .screenshot({
        path: `${manifest.artifacts_dir}/failure.png`,
        fullPage: true,
      })
      .catch(() => {});
} finally {
  closing = true;
  await interruptionAction;
  if (inspector)
    tracked = [...new Set([...tracked, ...ownedProcesses(inspector.pid)])];
  if (page && !page.isClosed()) {
    await page
      .locator("body")
      .ariaSnapshot()
      .then((text) =>
        writeFileSync(`${manifest.artifacts_dir}/final-ui.yml`, text),
      )
      .catch(() => {});
    await ui?.disconnect().catch((error) => {
      report.disconnectError = String(error);
      report.status = "FAIL";
    });
  }
  await stop().catch((error) => {
    report.cleanup.error = String(error);
    report.status = "FAIL";
  });
  if (tracingStarted)
    await context.tracing
      .stop({ path: `${manifest.artifacts_dir}/trace.zip` })
      .catch((error) => {
        report.traceError = String(error);
        report.status = "FAIL";
      });
  await browser?.close().catch((error) => {
    report.cleanup.browserError = String(error);
    report.status = "FAIL";
  });
  log.end();
  if (
    interrupted &&
    !report.cleanup.error &&
    !report.cleanup.browserError &&
    !report.traceError
  ) {
    report.status = "BLOCKED";
    report.failureCategory = "interrupted";
  }
  report.replay = `node tests/uat/run.mjs ${args.length ? args.join(" ") : name}`;
  report.screenshots = readdirSync(manifest.artifacts_dir).filter((name) =>
    name.endsWith(".png"),
  );
  report.inspector_version = manifest.inspector.version;
  report.auto_refresh = manifest.auto_refresh;
  writeFileSync(
    `${manifest.artifacts_dir}/report.json`,
    JSON.stringify(report, null, 2) + "\n",
  );
  writeFileSync(
    `${manifest.artifacts_dir}/report.md`,
    `# ${name}: ${report.status}\n\nRun: ${manifest.run_dir}\n\nReplay: \`${report.replay}\`\n\n\`\`\`json\n${JSON.stringify(report, null, 2)}\n\`\`\`\n`,
  );
  console.log(`${report.status}: ${manifest.artifacts_dir}/report.md`);
  if (report.error) console.error(report.error);
  if (report.cleanup.error) console.error(report.cleanup.error);
}
process.exitCode = interrupted ? 130 : report.status === "PASS" ? 0 : 1;
