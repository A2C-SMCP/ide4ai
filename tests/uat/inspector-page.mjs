import assert from "node:assert/strict";
import { expect } from "playwright/test";

/** All Inspector selectors live here; scenarios only express MCP behavior. */
export class InspectorPage {
  constructor(page, artifacts) {
    this.page = page;
    this.artifacts = artifacts;
  }
  button(name) {
    return this.page.getByRole("button", { name, exact: true });
  }
  async connect(url) {
    await this.page.goto(url);
    const control = this.page.getByRole("switch", {
      name: 'Connect or disconnect "ide4ai-local"',
      exact: true,
    });
    await control.focus();
    await control.press("Space"); // Mantine's visual track overlays its input.
    await this.button("Disconnect from server").waitFor();
  }
  async screen(name) {
    await this.page.getByRole("radio", { name, exact: true }).press("Space");
    await this.page.getByRole("heading", { name, exact: true }).waitFor();
  }
  async toolNames() {
    await this.screen("Tools");
    await this.button("project_create").waitFor();
    // The named tool buttons contain a paragraph; action buttons do not.
    return this.page
      .getByRole("button")
      .filter({ has: this.page.locator("p") })
      .allTextContents();
  }
  async waitTool(name) {
    await this.screen("Tools");
    await this.button(name).waitFor();
  }
  async refreshTools() {
    await this.screen("Tools");
    await this.button("Refresh").click();
    await this.button("Refresh").waitFor({ state: "hidden" });
  }
  async call(name, fields = {}) {
    await this.screen("Tools");
    await this.button(name).click();
    try {
      await this.button("Execute Tool").waitFor();
      await this.page
        .getByRole("heading", { name: "Results", exact: true })
        .waitFor({ state: "hidden" });
      for (const [label, value] of Object.entries(fields)) {
        const input = this.page.getByRole("textbox", {
          name: label,
          exact: true,
        });
        const text = typeof value === "string" ? value : JSON.stringify(value);
        if (text.includes("\n")) {
          await this.button(`Enlarge ${label}`).click();
          await this.page
            .locator("textarea")
            .filter({ visible: true })
            .waitFor();
        }
        await input.fill(text);
      }
    } catch (error) {
      error.uatCategory = "selector-drift";
      throw error;
    }
    await this.button("Execute Tool").click();
    await this.page
      .getByRole("heading", { name: "Results", exact: true })
      .waitFor();
    const output = this.page.locator("code").filter({ visible: true });
    await output.first().waitFor();
    return JSON.parse(await output.first().innerText());
  }
  async clearProtocol() {
    await this.button("Clear").click();
  }
  async notification(method) {
    await this.page.getByText(method, { exact: true }).first().waitFor();
  }
  async resources({ refresh = false } = {}) {
    await this.screen("Resources");
    if (refresh) {
      if (await this.button("Close preview").isVisible())
        await this.button("Close preview").click();
      await this.button("Refresh").click();
      await this.button("Refresh").waitFor({ state: "hidden" });
    }
  }
  async assertResourceNames(expected) {
    const buttons = this.page
      .getByRole("region", { name: /^URIs/ })
      .getByRole("button");
    await expect(buttons).toHaveCount(expected.length);
    for (const name of expected) await this.button(name).waitFor();
    assert.deepEqual(
      (await buttons.allTextContents()).sort(),
      [...expected].sort(),
    );
  }
  async resourceNames() {
    return this.page
      .getByRole("region", { name: /^URIs/ })
      .getByRole("button")
      .allTextContents();
  }
  async readResource(name) {
    await this.resources();
    await this.button(name).click();
    await this.page.getByText(/^Last updated:/).waitFor();
    return await this.page.locator("body").innerText();
  }
  async screenshot(name) {
    await this.page.screenshot({
      path: `${this.artifacts}/${name}`,
      fullPage: true,
    });
    console.log(`UAT checkpoint: ${name}`);
  }
  async disconnect() {
    const button = this.button("Disconnect from server");
    if (await button.isVisible()) {
      await button.click();
      await button.waitFor({ state: "hidden" });
    }
  }
  async assertTools(expected) {
    await this.screen("Tools");
    const buttons = this.page
      .getByRole("button")
      .filter({ has: this.page.locator("p") });
    await expect(buttons).toHaveCount(expected.length);
    for (const name of expected) await this.button(name).waitFor();
    const names = (await this.toolNames()).map((name) => name.trim()).sort();
    assert.deepEqual(names, [...expected].sort());
  }
}
