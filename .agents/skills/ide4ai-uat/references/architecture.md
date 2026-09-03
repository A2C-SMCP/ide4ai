# UAT 架构

## 分层

```text
Codex / ide4ai-uat Skill
        |
        | 编排、判定、报告
        v
prepare_run.py ----> 隔离运行目录、Inspector config、manifest
        |
        v
run_inspector.py --> npx Inspector Web --> uv run ide4ai-mcp (stdio)
                                ^
                                |
                       Playwright 用户操作
                                |
                                v
                      场景断言、截图证据
```

- **Skill 编排层**：决定运行哪个场景、如何分类失败、如何收尾和报告。
- **运行隔离层**：生成一次性注册表与工作区，固定 Inspector 版本和网络边界。
- **UI 驱动层**：Playwright 只模拟 Inspector 用户，不绕过 UI 调 MCP。
- **场景契约层**：描述前置状态、用户动作、可观察断言和证据点。
- **证据层**：运行清单、截图和结论共用同一 `run_dir`，便于复核。

## 状态边界

- 仓库工作树是被测代码，只读使用，UAT 不自动修代码。
- `projects.json` 是单次运行私有状态，不复用用户配置。
- `workspace/` 是单次运行私有测试项目，场景只能在这里制造数据。
- Inspector config 使用 `--config` 只读加载，不写入 Inspector 全局 catalog。
- Inspector API token 只保存在临时 manifest，不进入报告或版本库。

## 扩展场景

新增场景时只在 `references/scenarios/` 添加一个 Markdown 契约，并在用户明确指定时加载。每个场景必须包含：

1. 一个可验证的用户目标；
2. 可从全新运行目录建立的前置状态；
3. 只通过 Inspector UI 完成的步骤；
4. 可见且无歧义的断言；
5. 截图或调用结果证据点；
6. 明确的非目标，防止场景无限膨胀。

只有所有场景共同需要的能力才进入脚本层。某个场景的业务参数、等待策略或断言不得硬编码进 `prepare_run.py` 或 `run_inspector.py`。

`prepare_run.py --scenario <name>` 只选择并记录场景，不替场景制造业务状态。通用准备阶段可以创建空注册表、工作区和基线文件；Inspector 连接成功后的文件、项目、Terminal 与 Resource 状态变化必须由 UI 中可见的 MCP 操作产生。

每个场景使用全新的运行目录。跨 Inspector 重启场景可以在同一次运行内复用该目录和注册表，但不得复用其他场景的状态。

## 后续自动化边界

当前 Codex 版本由 Skill 动态理解 Inspector UI 并调用 Playwright。等 smoke 稳定后，可以把稳定交互提炼为 Page Object 或 Playwright Test，但仍保留同一 manifest、隔离目录和场景契约。这样 AI 负责适应 UI 变化与诊断，确定性脚本负责重复执行与 CI 门禁，两者不会形成两套验收语义。
