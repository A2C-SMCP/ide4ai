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

### 作为独立服务运行 | Run as Standalone Service

```bash
python -m ide4ai.python_ide.mcp.server
```

### 在代码中使用 | Use in Code

```python
import asyncio
from ide4ai.python_ide.mcp import MCPServerConfig, PythonIDEMCPServer

async def main():
    # 创建配置 | Create configuration
    config = MCPServerConfig(
        cmd_white_list=["ls", "pwd", "echo", "cat"],
        root_dir="/path/to/project",
        project_name="my-project",
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

```json
{
  "mcpServers": {
    "python-ide": {
      "command": "python",
      "args": ["-m", "ide4ai.python_ide.mcp.server"],
      "env": {
        "PROJECT_ROOT": "/path/to/project",
        "PROJECT_NAME": "my-project"
      }
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
