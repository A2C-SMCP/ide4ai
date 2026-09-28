# smoke-dynamic-catalog

## 目标

验证 ide4ai MCP 在真实 Inspector 会话中的最小系统闭环：空注册表启动、项目状态写入、动态工具目录通知、动态 Resource 目录与读取。

## 前置状态

- 使用 `prepare_run.py` 新建的运行目录。
- `projects.json` 在连接前不存在。
- 测试项目名称固定为 `uat-smoke`。
- `root_dir` 使用启动清单中的绝对 `workspace_dir`。
- Inspector 配置的 `autoRefreshOnListChanged` 为 `false`，从而同时验证通知提示与显式刷新。

## 步骤与断言

### 1. 连接空状态 Server

在 Inspector 中选择 `ide4ai-local` 并连接。

断言：

- UI 显示连接成功。
- Tools 初始列表恰好包含 `project_create`、`project_delete`、`project_list`、`project_switch`。
- Resources 初始列表为空。

保存 `01-connected.png` 和 `02-initial-tools.png`。

### 2. 创建项目

在 Tools 中调用 `project_create`：

```json
{
  "name": "uat-smoke",
  "root_dir": "<manifest.workspace_dir>"
}
```

断言：

- 调用结果没有 MCP error。
- Inspector 显示 Tools 列表已变化的提示；Resources 入口显示列表已变化的提示，或在进入 Resources 后可观察到对应待刷新状态。

### 3. 显式刷新动态目录

通过 Inspector UI 刷新 Tools。

断言刷新后的列表至少包含：

- `Glob`
- `Grep`
- `Read`
- `Edit`
- `Write`
- `Lsp`
- `terminal_start`
- `project_unload`

同时断言项目管理工具仍然存在。保存 `03-refreshed-tools.png`。

### 4. 刷新并读取 Resource

进入 Resources，通过 Inspector UI 执行刷新。

断言：

- 至少出现一个 URI 以 `window://` 开头的项目 Resource。
- 从 UI 读取该 Resource 成功，没有 MCP error。
- 展示内容属于 `uat-smoke` 工作区；若内容包含标题或项目标识，应与当前项目一致。

保存 `04-window-resource.png`。

### 5. 验证持久状态可见性

在 Tools 中调用 `project_list`。

断言：

- 返回集合顶层的 `current_project` 为 `uat-smoke`。
- 项目列表包含 `uat-smoke`，其 `root_dir` 与启动清单的 `workspace_dir` 一致。

## 非目标

本 smoke 不启动 Terminal Runtime、不执行 Shell、不配置语言服务器，也不覆盖跨 Inspector 重启恢复。后续场景应在独立文件中扩展，不能把所有验收堆入本场景。
