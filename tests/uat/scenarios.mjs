import assert from "node:assert/strict";
import { realpathSync } from "node:fs";
export const projectTools = [
  "project_create",
  "project_delete",
  "project_list",
  "project_switch",
];
export const ideTools = [
  ...projectTools,
  "Glob",
  "Grep",
  "Read",
  "Edit",
  "Write",
  "Lsp",
  "terminal_start",
  "project_unload",
];

export const scenarios = {
  "terminal-test-loop": async (ui, manifest) => {
    await ui.call("project_create", {
      Name: "uat-terminal-loop",
      "Root Dir": manifest.workspace_dir,
    });
    await ui.refreshTools();
    const written = await ui.call("Write", {
      "File Path": `${manifest.workspace_dir}/app.py`,
      Content: 'print("UAT_TERMINAL_OK")\n',
    });
    assert.equal(written.success, true);
    await ui.screenshot("01-terminal-fixture.png");
    await ui.clearProtocol();
    const started = await ui.call("terminal_start");
    assert.equal(started.terminal.state, "open");
    await ui.notification("notifications/tools/list_changed");
    await ui.notification("notifications/resources/list_changed");
    await ui.refreshTools();
    await ui.assertTools([
      ...ideTools.filter((name) => name !== "terminal_start"),
      "terminal_close",
      "shell_open",
      "shell_exec",
      "shell_read",
      "shell_write",
      "shell_signal",
      "shell_list",
      "shell_close",
    ]);
    await ui.screenshot("02-terminal-tools.png");
    const opened = await ui.call("shell_open");
    assert.equal(
      realpathSync(opened.cwd),
      realpathSync(manifest.workspace_dir),
    );
    await ui.screenshot("02b-shell-opened.png");
    const result = await ui.call("shell_exec", {
      "Shell Id": opened.shell_id,
      Command: "python app.py",
    });
    assert.equal(result.exit_code, 0);
    assert.match(result.output, /UAT_TERMINAL_OK/);
    await ui.screenshot("03-terminal-command.png");
    if (manifest.inject_failure)
      throw new Error("Intentional assertion failure with a live Shell");
    await ui.resources({ refresh: true });
    await ui.assertResourceNames([
      "IDE Window - uat-terminal-loop",
      "Shell Overview",
    ]);
    const names = await ui.resourceNames();
    const overview = names.find((name) => /shell/i.test(name));
    assert.ok(overview, "Shell Overview must be in the resource catalog");
    const content = await ui.readResource(overview);
    assert.match(content, /UAT_TERMINAL_OK/);
    assert.ok(content.includes(opened.shell_id));
    await ui.screenshot("04-shell-overview.png");
    await ui.clearProtocol();
    await ui.call("terminal_close");
    await ui.notification("notifications/tools/list_changed");
    await ui.notification("notifications/resources/list_changed");
    await ui.refreshTools();
    await ui.assertTools(ideTools);
    await ui.resources({ refresh: true });
    await ui.assertResourceNames(["IDE Window - uat-terminal-loop"]);
    assert.match(
      await ui.readResource("IDE Window - uat-terminal-loop"),
      /当前工作区: uat-terminal-loop/,
    );
    await ui.screenshot("05-terminal-closed.png");
  },
  "smoke-dynamic-catalog": async (ui, manifest) => {
    await ui.screenshot("01-connected.png");
    await ui.assertTools(projectTools);
    await ui.screenshot("02-initial-tools.png");
    await ui.resources();
    assert.deepEqual(await ui.resourceNames(), []);
    const created = await ui.call("project_create", {
      Name: "uat-smoke",
      "Root Dir": manifest.workspace_dir,
    });
    assert.equal(created.project.name, "uat-smoke");
    await ui.notification("notifications/tools/list_changed");
    await ui.notification("notifications/resources/list_changed");
    if (!manifest.auto_refresh) await ui.refreshTools();
    else await ui.waitTool("terminal_start");
    await ui.assertTools(ideTools);
    await ui.screenshot("03-refreshed-tools.png");
    await ui.resources({ refresh: !manifest.auto_refresh });
    const resource = await ui.readResource("IDE Window - uat-smoke");
    assert.match(resource, /当前工作区: uat-smoke/);
    await ui.screenshot("04-window-resource.png");
    const listed = await ui.call("project_list");
    assert.equal(listed.current_project, "uat-smoke");
    assert.equal(
      realpathSync(listed.projects[0].root_dir),
      realpathSync(manifest.workspace_dir),
    );
  },
};
