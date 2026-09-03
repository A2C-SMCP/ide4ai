# UAT 场景索引

用户未指定场景时运行 `smoke-dynamic-catalog`。用户指定名称时，只加载对应场景契约及其直接引用的公共规则。

| 场景 | 用途 | 额外依赖 |
|---|---|---|
| `smoke-dynamic-catalog` | 最小连接、动态目录和项目状态冒烟 | 无 |
| `project-code-edit-loop` | 搜索、读取、创建和精确编辑代码 | `rg` |
| `terminal-test-loop` | 修改后启动 Terminal 并运行验证 | Python、TFBash Runtime |
| `multi-project-switch` | 两个项目间的工具、Resource 和 Terminal 隔离 | TFBash Runtime |
| `restart-persistence` | Inspector 重启后的注册表与当前项目恢复 | 同一运行目录内重启 Inspector |
| `terminal-resource-updates` | Shell Overview 的订阅与事件驱动更新 | Inspector Resource Subscribe、TFBash Runtime |
| `lsp-python-workflow` | Python LSP 状态、重载和持久配置 | `pyright-langserver` |
| `project-guardrails` | 项目、参数和工作区边界错误 | 无 |

每个场景独立创建运行目录并单独报告 `PASS`、`FAIL`、`FLAKY` 或 `BLOCKED`。不要把多个场景串在同一状态目录中执行。
