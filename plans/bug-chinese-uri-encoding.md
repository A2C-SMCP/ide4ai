# Bug: py-ide4ai-mcp 中文文件路径操作失败

## 复现场景

通过 MCP stdio 协议调用 `py-ide4ai-mcp`，对中文路径文件执行 Read / Write / Edit 操作。

```
uv --directory /path/to/ide4ai run py-ide4ai-mcp --root-dir /tmp/test --project-name demo
```

调用 Write 工具：

```json
{"file_path": "/tmp/test/淘宝报告.md", "content": "# 巡店报告\n"}
```

调用 Read 工具：

```json
{"file_path": "/tmp/test/巡店报告.md"}
```

## 实际结果

Write 返回 success，但文件内容为空。Read 返回错误：

```
Error reading file /tmp/test/%E5%B7%A1%E5%BA%97%E6%8A%A5%E5%91%8A.md:
[Errno 2] No such file or directory:
'/tmp/test/%E5%B7%A1%E5%BA%97%E6%8A%A5%E5%91%8A.md'
```

Edit 返回 success，但文件内容未变更。

## 期望结果

Write 创建文件并写入内容，Read 返回文件内容，Edit 完成字符串替换。

## 根因

MCP 工具内部将 `file_path` 转为 `file://` URI 后，经过 Pydantic `AnyUrl` 构造，非 ASCII 字符被 percent-encode。后续代码用 `uri[7:]` 截取前缀，得到的是编码后的字符串（`%E6%B7%98%E5%AE%9D...`），而非原始路径。

```
file_path = "/tmp/淘宝报告.md"
uri       = "file:///tmp/淘宝报告.md"
AnyUrl →  = "file:///tmp/%E6%B7%98%E5%AE%9D%E6%8A%A5%E5%91%8A.md"
uri[7:]   = "/tmp/%E6%B7%98%E5%AE%9D%E6%8A%A5%E5%91%8A.md"  ← 错误
```

## 受影响的工具和操作

| 工具 | 操作 | 结果 |
|------|------|------|
| Read | 读取中文路径文件 | FileNotFoundError |
| Write | 创建中文路径新文件 | 文件创建成功，内容为空 |
| Write | 覆盖已有中文路径文件 | 内部 Read 先失败，后续异常 |
| Edit | 编辑中文路径文件 | Read 失败导致替换未执行 |

英文路径文件不受影响。

## 受影响的代码

| 文件 | 行号 | 方法 |
|------|------|------|
| `ide4ai/python_ide/workspace.py` | 723 | `create_file` |
| `ide4ai/python_ide/workspace.py` | 860 | 路径处理 |
| `ide4ai/environment/workspace/base.py` | 1000 | `expand_folder` |
| `ide4ai/environment/workspace/base.py` | 1098 | `collapse_folder` |

以上位置均使用 `uri[7:]` 截取路径。

`TextModel.__init__`（model.py:149）和 `TextModel.save`（model.py:279）使用 `uri.path` 属性，能正确解码，不受影响。

## 建议修复

将 `uri[7:]` 替换为 `AnyUrl(uri).path`，或用 `urllib.parse.unquote(uri[7:])` 解码。项目中已有正确用法可参考（model.py 的 `uri.path`）。
