# multi-project-switch

## 目标

验证 AI Agent 在两个项目之间切换时，当前项目、文件访问语义、Terminal Runtime 和 Resource 内容不会串线。

## 前置状态

- 使用 `prepare_run.py --scenario multi-project-switch` 新建运行目录。
- 临时引导项目名为 `uat-bootstrap`，根目录为 `workspace_dir`。
- 项目 A 名为 `uat-project-a`，根目录为 `<workspace_dir>/project-a`。
- 项目 B 名为 `uat-project-b`，根目录为 `<workspace_dir>/project-b`。
- A、B 两个同级目录必须通过引导项目的 Inspector Terminal 创建，不能用本地 shell 预造业务状态。

## 步骤与断言

### 1. 通过引导项目建立两个独立根目录

创建引导项目，启动 Terminal、打开 Shell，并通过 `shell_exec` 执行 `mkdir -p project-a project-b`。关闭引导项目的 Terminal，然后注册项目 A 和 B，调用 `project_switch` 切换到 A。

断言建目录命令退出码为 `0`；A、B 的注册根目录互不嵌套且分别等于两个规范化后的同级目录。保存 `01-independent-project-roots.png`。

### 2. 建立项目 A 状态并切换到 B

在 A 中用 `Write` 创建 `<workspace_dir>/project-a/project-a.txt`，内容为 `PROJECT_A`。启动 A 的 Terminal 并打开 Shell，然后调用 `project_switch` 切换到 B，显式刷新 Tools 与 Resources。

断言当前项目变为 B；B 只显示 `terminal_start`，不显示项目 A 已打开 Runtime 的 Shell 工具；对 B 执行 `Glob` 时看不到 `project-a.txt`，IDE Window 标识 B 且不包含 `PROJECT_A` 或 `project-a.txt`。保存 `02-switched-project-b.png`。

### 3. 建立项目 B 状态

用 `Write` 创建 `<workspace_dir>/project-b/project-b.txt`，内容为 `PROJECT_B`。启动 B 的 Terminal 并打开 Shell。

断言 B 的 Shell cwd 等于规范化后的项目 B 根目录。保存 `03-project-b-state.png`。

### 4. 切回项目 A

调用 `project_switch` 切回 A，刷新目录并调用 `shell_list`。

断言 A 的原 Shell 仍存在且 cwd 属于 A；对 A 执行 `Glob` 时看不到 `project-b.txt`；IDE Window 标识 A、包含 `project-a.txt`，且不包含 `PROJECT_B` 或 `project-b.txt`。保存 `04-returned-project-a.png`。

### 5. 再次验证项目 B 并收尾

切回 B，断言 `shell_list` 只返回 B 的 Shell 且 cwd 属于 B；再次读取 IDE Window，确认包含 `project-b.txt` 且不包含 A 的标记。分别在 B、A 调用 `terminal_close`，确认每次关闭只改变当前项目的 Terminal 目录状态。保存 `05-project-isolation.png`。

## 非目标

本场景不验证并发切换、删除繁忙项目或跨 Server 进程共享 Runtime。引导项目只负责通过 Inspector 创建夹具目录，不参与 A/B 的隔离断言。
