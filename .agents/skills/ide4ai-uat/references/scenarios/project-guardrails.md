# project-guardrails

## 目标

验证无效项目元数据、重复注册、工具参数错误和 Terminal cwd 越界不会污染当前项目状态。

## 前置状态

- 使用 `prepare_run.py --scenario project-guardrails` 新建运行目录。
- `run_dir` 存在，`workspace_dir` 是其子目录。
- 项目名为 `uat-guardrails`。

## 步骤与断言

### 1. 规范化已有相对根目录并拒绝不存在路径

从 Inspector Server 的仓库根目录计算指向 `workspace_dir` 的已有相对路径，用它创建 `uat-guardrails`。随后用另一个项目名提交不存在的绝对目录 `<run_dir>/missing-root`。

断言首次创建成功，返回的 `root_dir` 已规范化为与 `workspace_dir` 相同的绝对位置；第二次调用返回明确的结构化错误。`project_list` 仍只有 `uat-guardrails`，`current_project` 仍为 `uat-guardrails`。保存 `01-project-root-contract.png`。

### 2. 创建有效项目并拒绝重复注册

复用已创建的 `uat-guardrails`，随后分别尝试：

- 使用不同大小写的同名项目和已有的不同根目录 `run_dir`；
- 使用不同名称和同一个根目录。

断言两次重复注册均失败；`project_list` 仍只有一个项目且当前项目不变。保存 `02-duplicate-projects.png`。

### 3. 拒绝无效工具参数

刷新 Tools，调用 `Glob` 时省略必填 `pattern`；调用 `Edit` 时令 `old_string` 与 `new_string` 相同。

断言两次调用均返回可见的参数或操作错误，不产生文件变化，也不触发目录变化通知。保存 `03-invalid-tool-input.png`。

### 4. 拒绝 Terminal cwd 越界

调用 `terminal_start`，把 cwd 设置为 `run_dir`（它位于项目根目录之外）。

断言调用失败并说明 cwd 必须位于当前项目根目录内。显式刷新 Tools，确认仍显示 `terminal_start`，没有任何 `shell_*` 工具；Resources 不出现 Shell Overview。保存 `04-terminal-boundary.png`。

### 5. 验证有效状态仍可用

用默认 cwd 成功调用 `terminal_start`，刷新后打开 Shell 并确认 cwd 等于项目根目录；随后调用 `terminal_close`。最后调用 `project_list`，确认唯一项目和当前选择保持正确。保存 `05-guardrails-recovery.png`。

## 非目标

`Read` 工具按产品契约可以读取任意绝对文件，本场景不把它误判为工作区沙箱。场景也不验证并发竞态、操作系统权限或恶意 Shell 命令过滤。
