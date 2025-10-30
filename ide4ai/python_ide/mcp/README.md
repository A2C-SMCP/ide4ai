# Python IDE MCP Server

将 PythonIDE 的能力封装为 MCP (Model Context Protocol) Server，为 AI 助手提供强大的 IDE 能力。

Wraps PythonIDE capabilities as MCP (Model Context Protocol) Server, providing powerful IDE capabilities for AI assistants.

## 架构设计 | Architecture

```
ide4ai/python_ide/mcp/
├── __init__.py              # 包入口 | Package entry
├── server.py                # MCP Server 主实现 | MCP Server main implementation
├── config.py                # 配置管理 | Configuration management
├── tools/                   # 工具实现 | Tools implementation
│   ├── __init__.py
│   ├── base.py             # 工具基类 | Tool base class
│   ├── bash.py             # Bash 工具 | Bash tool
│   ├── glob.py             # Glob 工具 (待实现) | Glob tool (TODO)
│   ├── grep.py             # Grep 工具 (待实现) | Grep tool (TODO)
│   ├── read.py             # Read 工具 (待实现) | Read tool (TODO)
│   ├── edit.py             # Edit 工具 (待实现) | Edit tool (TODO)
│   └── write.py            # Write 工具 (待实现) | Write tool (TODO)
├── resources/               # 资源实现 (待实现) | Resources implementation (TODO)
│   ├── __init__.py
│   └── base.py             # 资源基类 | Resource base class
└── schemas/                 # Schema 定义 | Schema definitions
    ├── __init__.py
    └── tools.py            # 工具 Schema | Tools schema
```

## 核心特性 | Core Features

### 1. 单例模式 | Singleton Pattern

使用 `PyIDESingleton` 确保在 MCP Server 生命周期内 IDE 实例的唯一性和状态一致性。

Uses `PyIDESingleton` to ensure IDE instance uniqueness and state consistency throughout MCP Server lifecycle.

### 2. 工具封装 | Tool Encapsulation

每个工具独立实现，继承自 `BaseTool`，提供：
- 标准化的输入验证 | Standardized input validation
- 统一的错误处理 | Unified error handling
- 清晰的接口定义 | Clear interface definition

Each tool is independently implemented, inheriting from `BaseTool`, providing:
- Standardized input validation
- Unified error handling
- Clear interface definition

### 3. Schema 定义 | Schema Definition

使用 Pydantic 模型定义所有工具的输入输出 Schema，确保类型安全。

Uses Pydantic models to define input/output schemas for all tools, ensuring type safety.

## 已实现工具 | Implemented Tools

### Bash

在 IDE 环境中执行 Bash 命令 | Execute Bash commands in IDE environment

**输入参数 | Input Parameters:**
- `command` (required): 要执行的命令 | Command to execute
- `timeout` (optional): 超时时间(毫秒) | Timeout in milliseconds
- `description` (optional): 命令描述 | Command description
- `run_in_background` (optional): 是否后台运行 | Run in background
- `dangerously_disable_sandbox` (optional): 禁用沙箱 | Disable sandbox

**输出 | Output:**
- `success`: 是否成功 | Success status
- `output`: 命令输出 | Command output
- `error`: 错误信息 | Error message
- `exit_code`: 退出码 | Exit code
- `metadata`: 元数据 | Metadata

## 待实现工具 | Tools TODO

- [ ] **Glob**: 文件模式匹配 | File pattern matching
- [ ] **Grep**: 代码搜索 | Code search
- [ ] **Read**: 读取文件 | Read file
- [ ] **Edit**: 编辑文件 | Edit file
- [ ] **Write**: 写入文件 | Write file

## 使用方法 | Usage

### 安装 | Installation

#### 使用 uvx (推荐) | Using uvx (Recommended)

```bash
# 直接运行，无需安装 | Run directly without installation
uvx ide4ai py-ide4ai-mcp

# 或者安装到全局 | Or install globally
uv tool install ide4ai
py-ide4ai-mcp
```

#### 使用 pip | Using pip

```bash
pip install ide4ai
py-ide4ai-mcp
```

### 作为独立服务运行 | Run as Standalone Service

#### 使用命令行工具 | Using CLI Tool

```bash
# 如果已安装 | If installed
py-ide4ai-mcp

# 使用 uv run (开发环境) | Using uv run (development)
uv run py-ide4ai-mcp

# 使用 Python 模块 | Using Python module
python -m ide4ai.python_ide.mcp.server
```

### 在代码中使用 | Use in Code

#### 方式 1: 使用默认配置（从环境变量和命令行参数加载）| Method 1: Use Default Configuration (Load from Environment Variables and Command-line Arguments)

```python
import asyncio
from ide4ai.python_ide.mcp import MCPServerConfig, PythonIDEMCPServer

async def main():
    # 自动从环境变量和命令行参数加载配置 | Automatically load configuration from environment variables and command-line arguments
    # 优先级：命令行参数 > 环境变量 > 默认值 | Priority: Command-line arguments > Environment variables > Default values
    config = MCPServerConfig()
    
    # 创建并运行 server | Create and run server
    server = PythonIDEMCPServer(config)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

#### 方式 2: 通过代码直接指定配置 | Method 2: Specify Configuration Directly in Code

```python
import asyncio
from ide4ai.python_ide.mcp import MCPServerConfig, PythonIDEMCPServer

async def main():
    # 直接在代码中指定配置参数 | Specify configuration parameters directly in code
    # 这会覆盖环境变量和命令行参数 | This will override environment variables and command-line arguments
    config = MCPServerConfig(
        cmd_white_list=["ls", "pwd", "echo", "cat"],
        root_dir="/path/to/project",
        project_name="my-project",
        cmd_time_out=30,
        render_with_symbols=True,
        max_active_models=5,
        enable_simple_view_mode=True,
    )
    
    # 创建并运行 server | Create and run server
    server = PythonIDEMCPServer(config)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### 配置 MCP Client | Configure MCP Client

在 MCP 客户端配置文件中添加：

Add to MCP client configuration file:

#### 使用 uvx (推荐) | Using uvx (Recommended)

##### 方式 1: 通过环境变量配置 | Method 1: Configure via Environment Variables

```json
{
  "mcpServers": {
    "python-ide": {
      "command": "uvx",
      "args": ["ide4ai", "py-ide4ai-mcp"],
      "env": {
        "PROJECT_ROOT": "/path/to/project",
        "PROJECT_NAME": "my-project",
        "CMD_WHITE_LIST": "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "CMD_TIMEOUT": "30",
        "RENDER_WITH_SYMBOLS": "true",
        "MAX_ACTIVE_MODELS": "3",
        "ENABLE_SIMPLE_VIEW_MODE": "true"
      }
    }
  }
}
```

##### 方式 2: 通过命令行参数配置 | Method 2: Configure via Command-line Arguments

```json
{
  "mcpServers": {
    "python-ide": {
      "command": "uvx",
      "args": [
        "ide4ai",
        "py-ide4ai-mcp",
        "--root-dir", "/path/to/project",
        "--project-name", "my-project",
        "--cmd-white-list", "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "--cmd-timeout", "30",
        "--render-with-symbols", "true",
        "--max-active-models", "3",
        "--enable-simple-view-mode", "true"
      ]
    }
  }
}
```

##### 方式 3: 混合配置（命令行参数优先级更高）| Method 3: Mixed Configuration (Command-line Arguments Have Higher Priority)

```json
{
  "mcpServers": {
    "python-ide": {
      "command": "uvx",
      "args": [
        "ide4ai",
        "py-ide4ai-mcp",
        "--root-dir", "/path/to/project",
        "--cmd-timeout", "60"
      ],
      "env": {
        "PROJECT_NAME": "my-project",
        "CMD_WHITE_LIST": "ls,pwd,echo,cat"
      }
    }
  }
}
```

**配置参数说明 | Configuration Parameters:**

| 参数名 Parameter | 环境变量 Environment Variable | 命令行参数 CLI Argument | 默认值 Default | 说明 Description |
|-----------------|------------------------------|------------------------|---------------|------------------|
| root_dir | PROJECT_ROOT | --root-dir | "." | 项目根目录 \| Project root directory |
| project_name | PROJECT_NAME | --project-name | "mcp-project" | 项目名称 \| Project name |
| cmd_white_list | CMD_WHITE_LIST | --cmd-white-list | ["ls", "pwd", "echo", "cat", "grep", "find", "head", "tail", "wc"] | 命令白名单（逗号分隔）\| Command whitelist (comma separated) |
| cmd_time_out | CMD_TIMEOUT | --cmd-timeout | 10 | 命令超时时间(秒) \| Command timeout (seconds) |
| render_with_symbols | RENDER_WITH_SYMBOLS | --render-with-symbols | true | 是否渲染符号 \| Whether to render symbols |
| max_active_models | MAX_ACTIVE_MODELS | --max-active-models | 3 | 最大活跃模型数 \| Maximum active models |
| enable_simple_view_mode | ENABLE_SIMPLE_VIEW_MODE | --enable-simple-view-mode | true | 是否启用简化视图模式 \| Whether to enable simple view mode |

**配置优先级 | Configuration Priority:**
```
命令行参数 > 环境变量 > 默认值
Command-line Arguments > Environment Variables > Default Values
```

#### 使用已安装的命令 | Using Installed Command

通过环境变量配置 | Configure via Environment Variables:
```json
{
  "mcpServers": {
    "python-ide": {
      "command": "py-ide4ai-mcp",
      "args": [],
      "env": {
        "PROJECT_ROOT": "/path/to/project",
        "PROJECT_NAME": "my-project",
        "CMD_WHITE_LIST": "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "CMD_TIMEOUT": "30"
      }
    }
  }
}
```

通过命令行参数配置 | Configure via Command-line Arguments:
```json
{
  "mcpServers": {
    "python-ide": {
      "command": "py-ide4ai-mcp",
      "args": [
        "--root-dir", "/path/to/project",
        "--project-name", "my-project",
        "--cmd-white-list", "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "--cmd-timeout", "30"
      ]
    }
  }
}
```

#### 使用 Python 模块 | Using Python Module

通过环境变量配置 | Configure via Environment Variables:
```json
{
  "mcpServers": {
    "python-ide": {
      "command": "python",
      "args": ["-m", "ide4ai.python_ide.mcp.server"],
      "env": {
        "PROJECT_ROOT": "/path/to/project",
        "PROJECT_NAME": "my-project",
        "CMD_WHITE_LIST": "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "CMD_TIMEOUT": "30"
      }
    }
  }
}
```

通过命令行参数配置 | Configure via Command-line Arguments:
```json
{
  "mcpServers": {
    "python-ide": {
      "command": "python",
      "args": [
        "-m", "ide4ai.python_ide.mcp.server",
        "--root-dir", "/path/to/project",
        "--project-name", "my-project",
        "--cmd-white-list", "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "--cmd-timeout", "30"
      ]
    }
  }
}
```

## 开发指南 | Development Guide

### 添加新工具 | Adding New Tools

1. 在 `schemas/tools.py` 中定义输入输出 Schema
2. 在 `tools/` 目录创建新工具文件
3. 继承 `BaseTool` 并实现必要方法
4. 在 `server.py` 的 `_register_tools()` 中注册工具

Example:

```python
# 1. Define schema in schemas/tools.py
class NewToolInput(BaseModel):
    param: str = Field(..., description="Parameter description")

# 2. Create tool file in tools/
class NewTool(BaseTool):
    @property
    def name(self) -> str:
        return "NewTool"
    
    @property
    def description(self) -> str:
        return "Tool description"
    
    @property
    def input_schema(self) -> dict[str, Any]:
        return NewToolInput.model_json_schema()
    
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        # Implementation
        pass

# 3. Register in server.py
def _register_tools(self):
    new_tool = NewTool(self.ide)
    self.tools[new_tool.name] = new_tool
```

## 测试 | Testing

```bash
# 运行单元测试 | Run unit tests
pytest tests/integration/python_ide/test_mcp_server.py

# 运行集成测试 | Run integration tests
pytest tests/integration/python_ide/test_mcp_tools.py
```

## 依赖 | Dependencies

- `mcp`: MCP SDK
- `pydantic`: 数据验证 | Data validation
- `loguru`: 日志记录 | Logging
- `ide4ai`: PythonIDE 核心 | PythonIDE core

## 注意事项 | Notes

1. **安全性 | Security**: 
   - 使用命令白名单控制可执行命令 | Use command whitelist to control executable commands
   - 谨慎使用 `dangerously_disable_sandbox` | Use `dangerously_disable_sandbox` carefully

2. **性能 | Performance**:
   - IDE 实例使用单例模式，避免重复初始化 | IDE instance uses singleton pattern to avoid repeated initialization
   - 工具执行是异步的 | Tool execution is asynchronous

3. **错误处理 | Error Handling**:
   - 所有工具都有统一的错误处理机制 | All tools have unified error handling
   - 错误信息会记录到日志 | Error messages are logged

## 路线图 | Roadmap

- [x] 基础架构搭建 | Basic architecture setup
- [x] Bash 工具实现 | Bash tool implementation
- [ ] 其他工具实现 | Other tools implementation
- [ ] Resource 支持 | Resource support
- [ ] 完整的测试覆盖 | Complete test coverage
- [ ] 性能优化 | Performance optimization
- [ ] 文档完善 | Documentation improvement
