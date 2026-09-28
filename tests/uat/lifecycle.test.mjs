import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

for (const mode of ["assertion", "interrupt"]) {
  test(
    `real Inspector failure lifecycle: ${mode}`,
    { timeout: 90000 },
    async () => {
      const runner = fileURLToPath(new URL("./run.mjs", import.meta.url));
      const child = spawn(
        process.execPath,
        [
          runner,
          "terminal-test-loop",
          ...(mode === "assertion" ? ["--inject-failure"] : []),
        ],
        { stdio: ["ignore", "pipe", "pipe"] },
      );
      let output = "",
        runDir,
        interrupted = false;
      child.stdout.on("data", (data) => {
        output += data.toString();
        runDir = /UAT terminal-test-loop: (.+)/.exec(output)?.[1];
        if (
          mode === "interrupt" &&
          !interrupted &&
          output.includes("UAT checkpoint: 02b-shell-opened.png")
        ) {
          interrupted = true;
          child.kill("SIGTERM");
        }
      });
      child.stderr.on("data", (data) => {
        output += data.toString();
      });
      const code = await new Promise((resolve, reject) => {
        child.once("exit", resolve);
        child.once("error", reject);
      });
      assert.equal(code, mode === "interrupt" ? 130 : 1, output);
      assert.ok(runDir, output);
      const report = JSON.parse(
        readFileSync(`${runDir}/artifacts/report.json`, "utf8"),
      );
      assert.equal(report.status, mode === "interrupt" ? "BLOCKED" : "FAIL");
      assert.equal(
        report.failureCategory,
        mode === "interrupt" ? "interrupted" : "product",
      );
      assert.deepEqual(report.cleanup.surviving_pids, []);
      assert.ok(report.screenshots.length >= 3);
      assert.ok(existsSync(`${runDir}/artifacts/trace.zip`));
      if (mode === "assertion")
        assert.ok(existsSync(`${runDir}/artifacts/failure.png`));
    },
  );
}
