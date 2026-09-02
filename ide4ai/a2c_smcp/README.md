# IDE4AI MCP Server

将 IDE 的能力封装为 MCP (Model Context Protocol) Server，为 AI 助手提供强大的 IDE 能力。

Wraps IDE capabilities as MCP (Model Context Protocol) Server, providing powerful IDE capabilities for AI assistants.

## 架构设计 | Architecture

```
ide4ai/a2c_smcp/
├── __init__.py              # 公共导出 | Public exports
├── cli.py                   # 通用 MCP Server 与 CLI | Generic MCP server and CLI
├── server.py                # MCP Server 基类 | MCP Server base implementation
├── config.py                # 配置管理 | Configuration management
├── catalog.py               # 动态工具/资源目录 | Dynamic catalogs
├── providers.py             # 项目感知 Provider | Project-aware providers
├── projects/                # 持久化项目与懒加载运行态 | Persistent projects and lazy runtimes
├── tools/                   # 工具实现 | Tools implementation
│   ├── __init__.py
│   ├── base.py             # 工具基类 | Tool base class
│   ├── bash.py             # Legacy Python API compatibility | 旧 Python API 兼容层
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

### 1. stdio 多项目会话 | stdio Multi-project Session

多项目 Server 当前使用 stdio。SSE 与 Streamable HTTP 尚未定义会话隔离语义，因此会拒绝启动。

The multi-project server currently uses stdio. SSE and Streamable HTTP are rejected until their session-isolation semantics are defined.

### 2. 动态目录与懒加载 | Dynamic Catalog and Lazy Loading

工具和资源由当前项目实时组合。目录发现不会创建 IDE；第一次调用 IDE 工具或读取窗口资源时才加载对应项目的 IDE/Workspace/LSP。切换项目不会改变已经开始的调用。

### 3. 工具封装 | Tool Encapsulation

每个工具独立实现，继承自 `BaseTool`，提供：
- 标准化的输入验证 | Standardized input validation
- 统一的错误处理 | Unified error handling
- 清晰的接口定义 | Clear interface definition

Each tool is independently implemented, inheriting from `BaseTool`, providing:
- Standardized input validation
- Unified error handling
- Clear interface definition

### 4. Schema 定义 | Schema Definition

使用 Pydantic 模型定义所有工具的输入输出 Schema，确保类型安全。

Uses Pydantic models to define input/output schemas for all tools, ensuring type safety.

## 已实现工具 | Implemented Tools

### Terminal 与 TFBash 0.2 | Terminal and TFBash 0.2

选择项目后，MCP 目录使用状态驱动的 `terminal_start` / `terminal_close` 代替旧 `Bash` 和 toggle 型 `Terminal`。关闭状态下执行 `terminal_start` 会为当前项目创建进程内 `EmbeddedShellRuntime`；成功后动态暴露 TFBash 原生的七个工具：

- `shell_open`
- `shell_exec`
- `shell_read`
- `shell_write`
- `shell_signal`
- `shell_list`
- `shell_close`

工具定义、输入输出协议、错误包和 A2C tags 均直接来自 `tfbash-mcp==0.2.0`。`terminal_start` 支持可选 cwd、Shell、默认启动命令、环境覆盖和 deadline；项目不可变的 `root_dir` 始终作为 `workspace_root`，且是默认 cwd。它只创建 Runtime，不隐式创建 Shell。开启后只展示 `terminal_close`；该工具、`project_unload`、`project_delete` 和 Server 关闭复用同一有界优雅清理路径，先 terminate、等待 grace period、再 kill 剩余受管进程。生命周期工具按目标状态幂等，工具列表变化通过 MCP 事件通知，不使用轮询。

The legacy `BashTool` import remains available for direct Python compatibility, but the project-aware MCP server no longer registers it.

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
uvx --from ide4ai ide4ai-mcp

# 或者安装到全局 | Or install globally
uv tool install ide4ai
ide4ai-mcp
```

#### 使用 pip | Using pip

```bash
pip install ide4ai
ide4ai-mcp
```

### 作为独立服务运行 | Run as Standalone Service

#### 使用命令行工具 | Using CLI Tool

**默认使用 stdio 模式 | Default stdio mode:**
```bash
# 如果已安装 | If installed
ide4ai-mcp

# 使用 uv run (开发环境) | Using uv run (development)
uv run ide4ai-mcp

# 使用 Python 模块 | Using Python module
python -m ide4ai.a2c_smcp.cli
```

默认启动不隐式创建项目。客户端使用 `project_create` 注册目录；只要存在注册项目，Server 就持久化并恢复唯一的当前项目，可使用 `project_switch` 主动切换。`project_list` 将唯一项目名放在集合顶层的 `current_project` 字段，只有项目列表为空时该字段才为 `null`。项目名称、根目录和 LSP 配置只属于 `project_create`，不是 Server 启动参数。可用 `project_unload` 释放当前项目的 Terminal/IDE/Workspace/LSP 运行态。

### 在代码中使用 | Use in Code

#### 方式 1: 使用默认配置（从环境变量和命令行参数加载）| Method 1: Use Default Configuration (Load from Environment Variables and Command-line Arguments)

```python
import asyncio
from ide4ai.a2c_smcp import MCPServerConfig, IDEMCPServer

async def main():
    # 自动从环境变量和命令行参数加载配置 | Automatically load configuration from environment variables and command-line arguments
    # 优先级：命令行参数 > 环境变量 > 默认值 | Priority: Command-line arguments > Environment variables > Default values
    config = MCPServerConfig()
    
    # 创建并运行 server | Create and run server
    server = IDEMCPServer(config)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

#### 方式 2: 通过代码直接指定配置 | Method 2: Specify Configuration Directly in Code

**使用 stdio 模式 | Using stdio mode:**
```python
import asyncio
from confz import DataSource
from ide4ai.a2c_smcp import MCPServerConfig, IDEMCPServer

async def main():
    with MCPServerConfig.change_config_sources(DataSource(data={
        "transport": "stdio",
        "cmd_white_list": ["ls", "pwd", "echo", "cat"],
        "project_registry_path": "/path/to/projects.json",
    })):
        config = MCPServerConfig()
    
    server = IDEMCPServer(config)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### 配置 MCP Client | Configure MCP Client

在 MCP 客户端配置文件中添加：

Add to MCP client configuration file:

#### stdio 模式（默认，推荐用于本地集成）| stdio Mode (Default, Recommended for Local Integration)

##### 使用 uvx (推荐) | Using uvx (Recommended)

###### 方式 1: 通过环境变量配置 | Method 1: Configure via Environment Variables

```json
{
  "mcpServers": {
    "python-ide": {
      "command": "uvx",
      "args": ["--from", "ide4ai", "ide4ai-mcp"],
      "env": {
        "TRANSPORT": "stdio",
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

###### 方式 2: 通过命令行参数配置 | Method 2: Configure via Command-line Arguments

```json
{
  "mcpServers": {
    "python-ide": {
      "command": "uvx",
      "args": [
        "--from", "ide4ai",
        "ide4ai-mcp",
        "--transport", "stdio",
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

###### 方式 3: 混合配置（命令行参数优先级更高）| Method 3: Mixed Configuration (Command-line Arguments Have Higher Priority)

```json
{
  "mcpServers": {
    "python-ide": {
      "command": "uvx",
      "args": [
        "--from", "ide4ai",
        "ide4ai-mcp",
        "--cmd-timeout", "60"
      ],
      "env": {
        "TRANSPORT": "stdio",
        "CMD_WHITE_LIST": "ls,pwd,echo,cat"
      }
    }
  }
}
```

##### 使用已安装的命令 | Using Installed Command

通过环境变量配置 | Configure via Environment Variables:
```json
{
  "mcpServers": {
    "python-ide": {
      "command": "ide4ai-mcp",
      "args": [],
      "env": {
        "TRANSPORT": "stdio",
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
      "command": "ide4ai-mcp",
      "args": [
        "--transport", "stdio",
        "--cmd-white-list", "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "--cmd-timeout", "30"
      ]
    }
  }
}
```

##### 使用 Python 模块 | Using Python Module

通过环境变量配置 | Configure via Environment Variables:
```json
{
  "mcpServers": {
    "python-ide": {
      "command": "python",
      "args": ["-m", "ide4ai.a2c_smcp.cli"],
      "env": {
        "TRANSPORT": "stdio",
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
        "-m", "ide4ai.a2c_smcp.cli",
        "--transport", "stdio",
        "--cmd-white-list", "ls,pwd,echo,cat,grep,find,head,tail,wc",
        "--cmd-timeout", "30"
      ]
    }
  }
}
```

---

**配置参数说明 | Configuration Parameters:**

| 参数名 Parameter | 环境变量 Environment Variable | 命令行参数 CLI Argument | 默认值 Default | 说明 Description |
|-----------------|------------------------------|------------------------|---------------|------------------|
| transport | TRANSPORT | --transport | "stdio" | 当前多项目 Server 仅支持 stdio \| The multi-project server currently supports stdio only |
| host | HOST | --host | "127.0.0.1" | 服务器主机 \| Server host (for sse/streamable-http) |
| port | PORT | --port | 8000 | 服务器端口 \| Server port (for sse/streamable-http) |
| project_registry_path | PROJECT_REGISTRY_PATH | --project-registry-path | platform config/ide4ai/projects.json | Server 持久化项目及当前选择的元数据文件 \| Server-owned project and selection metadata |
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

### 传输范围 | Transport Scope

当前动态多项目服务器仅支持 stdio transport。网络传输需要先实现每个 MCP 会话独立的项目选择和运行态所有权。

## 开发指南 | Development Guide

### 添加新工具 | Adding New Tools

1. 在 `schemas/tools.py` 中定义输入输出 Schema
2. 在 `tools/` 目录创建新工具文件
3. 继承 `BaseTool` 并实现必要方法
4. 将工具类加入 `IDEToolProvider`，或为状态化工具实现独立 `ToolProvider`

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
pytest tests/integration/python_ide/a2c_smcp/test_mcp_server_integration.py

# 运行集成测试 | Run integration tests
pytest tests/a2c_smcp/tools
```

## 依赖 | Dependencies

- `mcp`: MCP SDK
- `pydantic`: 数据验证 | Data validation
- `loguru`: 日志记录 | Logging
- `ide4ai`: IDE 核心 | IDE core

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
