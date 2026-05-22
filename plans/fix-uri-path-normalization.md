# Fix Plan: URI / 文件系统路径归一化

## 背景

`plans/bug-chinese-uri-encoding.md` 描述的问题本质不是单个 `uri[7:]` 的局部 bug，而是项目里缺少统一的 `file://` URI 与本地文件系统路径之间的边界转换。

当前改动已经修复了部分 `uri[7:]` 截断导致的中文路径 percent-encoding 问题，但仍存在两个系统性风险：

1. MCP 工具层同时使用原始 `file_path`、`file_uri`、workspace 内部 URI，存在同一条路径在不同表示之间反复切换的问题。
2. 新增的 `file_uri_to_path()` 对普通文件路径也执行 `unquote`，会把真实文件名中的字面量 `%20`、`%E6...` 错误解码。

## 目标

建立一个明确、可复用、可测试的路径归一化边界：

- 工具输入可以是普通绝对路径或 `file://` URI。
- 文件系统操作只使用解码后的本地路径。
- workspace / LSP / `TextModel` 只使用规范化后的 `file://` URI。
- URL decoding 只发生在 URI 到文件路径的转换中，不对普通文件路径做隐式解码。
- Read / Write / Edit / NotebookEdit 对中文、空格、percent 字面量路径行为一致。

## 建议抽象

新增或移动到一个更中性的工具模块，例如：

`ide4ai/environment/workspace/uri_utils.py`

建议提供三个函数：

```python
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


def file_uri_to_path(uri: str) -> str:
    """Convert a file:// URI to a local filesystem path."""
    ...


def path_to_file_uri(path: str | Path) -> str:
    """Convert a local filesystem path to a file:// URI."""
    ...


def normalize_tool_file_path(value: str | Path) -> tuple[str, str]:
    """Return (file_uri, fs_path) for MCP tool file_path input."""
    ...
```

语义要求：

- `file_uri_to_path()` 只接受 `file://` URI；非 `file://` 输入应抛 `ValueError`，避免普通路径被误解码。
- `path_to_file_uri()` 只负责把本地路径编码成 URI，路径中的中文、空格、`%` 字面量都应正确 percent-encode。
- `normalize_tool_file_path()` 是 MCP 工具层入口：如果输入是 `file://`，先解码为 `fs_path`；如果输入是普通路径，保留原始路径语义，再生成规范 URI。

## 实现步骤

1. 新增 `uri_utils.py` 和单元测试。
2. 将当前 `BaseWorkspace.file_uri_to_path` helper 迁移到 `uri_utils.py`，并修正为“只接受 URI”。
3. 修改 workspace 内部所有 URI 到路径转换点：
   - `BaseWorkspace.expand_folder`
   - `BaseWorkspace.collapse_folder`
   - `PyWorkspace.create_file`
   - `PyWorkspace.find_in_path`
   - `PyWorkspace.render` 中 active model 路径提取
   - `TextModel.__init__`
   - `TextModel.save`
4. 修改 MCP 工具层：
   - `ReadTool`: 使用 `normalize_tool_file_path()` 生成 `file_uri`，调用 workspace 时只传 `file_uri`。
   - `WriteTool`: 使用 `fs_path` 做 `os.path.exists()`，使用 `file_uri` 调 workspace；修复 `file://` 已存在文件被误判为不存在的问题。
   - `EditTool`: 使用 `normalize_tool_file_path()`；替换完成后显式 `workspace.save_file(uri=file_uri)`，确保磁盘落盘。
   - `NotebookEditTool`: 对 `file://` 输入使用 `normalize_tool_file_path()`，对普通路径不做隐式 `unquote`。
5. 清理重复的 URI 手写逻辑：
   - 禁止新增 `uri[7:]`。
   - 避免 `.replace("file://", "")`。
   - 避免直接对普通路径 `unquote()`。
6. 保留 `uv.lock` 版本变更与本问题解耦；如果不是本修复需要，应单独处理或还原。

## 必须覆盖的回归用例

### URI 工具函数

| 场景 | 输入 | 期望 |
|------|------|------|
| 中文 URI | `file:///tmp/淘宝报告.md` | `/tmp/淘宝报告.md` |
| 编码中文 URI | `file:///tmp/%E6%B7%98%E5%AE%9D.md` | `/tmp/淘宝.md` |
| 空格 URI | `file:///tmp/my%20file.py` | `/tmp/my file.py` |
| percent 字面量路径 | `/tmp/a%20b.py` | 普通路径保持 `%20` 字面量 |
| percent 字面量转 URI | `/tmp/a%20b.py` | URI 中 `%` 应编码为 `%25` |
| 非 file URI | `http://example.com/a.py` | 抛 `ValueError` |

### MCP 端到端

使用 `PythonIDE` 和实际工具执行：

1. `WriteTool` 写入普通中文路径：`/tmp/.../巡店报告.md`，磁盘内容正确。
2. `ReadTool` 读取同一中文路径，内容正确。
3. `EditTool` 替换中文路径文件内容，返回成功且磁盘内容已变更。
4. `WriteTool` 覆盖已存在中文路径文件，输入为普通路径，内容正确。
5. `WriteTool` 覆盖已存在中文路径文件，输入为 `file://` URI，内容正确。
6. 路径名包含字面量 `%20` 或 `%E6` 时，不被错误解码到另一个文件名。
7. `NotebookEditTool` 对中文路径 notebook 的读写保持正常。

## 当前改动的已知问题

### Edit 未落盘

`EditTool` 调用 `workspace.replace_in_file()` 后直接返回成功，没有调用 `save_file()`。手工复现中，中文路径文件 Edit 返回 `success=True`，但磁盘内容仍然是旧内容。

### Write 的 `file://` 已存在判断错误

`WriteTool` 当前使用原始 `file_path` 做 `os.path.exists(file_path)`。当输入是 `file:///.../淘宝报告.md` 时，存在性检查会失败，之后进入创建文件分支，并在 `create_file()` 内部因真实文件已存在而失败。

### 普通路径被 `unquote`

当前 helper 对普通路径也执行 `unquote`。如果文件真实名称是 `a%20b.py`，会被误解码为 `a b.py`，属于潜在数据错读/错写风险。

## 验收标准

- `rg "uri\\[7:\\]|replace\\(\"file://\"|unquote\\(" ide4ai` 不再出现未审计的手写 URI/path 转换。
- 新增 URI 工具函数单元测试全部通过。
- Read / Write / Edit 中文路径端到端测试全部通过。
- `file://` 输入和普通路径输入在 MCP 工具层行为一致。
- percent 字面量路径不会被错误解码。
- 现有相关测试通过：

```bash
poetry run pytest tests/environment/workspace/test_uri_utils.py
poetry run pytest tests/environment/workspace/test_model.py tests/environment/workspace/test_text_model_search.py
poetry run pytest tests/a2c_smcp/tools/test_mcp_read_tool.py tests/integration/python_ide/a2c_smcp/test_write_tool.py tests/a2c_smcp/tools/test_mcp_edit_tool.py
```
