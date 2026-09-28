# ide4ai UAT 场景审阅稿

本文用于产品和工程审阅当前 UAT 是否覆盖真实项目工作场景。每个场景按“用户目标、路线、检查点与预期、证明范围、非目标”描述。

## 审阅状态

| 场景 | 当前状态 | 审阅结论 |
|---|---|---|
| `smoke-dynamic-catalog` | 本轮确定性执行器 PASS（手动/自动刷新） | [ ] 符合 [ ] 调整 |
| `project-code-edit-loop` | Inspector UI 实跑 PASS | [ ] 符合 [ ] 调整 |
| `terminal-test-loop` | 本轮确定性执行器 PASS | [ ] 符合 [ ] 调整 |
| `multi-project-switch` | PR #36 已记录实跑 PASS，本轮未重跑 | [ ] 符合 [ ] 调整 |
| `restart-persistence` | PR #36 已记录实跑 PASS，本轮未重跑 | [ ] 符合 [ ] 调整 |
| `terminal-resource-updates` | PR #36 已记录实跑 PASS，本轮未重跑 | [ ] 符合 [ ] 调整 |
| `lsp-python-workflow` | PR #36 已记录实跑 PASS，本轮未重跑 | [ ] 符合 [ ] 调整 |
| `project-guardrails` | PR #36 已记录实跑 PASS，本轮未重跑 | [ ] 符合 [ ] 调整 |

## 统一验收路线与规则

所有场景遵循同一条基础路线：

```text
创建独立运行目录
→ 生成独立 projects.json、workspace、artifacts
→ 启动固定版本 Inspector
→ 在 Inspector UI 连接 ide4ai MCP
→ 只通过 UI 调用工具、刷新目录和读取 Resource
→ 按检查点截图
→ 在 UI 断开连接并停止本次进程
→ 保存 artifacts/report.md
```

统一约束：

- Inspector 固定使用 `@modelcontextprotocol/inspector@2.4.0`。
- 每个场景使用独立工作区和项目注册表，不读取或修改用户现有 ide4ai 状态。
- Inspector 连接后，不允许用本地 Shell、HTTP、Inspector CLI 或 MCP SDK 绕过 UI 制造业务状态。
- 多行参数必须通过 Inspector 的 `Enlarge <字段名>` 编辑器输入。
- macOS 上 `/var/...` 与 `/private/var/...` 按规范化后的真实文件位置比较，不做原始字符串相等判断。
- Inspector 可能将 Resource 错误合并展示，报告必须分别判断 `resources/list`、`resources/read` 和 `resources/templates/list`。
- 等待动态变化时依据 Inspector 已显示的通知、状态或可见条件，不使用 sleep-loop 轮询。
- 每个场景必须在自己的 `artifacts_dir` 保存截图和 `report.md`。
- 首次断言失败必须保留证据，不允许通过原地反复重试隐藏失败。

最终状态定义：

- `PASS`：所有断言首次通过。
- `FAIL`：产品行为不符合场景契约。
- `FLAKY`：首次失败，使用全新隔离运行目录复跑才通过。
- `BLOCKED`：Inspector、Playwright 或必要依赖不可用，尚未验证产品行为。

---

## 场景 1：最小动态目录冒烟

场景名：`smoke-dynamic-catalog`

### 用户目标

用户首次启动 ide4ai，当前没有任何项目。注册项目后，项目级代码工具与工作区 Resource 应动态出现，当前项目状态应可查询。

### 路线

```text
空注册表启动
→ 连接 MCP
→ 检查初始工具与 Resource
→ 创建项目
→ 观察目录变化通知
→ 显式刷新 Tools
→ 刷新并读取 IDE Window Resource
→ project_list 检查当前项目
```

### 检查点与预期

1. 连接空状态 Server
   - Inspector 显示连接成功。
   - 初始 Tools 恰好只有 `project_create`、`project_delete`、`project_list`、`project_switch`。
   - 初始 Resources 为空。
   - 证明未选择项目时不会错误暴露文件、LSP 或 Terminal 能力。

2. 创建项目
   - 创建 `uat-smoke`，根目录使用清单中的绝对 `workspace_dir`。
   - 调用无 MCP error。
   - Inspector 显示 Tools 和 Resources 列表变化提示或待刷新状态。

3. 刷新动态工具目录
   - 至少出现 `Glob`、`Grep`、`Read`、`Edit`、`Write`、`Lsp`、`terminal_start`、`project_unload`。
   - 原有项目管理工具继续存在。

4. 读取项目 Resource
   - `resources/list` 返回至少一个 `window://...` 项目 Resource。
   - `resources/read` 成功，内容属于 `uat-smoke`。
   - 如果 `resources/templates/list` 未实现，不得把它的错误误判成项目 Resource 读取失败。

5. 查询项目状态
   - `project_list.current_project == "uat-smoke"`。
   - 项目列表包含 `uat-smoke`。
   - 返回根目录与规范化后的 `workspace_dir` 指向同一位置。

### 证明范围

- 空状态启动正常。
- 项目注册可用。
- Tools 与 Resources 会随项目状态动态刷新。
- IDE Window 可读取。
- 当前项目状态可查询。

### 非目标

- 不启动 Terminal 或执行 Shell。
- 不配置 LSP。
- 不验证重启恢复或多项目隔离。
- 该场景保持最小、快速，不继续堆叠完整开发流程。

### 审阅意见

- [ ] 路线符合预期
- [ ] 需要调整：

---

## 场景 2：项目代码编辑闭环

场景名：`project-code-edit-loop`

### 用户目标

AI Agent 在真实项目里完成一次“创建文件、找到目标、读取上下文、精确修改、再次验证”的日常代码编辑任务。

### 路线

```text
创建项目
→ Write 创建 app.py
→ Read 检查完整内容
→ Glob 找到 Python 文件
→ Grep 定位 TODO
→ Edit 精确替换
→ Read 验证工作区新内容
→ IDE Window 验证当前项目视图
```

### 检查点与预期

1. 建立项目
   - 创建 `uat-code-loop`。
   - 刷新后 `Write`、`Glob`、`Grep`、`Read`、`Edit` 均可见。

2. 创建代码
   - 通过 `Enlarge Content` 写入：

     ```python
     def greeting(name: str) -> str:
         # TODO: personalize greeting
         return "hello"


     print(greeting("ide4ai"))
     ```

   - `Write.success == true`。
   - `Read` 能看到完整多行内容，换行和缩进没有被压平。

3. 定位目标
   - `Glob("**/*.py")` 返回 `app.py`。
   - `Grep("TODO", output_mode="content", line_number=true)` 只命中目标注释并带准确行号。

4. 精确编辑
   - `Edit.file_path` 使用 `<workspace_dir>/app.py` 绝对路径。
   - 将唯一的 `return "hello"` 替换为 `return f"hello, {name}"`。
   - 预期 `success == true` 且 `replacements_made == 1`。
   - 再次 `Read` 时新逻辑存在、旧 return 消失、其他代码未被破坏。

5. 验证 IDE Window
   - Resource URI 以 `window://` 开头。
   - 内容标识当前项目为 `uat-code-loop`。
   - 目录包含 `app.py`，打开文件内容包含修改后的代码。

### 证明范围

- Agent 可以创建代码文件。
- 文件发现、文本定位和上下文读取可用。
- Edit 可以完成唯一、精确的代码替换。
- 修改后的 IDE 工作区状态可以通过 Read 和 IDE Window 观察。

### 重要预期边界

当前 `Edit` 更新的是 IDE 工作区模型。本场景通过 `Read` 验证修改后的内存态，不用基于磁盘的 `Grep` 证明自动保存。

如果产品预期是“Edit 后外部测试命令、Git 和磁盘搜索必须立即看到新内容”，则还需要增加保存文件能力或明确 Edit 自动保存契约。

### 非目标

- 不执行修改后的程序。
- 不验证自动保存。
- 不启动 Terminal。
- 不验证 LSP 语义能力或多项目切换。

### 审阅意见

- [ ] 路线符合预期
- [ ] Edit 应自动保存到磁盘
- [ ] 允许只更新 IDE 工作区模型
- [ ] 需要调整：

---

## 场景 3：Terminal 测试闭环

场景名：`terminal-test-loop`

### 用户目标

Agent 写完代码后启动项目 Terminal，运行程序或测试，检查真实退出码和输出，再安全关闭 Runtime。

### 路线

```text
创建项目与代码
→ terminal_start
→ 刷新动态工具
→ shell_open
→ shell_exec 执行 python app.py
→ 读取 Shell Overview
→ terminal_close
→ 确认工具与 Resource 恢复
```

### 检查点与预期

1. 创建可执行文件
   - 写入 `print("UAT_TERMINAL_OK")`。
   - `Write.success == true`，文件真实落盘。

2. 启动 Terminal Runtime
   - `terminal_start` 无 MCP error。
   - 返回 `terminal.state == "open"`。
   - Inspector 收到 Tools 和 Resources 目录变化通知。
   - 刷新后 `terminal_start` 消失。
   - `terminal_close`、`shell_open`、`shell_exec`、`shell_read`、`shell_write`、`shell_signal`、`shell_list`、`shell_close` 出现。

3. 打开 Shell 并执行程序
   - `shell_open` 返回 shell ID。
   - cwd 与规范化后的项目根目录相同。
   - `shell_exec` 执行 `python app.py`。
   - 预期执行状态为 `exited`、退出码为 `0`、输出包含 `UAT_TERMINAL_OK`。
   - 命令完成后 Shell 仍可继续使用。

4. 读取 Shell Overview
   - Resources 出现 `window://io.github.a2c-smcp.tfbash/shell-overview`。
   - 内容包含当前 shell ID、状态、项目 cwd、最近命令及 `UAT_TERMINAL_OK`。

5. 关闭 Runtime
   - `terminal_close` 成功。
   - 所有 `shell_*` 工具和 Shell Overview 消失。
   - `terminal_start` 恢复。
   - IDE Window 仍然存在，项目没有被卸载。

### 证明范围

- Terminal Runtime 按当前项目动态启停。
- Shell cwd 正确绑定项目根目录。
- 可以真实执行代码并取得退出码和输出。
- Shell 状态可通过 Resource 观察。
- 关闭 Runtime 后动态能力被正确回收。

### 非目标

- 不验证后台长任务、超时、强制回收或 signal。
- 不验证多项目 Terminal 隔离。
- 不验证 Resource 订阅通知。

### 审阅意见

- [ ] 路线符合预期
- [ ] 需要增加测试框架命令，例如 `pytest`
- [ ] 需要增加失败命令和非零退出码
- [ ] 需要调整：

---

## 场景 4：多项目切换与隔离

场景名：`multi-project-switch`

### 用户目标

用户同时注册两个项目。Agent 在 A、B 之间切换时，文件、IDE Window、Terminal Runtime 和 Shell 不能串线。

### 夹具路线

Inspector 连接后的业务目录不能由本地 Shell 预造，因此先创建临时 `uat-bootstrap` 项目，通过其 Terminal 创建两个同级目录：

```text
workspace/
├── project-a/
└── project-b/
```

A、B 使用同级、互不嵌套的项目根，确保文件隔离断言有效。

### 完整路线

```text
创建 bootstrap 项目
→ bootstrap Terminal 创建 project-a 和 project-b
→ 关闭 bootstrap Terminal
→ 注册 A、B
→ 切换到 A
→ 创建 A 文件并启动 A Terminal
→ 切换到 B，验证看不到 A 文件和 Shell
→ 创建 B 文件并启动 B Terminal
→ 切回 A，验证 A 状态恢复且看不到 B
→ 再切回 B，验证 B 状态恢复
→ 分别关闭 A、B Runtime
```

### 检查点与预期

1. 建立独立根目录
   - bootstrap Shell 执行 `mkdir -p project-a project-b`，退出码为 `0`。
   - A、B 注册根目录分别等于两个规范化后的同级目录。
   - 两个项目根互不包含。

2. 建立 A 状态并切换到 B
   - A 创建 `project-a.txt`，内容为 `PROJECT_A`。
   - A 启动 Terminal 并打开 Shell。
   - 切换到 B 后，`current_project == "uat-project-b"`。
   - B 只显示 `terminal_start`，不继承 A 的 Shell 工具状态。
   - B 的 Glob 看不到 `project-a.txt`。
   - B 的 IDE Window 不包含 `PROJECT_A` 或 `project-a.txt`。

3. 建立 B 状态
   - B 创建 `project-b.txt`，内容为 `PROJECT_B`。
   - B 启动自己的 Terminal 和 Shell。
   - B Shell cwd 等于 B 根目录。

4. 切回 A
   - A 原 Shell 仍存在，cwd 仍属于 A。
   - A 的 Glob 看不到 `project-b.txt`。
   - A 的 IDE Window 包含 `project-a.txt`，不包含 `PROJECT_B` 或 `project-b.txt`。

5. 再切回 B 并收尾
   - `shell_list` 只返回 B 的 Shell。
   - B 的 IDE Window 包含 B 文件，不包含 A 标记。
   - 关闭 B Terminal 只影响 B。
   - 切回 A 后 A Terminal 仍存在，关闭 A 后才恢复 `terminal_start`。

### 证明范围

- 当前项目选择隔离。
- 文件搜索范围隔离。
- IDE Window Resource 隔离。
- Terminal Runtime 与 Shell cwd 隔离。
- 项目切换后原项目 Runtime 可以恢复使用。

### 非目标

- 不验证高并发切换。
- 不验证删除正在运行的项目。
- 不验证多个 MCP Server 进程共享 Runtime。
- bootstrap 仅用于通过 Inspector 创建夹具，不参与 A/B 隔离结论。

### 审阅意见

- [ ] 路线符合预期
- [ ] 需要增加运行中命令时切换项目
- [ ] 需要增加删除当前项目
- [ ] 需要增加同项目多个 Shell
- [ ] 需要调整：

---

## 场景 5：重启后的项目持久化

场景名：`restart-persistence`

### 用户目标

用户关闭并重新启动 Inspector/MCP Server 后，不需要重新注册项目；当前项目选择和项目文件能够恢复。

### 路线

```text
第一会话创建项目和标记文件
→ project_list 确认当前项目
→ UI 断开并完整停止 Inspector/MCP
→ 保留 manifest、projects.json 和 workspace
→ 使用同一 manifest 启动第二会话
→ 不重新创建项目，直接检查动态工具
→ project_list 检查恢复状态
→ Read 文件并读取 IDE Window
```

### 检查点与预期

1. 第一会话写入状态
   - 创建 `uat-restart`。
   - 写入 `restart-marker.txt`，内容为 `PERSISTED`。
   - `project_list.current_project == "uat-restart"`。

2. 完整停止第一会话
   - 在 UI 中断开 MCP。
   - 精确中断本次 Inspector 长驻进程并确认退出。
   - 不删除或修改 `run-manifest.json`、`projects.json` 和 `workspace_dir`。

3. 第二会话恢复
   - 使用同一个 manifest 重启 Inspector。
   - 不执行 `project_create`。
   - 连接后立即出现项目管理工具、文件工具、`Lsp`、`terminal_start` 和 `project_unload`。

4. 验证恢复内容
   - `project_list` 包含 `uat-restart`。
   - 当前项目仍为 `uat-restart`。
   - 根目录与原 workspace 指向同一位置。
   - `Read` 可以读取 `PERSISTED`。
   - IDE Window 属于恢复后的项目。

### 证明范围

- 项目注册表跨进程持久化。
- 当前项目选择跨进程持久化。
- 项目文件和动态工具目录可恢复。

### 重要预期边界

当前不要求 Terminal Runtime 或 Shell 跨进程恢复。重启后预期出现 `terminal_start`，不是恢复旧 Shell。

### 非目标

- 不验证进程崩溃时的注册表原子性。
- 不验证多个 Server 同时修改注册表。
- 不验证旧版注册表迁移。
- 不恢复 Terminal/Shell 进程。

### 审阅意见

- [ ] 只恢复项目注册、选择和文件符合预期
- [ ] Terminal/Shell 也应恢复
- [ ] 需要增加异常崩溃恢复
- [ ] 需要调整：

---

## 场景 6：Terminal Resource 订阅更新

场景名：`terminal-resource-updates`

### 用户目标

客户端订阅 Shell Overview 后，Shell 创建或输出变化应由 Server 主动通知，而不是要求客户端不断轮询。

### 路线

```text
创建项目并启动 Terminal
→ 刷新 Tools 和 Resources
→ 打开 Shell Overview
→ Subscribe
→ shell_open
→ shell_exec 输出标记
→ 等待 resources/updated 通知
→ 刷新或读取 Resource 内容
→ Unsubscribe
→ 关闭 Terminal
```

### 检查点与预期

1. 暴露 Shell Resource
   - Shell 工具出现。
   - `window://io.github.a2c-smcp.tfbash/shell-overview` 出现。

2. 订阅
   - 在 Resource 面板点击 Subscribe。
   - UI 显示已订阅状态。
   - Protocol 区订阅请求成功，无 MCP error。

3. 触发更新
   - `shell_open` 创建 Shell。
   - `shell_exec` 执行 `echo UAT_RESOURCE_UPDATED`。
   - 不使用定时刷新或循环探测。
   - Inspector 主动收到 `notifications/resources/updated`。
   - 通知 URI 与 Shell Overview URI 相同。

4. 读取更新内容
   - 收到通知后，通过 Resource 面板刷新或读取。
   - 内容包含当前 shell、项目 cwd 和 `UAT_RESOURCE_UPDATED`。

5. 取消订阅与收尾
   - Unsubscribe 请求成功。
   - 关闭 Terminal 后 Shell Overview 从目录消失。

### 证明范围

- Resource 标准订阅生命周期可用。
- Shell 状态和输出变化会主动发出更新事件。
- 更新事件与 Resource URI 一致。
- 客户端不需要通过轮询发现变化。

### 非目标

- 不测试高频通知合并。
- 不测试断线后的事件补发。
- 不测试多个订阅者、事件顺序或丢包恢复。

### 审阅意见

- [ ] 路线符合预期
- [ ] 需要增加断线重连
- [ ] 需要增加多订阅者
- [ ] 需要调整：

---

## 场景 7：Python LSP 工作流

场景名：`lsp-python-workflow`

### 用户目标

用户注册 Python 项目时显式启用 Python LSP，随后可以查询语言服务器状态、主动重载，并确认项目 LSP 配置没有丢失。

### 前置依赖

必须存在真实 `pyright-langserver`。依赖缺失时结果为 `BLOCKED`，不能用假服务代替。

### 路线

```text
注册显式 Python 项目
→ 创建 main.py
→ Lsp status
→ Lsp reload
→ 再次 status
→ project_list 检查 LSP 配置
```

### 检查点与预期

1. 注册显式 Python 项目
   - `lsp.mode == "explicit"`。
   - `lsp.language_id == "python"`。
   - 项目创建成功，返回配置保持不变。
   - 刷新后 `Lsp` 工具可见。

2. 创建 Python 文件
   - 写入：

     ```python
     def answer() -> int:
         return 42
     ```

   - Write 成功，Python 文件进入工作区。

3. 查询状态
   - `Lsp(action="status")` 无 MCP error。
   - `language_id == "python"`。
   - `state` 为 `ready` 或 `running`。
   - 不存在 unavailable 原因。

4. 显式重载
   - 调用 `Lsp(action="reload")`，随后再次 status。
   - 重载后语言仍为 Python。
   - 状态仍为 `ready` 或 `running`，不进入 `unavailable`。
   - 当前项目不发生变化。

5. 验证项目配置
   - `project_list` 中的 LSP 配置仍为显式 Python。
   - 运行期间没有被降级或丢失。

### 证明范围

- 项目注册可以携带 LSP 配置。
- Python profile 可以选择。
- LSP 生命周期状态可查询。
- LSP 可以显式重载。
- 项目配置在运行过程中保持稳定。

### 重要预期边界

当前只验证语言服务器生命周期和配置，不验证诊断、补全、Hover、定义跳转、引用查找或 Rename 的语义正确性。

如果核心用户路线是“AI 依靠 LSP 理解并修改代码”，建议增加独立的 `lsp-python-semantic-loop`。

### 非目标

- 不验证具体 LSP 语义结果。
- 不验证 LSP 崩溃自恢复。
- 不验证其他语言或自定义 Server 命令。

### 审阅意见

- [ ] 生命周期与配置检查已经足够
- [ ] 必须增加诊断
- [ ] 必须增加定义/引用/补全等语义闭环
- [ ] 需要调整：

---

## 场景 8：项目与工具安全边界

场景名：`project-guardrails`

### 用户目标

Agent 输入不规范路径、重复项目、错误工具参数或越界 Terminal cwd 时，系统应明确拒绝非法操作，并保持已有项目可继续使用。

### 路线

```text
用已有相对路径创建项目
→ 检查规范化结果
→ 尝试不存在目录
→ 尝试重复名称和重复根目录
→ 调用缺少必填参数的 Glob
→ 调用 old_string 等于 new_string 的 Edit
→ 尝试越界 terminal_start
→ 验证状态未污染
→ 正常启动和关闭 Terminal，证明可恢复
```

### 检查点与预期

1. 项目路径契约
   - 从 Inspector Server 的仓库根目录计算指向 `workspace_dir` 的已有相对路径。
   - 使用该路径创建 `uat-guardrails` 应成功。
   - 返回根目录应被规范化为与 `workspace_dir` 相同的绝对位置。
   - 再提交不存在的 `<run_dir>/missing-root` 应失败。
   - 失败后仍只有 `uat-guardrails`，当前项目不变。

2. 重复注册
   - 使用不同大小写的同名项目和不同已有根目录，应因名称重复失败。
   - 使用不同项目名和同一个真实根目录，应因根目录重复失败。
   - 两次失败都不能改变当前项目或项目数量。

3. 无效工具参数
   - `Glob` 省略必填 `pattern`，应返回参数错误。
   - `Edit.old_string == Edit.new_string`，应返回操作错误。
   - 不产生文件变化，不触发错误的目录变化通知，后续工具仍可使用。

4. Terminal cwd 越界
   - 项目根为 `workspace_dir`，使用外层 `run_dir` 调用 `terminal_start`。
   - 调用应失败并说明 cwd 必须位于项目根内。
   - `terminal_start` 仍存在，不出现任何 `shell_*` 工具或 Shell Overview。

5. 失败后的恢复能力
   - 使用默认 cwd 再次调用 `terminal_start` 应成功。
   - Shell cwd 等于项目根目录。
   - Terminal 可以正常关闭。
   - 最终仍只有原项目，当前项目没有被前面的错误操作污染。

### 证明范围

- 已有相对项目路径会被规范化。
- 不存在目录不能注册。
- 项目名称大小写不敏感且唯一。
- 同一个真实根目录不能重复注册。
- 工具参数错误不会污染状态。
- Terminal cwd 不允许逃离当前项目根。
- 错误操作后系统仍可恢复使用。

### 重要预期边界

当前产品允许已有相对项目路径，服务端会将其规范化，而不是直接拒绝。

`Read` 当前也不是工作区沙箱：只要提供有效绝对路径，它可以读取项目根外的文件。Guardrails 只验证 Terminal cwd 边界，不把 Read 越界视为失败。

如果产品预期是“所有文件工具只能访问当前项目根”，则需要单独新增权限需求和相应 UAT。

### 非目标

- 不验证操作系统权限模型。
- 不验证恶意 Shell 命令过滤。
- 不验证并发注册竞态。
- 不把 Read 当作项目沙箱。

### 审阅意见

- [ ] 允许相对项目路径并规范化
- [ ] 应禁止相对项目路径
- [ ] Read 可以读取项目根外绝对路径
- [ ] 所有文件工具都应限制在项目根内
- [ ] 需要调整：

---

## 能力覆盖矩阵

| 能力域 | 主要场景 | 补充场景 |
|---|---|---|
| Inspector 连接与基础兼容性 | `smoke-dynamic-catalog` | 全部场景 |
| 项目注册与当前项目 | `smoke-dynamic-catalog` | `restart-persistence`、`project-guardrails` |
| 动态 Tools 目录 | `smoke-dynamic-catalog` | `terminal-test-loop`、`multi-project-switch` |
| 动态 Resources 目录 | `smoke-dynamic-catalog` | `terminal-test-loop`、`terminal-resource-updates` |
| 文件创建、发现、搜索和读取 | `project-code-edit-loop` | `multi-project-switch` |
| 精确代码编辑 | `project-code-edit-loop` | 无 |
| 程序与测试命令执行 | `terminal-test-loop` | 无 |
| Terminal 生命周期 | `terminal-test-loop` | `multi-project-switch`、`project-guardrails` |
| Shell Resource 内容 | `terminal-test-loop` | `terminal-resource-updates` |
| Resource 主动通知 | `terminal-resource-updates` | 无 |
| 多项目隔离 | `multi-project-switch` | 无 |
| 跨进程持久化 | `restart-persistence` | 无 |
| Python LSP 生命周期 | `lsp-python-workflow` | 无 |
| 路径、重复注册和错误恢复 | `project-guardrails` | 无 |

## 需要产品确认的关键决策

### 1. Edit 的保存语义

- [ ] Edit 只更新 IDE 工作区模型即可。
- [ ] Edit 必须自动保存到磁盘，使 Git、Grep 和测试命令立即看到新内容。
- [ ] 需要独立 Save 工具，由 Agent 显式保存。

### 2. LSP 验收深度

- [ ] 状态查询和重载已经足够。
- [ ] 需要增加诊断闭环。
- [ ] 需要增加定义跳转、引用、Hover、补全或 Rename。

### 3. 重启恢复边界

- [ ] 只恢复项目注册、当前选择和文件。
- [ ] 还需要恢复 Terminal 配置，但不恢复进程。
- [ ] 需要恢复运行中的 Terminal/Shell。

### 4. 文件访问边界

- [ ] Read 保持可读取任意有效绝对路径。
- [ ] Read 只能读取当前项目根目录。
- [ ] Read 可以越界，但 Write/Edit 必须限制在项目根目录。

### 5. 多项目高级场景

- [ ] 当前切换与隔离路线已经足够。
- [ ] 增加运行中命令时切换项目。
- [ ] 增加删除当前项目或繁忙项目。
- [ ] 增加同一项目多 Shell。

### 6. Terminal 测试深度

- [ ] 执行一个成功的 Python 程序已经足够。
- [ ] 需要执行真实项目测试命令，例如 `pytest`。
- [ ] 需要增加失败命令、非零退出码和错误输出。

## 总体审阅结论

- [ ] 当前 8 个场景符合项目主要工作路线，可以按此执行完整 UAT。
- [ ] 基础路线符合，但需要按上面的勾选项扩展。
- [ ] 场景划分需要重新设计。

补充意见：
