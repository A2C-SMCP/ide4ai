# Inspector 与 Playwright 契约

## 进程边界

- `prepare_run.py` 只创建隔离文件并给出启动清单，不启动网络服务；`run_inspector.py` 按清单原样 exec Inspector。
- Inspector Web 是唯一被长驻启动的顶层进程；它在点击 Connect 后按配置派生 `uv run ide4ai-mcp` stdio 子进程。
- 使用启动工具返回的进程/session 标识停止 Inspector，保证只终止本次运行。
- Inspector 只绑定 `127.0.0.1`，自动打开浏览器关闭，API token 每次随机生成。

## Playwright 操作规则

- 每次重要操作前获取最新页面快照。
- 优先使用 role + accessible name，其次使用稳定可见文本。
- 允许根据 Inspector 新版本的等价文案适配定位器，但不允许跳过用户可见操作。
- 不使用页面内 JavaScript 直接调用 Inspector API、修改 React 状态或伪造通知。
- 不通过 `curl`、MCP SDK 或 Inspector CLI 调用 `tools/list`、`tools/call`、`resources/list`、`resources/read`。
- HTTP 探针只可用于确认 Inspector Web 已开始监听，不能作为产品断言。

## 证据命名

截图放入运行清单的 `artifacts_dir`。默认 smoke 使用：

1. `01-connected.png`
2. `02-initial-tools.png`
3. `03-refreshed-tools.png`
4. `04-window-resource.png`
5. 失败时追加 `failure-<step>.png`

其他场景在自身契约中定义按执行顺序编号的截图名，失败时同样追加 `failure-<step>.png`。

报告可追加 Inspector stdout/stderr 摘要，但不得把随机 API token 写入 Issue、PR 或聊天报告。

## 兼容性原则

Inspector UI 的布局和文案可能变化，场景断言针对 MCP 语义，不针对像素位置。以下语义入口必须仍能通过 UI 找到：Server 选择、Connect/Disconnect、Tools、Resources、刷新提示或刷新动作、工具参数表单、调用结果、Resource 内容。任一入口消失均属于框架兼容性失败，需要保留截图并更新适配层。

macOS 可能把 `/var/...` 展示为 `/private/var/...`。路径断言应比较规范化后的同一文件系统位置，不做原始字符串相等判断。

Inspector 可能并行调用 `resources/list` 与 `resources/templates/list`，并把任一错误汇总为 Resources 面板告警。报告必须依据 Protocol 监控区分别判断具体方法；不应把未实现的 Templates 能力错误误判为 `resources/list` 或 `resources/read` 失败。

需要等待动态变化时，以 Inspector 已呈现的通知、状态或 Playwright 的可见条件等待为准，不实现定时刷新或 sleep-loop 轮询。

Inspector 的普通字符串输入框按单行处理。场景参数包含换行时，必须先点击对应的 `Enlarge <字段名>`，在展开的多行编辑器中填写并确认；不得把换行压平后的内容当作有效测试夹具。
