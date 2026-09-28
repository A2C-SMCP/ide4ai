# terminal-resource-updates

## 目标

验证订阅 Shell Overview 后，Shell 状态和输出变化通过 `notifications/resources/updated` 事件通知 Inspector，而不是依赖轮询。

## 前置状态

- 使用 `prepare_run.py --scenario terminal-resource-updates` 新建运行目录。
- 项目名为 `uat-resource-events`，根目录为 `workspace_dir`。
- Inspector UI 提供 Resource 的 Subscribe/Unsubscribe 入口。

## 步骤与断言

### 1. 暴露 Shell Overview

连接、创建项目并调用 `terminal_start`。显式刷新 Tools 与 Resources。

断言 Shell 工具和 `window://io.github.a2c-smcp.tfbash/shell-overview` 均出现。保存 `01-shell-resource.png`。

### 2. 订阅 Resource

选择 Shell Overview 并点击 Subscribe。

断言 UI 显示已订阅状态，Protocol 监控区的订阅请求成功且没有 MCP error。保存 `02-resource-subscribed.png`。

### 3. 触发内容更新

调用 `shell_open`，再调用 `shell_exec` 执行：

```text
echo UAT_RESOURCE_UPDATED
```

不要定时刷新或循环探测。等待 Inspector 可见的 `notifications/resources/updated`，断言通知 URI 与 Shell Overview URI 相同。保存 `03-resource-update-event.png`。

### 4. 读取更新内容

通过 Resource 面板的可见刷新/读取动作更新预览，断言内容包含当前 Shell、项目 cwd 和 `UAT_RESOURCE_UPDATED`。保存 `04-updated-shell-overview.png`。

### 5. 取消订阅并收尾

点击 Unsubscribe，断言请求成功；调用 `terminal_close` 并显式刷新目录，确认 Shell Overview 消失。保存 `05-resource-unsubscribed.png`。

## 非目标

本场景不通过 sleep-loop、重复刷新或 HTTP 探针验证更新，不测高频事件合并、断线重连补发或多个订阅者。
