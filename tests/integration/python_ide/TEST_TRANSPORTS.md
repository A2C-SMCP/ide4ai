# MCP Server 传输模式测试说明 | MCP Server Transport Mode Test Guide

## 测试文件 | Test Files

### 1. `test_mcp_server_transports.py`
测试三种传输模式的功能和集成 | Tests functionality and integration of three transport modes

**测试类 | Test Classes:**
- `TestMCPServerTransportModes`: 基础配置和初始化测试 | Basic configuration and initialization tests
- `TestMCPServerSSETransport`: SSE 传输模式测试 | SSE transport mode tests
- `TestMCPServerStreamableHTTPTransport`: Streamable HTTP 传输模式测试 | Streamable HTTP transport mode tests
- `TestMCPServerTransportIntegration`: 传输模式集成测试 | Transport mode integration tests

### 2. `test_mcp_server_config.py`
扩展了配置测试，添加了传输模式配置测试 | Extended configuration tests with transport mode configuration tests

**新增测试方法 | New Test Methods:**
- `test_transport_mode_config`: 测试传输模式配置 | Test transport mode configuration
- `test_transport_mode_from_env`: 测试从环境变量加载传输配置 | Test loading transport config from environment variables
- `test_transport_mode_from_cli`: 测试从命令行参数加载传输配置 | Test loading transport config from CLI arguments
- `test_mixed_config_with_transport`: 测试混合配置 | Test mixed configuration

## 运行测试 | Running Tests

### 运行所有传输模式测试 | Run All Transport Mode Tests

```bash
# 运行所有传输模式相关测试 | Run all transport mode related tests
pytest tests/integration/python_ide/test_mcp_server_transports.py -v

# 运行配置测试（包括传输模式配置）| Run configuration tests (including transport mode config)
pytest tests/integration/python_ide/test_mcp_server_config.py -v
```

### 运行特定测试类 | Run Specific Test Class

```bash
# 只测试 SSE 传输 | Test SSE transport only
pytest tests/integration/python_ide/test_mcp_server_transports.py::TestMCPServerSSETransport -v

# 只测试 Streamable HTTP 传输 | Test Streamable HTTP transport only
pytest tests/integration/python_ide/test_mcp_server_transports.py::TestMCPServerStreamableHTTPTransport -v

# 只测试传输模式配置 | Test transport mode configuration only
pytest tests/integration/python_ide/test_mcp_server_config.py::TestMCPServerConfig::test_transport_mode_config -v
```

### 运行特定测试方法 | Run Specific Test Method

```bash
# 测试 SSE 服务器启动和关闭 | Test SSE server startup and shutdown
pytest tests/integration/python_ide/test_mcp_server_transports.py::TestMCPServerSSETransport::test_sse_server_startup_and_shutdown -v

# 测试 Streamable HTTP 端点可访问性 | Test Streamable HTTP endpoints accessibility
pytest tests/integration/python_ide/test_mcp_server_transports.py::TestMCPServerStreamableHTTPTransport::test_streamable_http_server_endpoints_accessible -v
```

### 使用覆盖率运行 | Run with Coverage

```bash
# 运行测试并生成覆盖率报告 | Run tests and generate coverage report
pytest tests/integration/python_ide/test_mcp_server_transports.py \
    --cov=ide4ai.python_ide.mcp \
    --cov-report=html \
    --cov-report=term-missing \
    -v

# 查看覆盖率报告 | View coverage report
open htmlcov/index.html
```

## 测试覆盖范围 | Test Coverage

### 配置测试 | Configuration Tests
- ✅ 默认配置值 | Default configuration values
- ✅ stdio 模式配置 | stdio mode configuration
- ✅ SSE 模式配置 | SSE mode configuration
- ✅ Streamable HTTP 模式配置 | Streamable HTTP mode configuration
- ✅ 环境变量配置 | Environment variable configuration
- ✅ 命令行参数配置 | CLI argument configuration
- ✅ 混合配置 | Mixed configuration
- ✅ 无效传输模式验证 | Invalid transport mode validation

### 服务器初始化测试 | Server Initialization Tests
- ✅ stdio 模式服务器初始化 | stdio mode server initialization
- ✅ SSE 模式服务器初始化 | SSE mode server initialization
- ✅ Streamable HTTP 模式服务器初始化 | Streamable HTTP mode server initialization
- ✅ 工具注册验证 | Tool registration verification

### SSE 传输测试 | SSE Transport Tests
- ✅ 服务器启动和关闭 | Server startup and shutdown
- ✅ 端点可访问性 | Endpoint accessibility
- ✅ SSE 连接端点 (`GET /sse`) | SSE connection endpoint
- ✅ 消息发送端点 (`POST /messages/`) | Message sending endpoint

### Streamable HTTP 传输测试 | Streamable HTTP Transport Tests
- ✅ 服务器启动和关闭 | Server startup and shutdown
- ✅ 端点可访问性 | Endpoint accessibility
- ✅ 消息处理端点 (`POST /message`) | Message handling endpoint

### 集成测试 | Integration Tests
- ✅ 传输模式路由逻辑 | Transport mode routing logic
- ✅ 无效传输模式错误处理 | Invalid transport mode error handling

## 测试注意事项 | Test Notes

### 超时设置 | Timeout Settings
某些测试使用了 `@pytest.mark.timeout(10)` 标记，确保测试不会无限期挂起。
Some tests use `@pytest.mark.timeout(10)` marker to ensure tests don't hang indefinitely.

### 端口使用 | Port Usage
测试使用不同的端口（8005-8010）以避免冲突。如果遇到端口占用问题，可以修改测试中的端口号。
Tests use different ports (8005-8010) to avoid conflicts. If you encounter port conflicts, you can modify the port numbers in tests.

### 异步测试 | Async Tests
所有涉及服务器启动的测试都是异步的，使用 `@pytest.mark.asyncio` 标记。
All tests involving server startup are asynchronous and use `@pytest.mark.asyncio` marker.

### 清理机制 | Cleanup Mechanism
测试会自动清理启动的服务器任务，确保不会留下后台进程。
Tests automatically clean up started server tasks to ensure no background processes are left.

## 故障排查 | Troubleshooting

### 端口已被占用 | Port Already in Use
```bash
# 查找占用端口的进程 | Find process using the port
lsof -i :8000

# 终止进程 | Kill the process
kill -9 <PID>
```

### 测试超时 | Test Timeout
如果测试超时，可能是因为：
If tests timeout, it might be because:
1. 服务器启动时间过长 | Server takes too long to start
2. 网络问题 | Network issues
3. 端口被占用 | Port is already in use

解决方法 | Solutions:
- 增加等待时间 | Increase wait time
- 检查端口可用性 | Check port availability
- 使用不同的端口 | Use different ports

### 依赖问题 | Dependency Issues
确保已安装所有必要的依赖：
Ensure all necessary dependencies are installed:
```bash
uv sync
```

## 持续集成 | Continuous Integration

这些测试可以集成到 CI/CD 流程中：
These tests can be integrated into CI/CD pipelines:

```yaml
# .github/workflows/tests.yml 示例 | Example
- name: Run Transport Mode Tests
  run: |
    pytest tests/integration/python_ide/test_mcp_server_transports.py -v
    pytest tests/integration/python_ide/test_mcp_server_config.py -v
```

## 贡献指南 | Contributing Guidelines

添加新的传输模式测试时，请确保：
When adding new transport mode tests, ensure:

1. 使用独特的端口号 | Use unique port numbers
2. 添加适当的超时设置 | Add appropriate timeout settings
3. 实现清理机制 | Implement cleanup mechanisms
4. 添加中英文双语注释 | Add bilingual comments (Chinese and English)
5. 更新此文档 | Update this documentation
