---
name: ide4ai-uat
description: "通过 MCP Inspector Web UI 和 Playwright 对本仓库的 ide4ai MCP 执行端到端验收。适用于验证动态工具刷新、项目状态持久化、Resource 列表与读取、Inspector 兼容性，或在功能变更后运行 UAT/冒烟回归。"
---

# ide4ai UAT

把 Inspector 当作真实 MCP 客户端，把 Playwright 当作唯一操作入口。不要用 Inspector CLI、直接 MCP SDK 调用或 HTTP 请求代替 UI 操作；命令行只负责准备隔离环境、启动和停止 Inspector。

框架分层、状态边界和后续场景扩展规则见 [UAT 架构](references/architecture.md)。

## 默认行为

- 用户没有指定场景时，运行 `smoke-dynamic-catalog`。
- 用户指定场景时，从 [场景索引](references/scenarios/index.md) 确认用途与依赖，然后只读取对应的场景文件。
- 使用仓库当前工作树，通过 `uv run ide4ai-mcp` 启动 MCP Server。
- 使用固定版本 `@modelcontextprotocol/inspector@2.4.0`，避免 `npx` 浮动升级改变验收结果。
- 每次运行创建独立的项目注册表、测试工作区和证据目录，不读取或修改用户现有 ide4ai 状态。
- 任何断言失败都算失败。不要因为刷新、重试或等待后偶然通过而隐藏首次失败。

## 前置检查

1. 确认当前目录属于 ide4ai 仓库，且 `pyproject.toml` 中项目名为 `ide4ai`。
2. 确认 Node.js `>=22.19.0`，并存在 `npx`、`uv`。
3. 确认本次会话具有 Playwright 浏览器操作能力。若没有，停止并报告缺失依赖；不要退化为 Inspector CLI。
4. 若用户指定了场景，先确认它出现在场景索引中，且对应文件存在于 `references/scenarios/`。

## 确定性执行入口

smoke 和 Terminal 场景优先使用已集中维护的 Page Object 执行器：

```bash
uv sync --group py
npm ci --prefix tests/uat
node tests/uat/run.mjs smoke-dynamic-catalog
node tests/uat/run.mjs terminal-test-loop
```

执行器自动通过 Playwright 操作 Inspector Web UI，并保存截图、trace、日志、报告及清理结果。
运行 `--auto-refresh` 可额外验收自动刷新；详见 [UAT README](../../../tests/uat/README.md)。
其他场景继续按下述步骤使用 Playwright 工具执行，不使用直接 MCP 调用替代。

## 准备并启动

从仓库根目录运行：

```bash
python3 .agents/skills/ide4ai-uat/scripts/prepare_run.py
```

指定场景时传入场景文件名（不含 `.md`）：

```bash
python3 .agents/skills/ide4ai-uat/scripts/prepare_run.py --scenario project-code-edit-loop
```

脚本向 stdout 输出一份 JSON 启动清单。取得其中的 `run_dir` 后，以长驻进程运行下面的命令；启动器会安全传递清单中的 argv 和环境变量，避免拼接 shell 文本：

```bash
python3 .agents/skills/ide4ai-uat/scripts/run_inspector.py <run_dir>/run-manifest.json
```

等待日志显示 Web 服务就绪，再访问清单中的 `inspector.url`。

准备脚本默认使用 `127.0.0.1:6274`。端口被占用时，改用明确端口重新准备，例如：

```bash
python3 .agents/skills/ide4ai-uat/scripts/prepare_run.py --client-port 6276
```

Inspector 的 `--config` 文件是只读输入；其中只有一个 `ide4ai-local` stdio Server。详细启动契约见 [Inspector 与 Playwright 契约](references/inspector-playwright.md)。

## 用 Playwright 执行

1. 打开 `inspector.url`，等待 Inspector 主界面可交互。
2. 通过可访问性角色、可见文本和最新页面快照定位元素。禁止依赖脆弱的 DOM 层级或用脚本直接篡改页面状态。
3. 选择 `ide4ai-local` 并点击连接；以 UI 的 connected 状态为准，不以进程存在代替连接成功。
4. 按场景文件逐步操作。连接成功后，工具调用、参数填写、刷新、Resource 订阅与读取都必须在 Inspector UI 内完成。
5. 按场景契约定义的检查点和文件名截图到清单的 `artifacts_dir`；默认 smoke 至少保存四张既定截图。
6. 若 UI 文案变化但语义入口仍明确，可以按语义继续；在报告中记录兼容性偏差。若语义不明确，停止并保留证据。

默认场景见 [动态目录 smoke](references/scenarios/smoke-dynamic-catalog.md)，其他场景按 [场景索引](references/scenarios/index.md) 选择。

需要从产品视角审阅全部场景的用户路线、预期结果和能力边界时，使用 [UAT 场景审阅稿](references/scenario-review.md)。

## 失败判定与复核

- 区分三类失败：产品失败（MCP 行为错误）、框架失败（Inspector/Playwright/环境不可用）、选择器漂移（UI 语义仍在但自动定位失效）。
- 首次失败后先截图并记录原始错误。只有在疑似时序问题时，才允许用全新的运行目录完整复跑一次。
- 第二次通过时结果仍标记 `FLAKY`，不能写成 `PASS`。
- 不要在同一运行目录中反复修补状态直到通过。

## 收尾与报告

1. 在 UI 中断开 MCP 连接。
2. 向启动 Inspector 的长驻进程发送中断并等待退出；不要用宽泛的 `pkill`。
3. 保留运行目录作为证据。只有用户明确要求清理时，才删除清单里的精确 `run_dir`。
4. 按 [报告模板](references/report-template.md) 将结论保存为清单中的 `<artifacts_dir>/report.md`，确保引用的截图文件名与当前场景契约完全一致，并给出运行目录的绝对路径。

最终状态只能是：

- `PASS`：全部断言首次通过。
- `FAIL`：产品行为不符合场景契约。
- `FLAKY`：首次失败、全新隔离复跑通过。
- `BLOCKED`：框架或依赖无法执行，尚未验证产品行为。
