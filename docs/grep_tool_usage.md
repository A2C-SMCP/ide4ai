# Grep 工具使用说明 | Grep Tool Usage Guide

## 概述 | Overview

Grep 工具是一个基于 ripgrep 的强大搜索工具，用于在 IDE 环境中搜索文件内容。

The Grep tool is a powerful search tool based on ripgrep for searching file contents in the IDE environment.

## 功能特性 | Features

- ✅ 支持正则表达式搜索 | Supports regex search
- ✅ 支持 glob 模式过滤文件 | Supports glob pattern file filtering
- ✅ 支持文件类型过滤 | Supports file type filtering
- ✅ 三种输出模式 | Three output modes:
  - `content`: 显示匹配的行及上下文 | Show matched lines with context
  - `files_with_matches`: 仅显示包含匹配的文件路径（默认）| Show only file paths with matches (default)
  - `count`: 显示每个文件的匹配计数 | Show match count per file
- ✅ 支持多行匹配 | Supports multiline matching
- ✅ 大小写敏感/不敏感搜索 | Case-sensitive/insensitive search
- ✅ 上下文行显示 | Context line display

## 实现位置 | Implementation Location

- **核心方法**: `ide4ai/python_ide/workspace.py::PyWorkspace.grep_files()`
- **MCP 工具**: `ide4ai/python_ide/mcp/tools/grep.py::GrepTool`
- **Schema 定义**: `ide4ai/python_ide/mcp/schemas/tools.py::GrepInput/GrepOutput`

## 使用示例 | Usage Examples

### 1. 基本搜索 | Basic Search

搜索所有包含 "TODO" 的文件：

```python
from ide4ai.python_ide.workspace import PyWorkspace

workspace = PyWorkspace(root_dir="/path/to/project", project_name="my-project")
result = workspace.grep_files(pattern="TODO")
print(result["output"])
```

### 2. 搜索特定文件类型 | Search Specific File Types

搜索 Python 文件中的类定义：

```python
result = workspace.grep_files(
    pattern=r"class\s+\w+",
    file_type="py",
    output_mode="content",
    line_number=True
)
```

### 3. 使用 Glob 模式 | Using Glob Patterns

搜索测试文件中的断言：

```python
result = workspace.grep_files(
    pattern="assert",
    glob="**/test_*.py",
    output_mode="content"
)
```

### 4. 带上下文的搜索 | Search with Context

显示匹配行前后各 3 行：

```python
result = workspace.grep_files(
    pattern="def main",
    output_mode="content",
    context=3,
    line_number=True
)
```

### 5. 多行搜索 | Multiline Search

搜索跨行的模式：

```python
result = workspace.grep_files(
    pattern=r"def.*\n.*return",
    multiline=True,
    output_mode="content"
)
```

### 6. 大小写不敏感搜索 | Case-Insensitive Search

```python
result = workspace.grep_files(
    pattern="error",
    case_insensitive=True,
    output_mode="files_with_matches"
)
```

### 7. 限制输出行数 | Limit Output Lines

```python
result = workspace.grep_files(
    pattern="import",
    output_mode="content",
    head_limit=50  # 只显示前 50 行
)
```

## MCP 工具调用 | MCP Tool Invocation

通过 MCP 协议调用 Grep 工具：

```json
{
  "name": "Grep",
  "arguments": {
    "pattern": "TODO",
    "path": "src",
    "output_mode": "files_with_matches"
  }
}
```

## 输出格式 | Output Format

### 成功响应 | Success Response

```json
{
  "success": true,
  "output": "src/main.py\nsrc/utils.py\n",
  "matched": true,
  "metadata": {
    "pattern": "TODO",
    "path": "/path/to/project/src",
    "output_mode": "files_with_matches",
    "exit_code": 0
  }
}
```

### 错误响应 | Error Response

```json
{
  "success": false,
  "output": "",
  "matched": false,
  "error": "搜索路径不存在 / Search path does not exist: /invalid/path"
}
```

## 参数说明 | Parameter Description

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `pattern` | string | ✅ | - | 正则表达式搜索模式 |
| `path` | string | ❌ | workspace root | 搜索路径 |
| `glob` | string | ❌ | null | Glob 文件过滤模式 |
| `output_mode` | string | ❌ | "files_with_matches" | 输出模式 |
| `-B` (context_before) | int | ❌ | null | 显示匹配前的行数 |
| `-A` (context_after) | int | ❌ | null | 显示匹配后的行数 |
| `-C` (context) | int | ❌ | null | 显示匹配前后的行数 |
| `-n` (line_number) | bool | ❌ | null | 显示行号 |
| `-i` (case_insensitive) | bool | ❌ | null | 忽略大小写 |
| `type` (file_type) | string | ❌ | null | 文件类型（如 "py", "js"） |
| `head_limit` | int | ❌ | null | 限制输出行数 |
| `multiline` | bool | ❌ | false | 启用多行模式 |

## 注意事项 | Notes

1. **ripgrep 依赖**: 需要系统安装 ripgrep。如果未安装，会抛出错误提示。
   
   安装方法：
   - macOS: `brew install ripgrep`
   - Ubuntu: `apt-get install ripgrep`
   - 其他: https://github.com/BurntSushi/ripgrep#installation

2. **路径安全**: 搜索路径必须在工作区根目录内，否则会抛出 ValueError。

3. **超时设置**: 默认超时 30 秒。对于大型代码库，可能需要调整。

4. **正则表达式语法**: 使用 ripgrep 的正则语法（类似 Rust regex），与标准 grep 略有不同。

5. **性能**: ripgrep 针对速度优化，比传统 grep 快得多，适合大型代码库。

## 测试 | Testing

运行测试验证功能：

```bash
# 验证导入
uv run python -c "from ide4ai.python_ide.mcp.tools import GrepTool; print('OK')"

# 验证 Schema
uv run python -c "from ide4ai.python_ide.mcp.schemas.tools import GrepInput; print(GrepInput.model_json_schema())"
```

## 相关工具 | Related Tools

- **Glob Tool**: 用于文件名模式匹配
- **Read Tool**: 用于读取文件内容
- **Bash Tool**: 用于执行命令行操作

## 参考资料 | References

- [ripgrep 官方文档](https://github.com/BurntSushi/ripgrep)
- [MCP 协议规范](https://modelcontextprotocol.io/)
