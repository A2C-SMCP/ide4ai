# terminal-test-loop

## 目标

验证 AI Agent 在修改代码后启动项目级 Terminal、执行验证命令、查看 Shell 状态并安全关闭 Runtime 的完整闭环。

## 前置状态

- 使用 `prepare_run.py --scenario terminal-test-loop` 新建运行目录。
- 项目名为 `uat-terminal`，根目录为清单的 `workspace_dir`。
- 本机 Python 和内嵌 TFBash Runtime 可用。

## 步骤与断言

### 1. 准备可执行文件

连接并创建项目，刷新 Tools 后用 `Write` 创建 `<workspace_dir>/app.py`；先通过 `Enlarge Content` 在多行编辑器中填写：

```python
print("UAT_TERMINAL_OK")
```

断言写入成功。保存 `01-terminal-fixture.png`。

### 2. 启动 Terminal Runtime

调用 `terminal_start`，断言结果没有 MCP error、`terminal.state` 为 `open`，并观察到 Tools 与 Resources 的列表变化通知。

显式刷新 Tools，断言 `terminal_start` 消失，`terminal_close`、`shell_open`、`shell_exec`、`shell_read`、`shell_write`、`shell_signal`、`shell_list`、`shell_close` 出现。保存 `02-terminal-tools.png`。

### 3. 打开 Shell 并执行验证

调用 `shell_open`，断言返回的 cwd 与规范化后的 `workspace_dir` 相同。调用 `shell_exec` 执行：

```text
python app.py
```

断言调用没有 MCP error；执行完成、退出码为 `0`，输出包含 `UAT_TERMINAL_OK`。保存 `03-terminal-command.png`。

### 4. 读取 Shell Overview

刷新 Resources，断言除 IDE Window 外还出现 URI 为 `window://io.github.a2c-smcp.tfbash/shell-overview` 的 Resource。通过 UI 读取它，确认内容包含当前 shell、项目 cwd 和最近命令输出。保存 `04-shell-overview.png`。

### 5. 关闭 Runtime

调用 `terminal_close`，观察目录变化通知并显式刷新 Tools 与 Resources。

断言 Shell 工具和 Shell Overview 消失，`terminal_start` 恢复，IDE Window 仍可读取。保存 `05-terminal-closed.png`。

## 非目标

本场景不验证后台长任务、强制回收、信号处理、多项目隔离或 Resource 订阅更新。
