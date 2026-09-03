# restart-persistence

## 目标

验证项目注册和当前选择在 Inspector/MCP Server 完整重启后从同一隔离注册表恢复。

## 前置状态

- 使用 `prepare_run.py --scenario restart-persistence` 新建运行目录。
- 两次 Inspector 会话复用同一个 `run-manifest.json`、`projects.json` 和 `workspace_dir`。
- 不复用其他 UAT 场景的运行目录。

## 步骤与断言

### 1. 第一会话写入状态

启动 Inspector，连接 Server，创建项目 `uat-restart`，根目录为 `workspace_dir`。刷新 Tools 后用 `Write` 创建 `<workspace_dir>/restart-marker.txt`，内容为 `PERSISTED`。

调用 `project_list`，断言 `current_project` 为 `uat-restart`。保存 `01-before-restart.png`。

### 2. 完整停止第一会话

在 UI 中断开连接，向本次 Inspector 长驻进程发送中断并等待退出。不得删除或修改运行目录、注册表和 manifest。

断言第一进程已退出。该检查点记录进程退出摘要，不用产品 API 代替。

### 3. 使用同一 manifest 重启

再次执行 `run_inspector.py <run_dir>/run-manifest.json`，通过新的 Inspector 页面连接 `ide4ai-local`。

断言连接后无需重新创建项目，Tools 初始目录已经包含项目工具、文件工具、`Lsp`、`terminal_start` 和 `project_unload`。保存 `02-after-restart-tools.png`。

### 4. 验证恢复状态

调用 `project_list`，断言注册项目包含 `uat-restart`、`current_project` 为 `uat-restart`，根目录与规范化后的 `workspace_dir` 相同。

用 `Read` 读取 `restart-marker.txt`；刷新并读取 IDE Window Resource，确认内容属于恢复后的项目。保存 `03-restored-project.png` 和 `04-restored-resource.png`。

## 非目标

本场景不验证进程崩溃时的写入原子性、多个 Server 同时写注册表、旧版注册表迁移或 Terminal Runtime 跨进程恢复。
