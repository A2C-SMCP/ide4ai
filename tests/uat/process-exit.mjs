import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

/** Register OS exit watches before signalling descendants, including separate groups. */
export async function watchProcesses(pids) {
  const child = spawn(
    "python3",
    [
      fileURLToPath(new URL("./process_exit.py", import.meta.url)),
      "12",
      ...pids.map(String),
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  const pending = new Set();
  let readyResolve,
    readyReject,
    doneResolve,
    doneReject,
    completed = false,
    stderr = "";
  const ready = new Promise((resolve, reject) => {
    readyResolve = resolve;
    readyReject = reject;
  });
  const done = new Promise((resolve, reject) => {
    doneResolve = resolve;
    doneReject = reject;
  });
  // Prevent an early observer error from becoming an unhandled rejection.
  done.catch(() => {});
  createInterface({ input: child.stdout }).on("line", (line) => {
    const message = JSON.parse(line);
    if (message.kind === "ready") {
      for (const pid of message.value) pending.add(pid);
      readyResolve();
    }
    if (message.kind === "exit") pending.delete(message.value);
    if (message.kind === "done") {
      completed = true;
      doneResolve(message.value);
    }
  });
  child.stderr.on("data", (data) => {
    stderr += data.toString();
  });
  child.on("error", (error) => {
    readyReject(error);
    doneReject(error);
  });
  child.on("close", (code) => {
    if (code || !completed) {
      const error = new Error(`Process exit observer failed: ${stderr}`);
      readyReject(error);
      doneReject(error);
    }
  });
  await ready;
  return { pending, done };
}
