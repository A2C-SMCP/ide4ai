# 命令过滤器使用指南 | Command Filter Usage Guide

## 概述 | Overview

`CommandFilterConfig` 提供了灵活的命令过滤机制，支持黑名单和白名单两种模式，用于控制终端环境中可执行的命令。

`CommandFilterConfig` provides a flexible command filtering mechanism, supporting both blacklist and whitelist modes to control executable commands in terminal environments.

## 设计原则 | Design Principles

1. **白名单优先**：如果指定了白名单，只有白名单中的命令才能执行
2. **黑名单补充**：如果未指定白名单，则除黑名单外的所有命令都可执行
3. **默认安全**：默认使用黑名单模式，阻止危险命令（如 `rm`, `dd` 等）

1. **Whitelist Priority**: If whitelist is specified, only whitelisted commands can execute
2. **Blacklist Supplement**: If whitelist is not specified, all commands except blacklisted ones can execute
3. **Default Safety**: Default to blacklist mode, blocking dangerous commands (e.g., `rm`, `dd`)

## 使用方式 | Usage

### 1. 白名单模式 | Whitelist Mode

仅允许特定命令执行，最安全的方式：

```python
from ide4ai.environment.terminal import CommandFilterConfig, PexpectTerminalEnv, EnvironmentArguments

# 创建白名单配置
cmd_filter = CommandFilterConfig.from_white_list(["echo", "ls", "pwd", "cat"])

# 使用配置创建终端环境
env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=10),
    work_dir="/path/to/workspace",
    cmd_filter=cmd_filter,
)
```

### 2. 黑名单模式 | Blacklist Mode

允许大部分命令，仅阻止危险命令：

```python
from ide4ai.environment.terminal import CommandFilterConfig, PexpectTerminalEnv, EnvironmentArguments

# 创建自定义黑名单配置
cmd_filter = CommandFilterConfig.allow_all_except(["rm", "dd", "mkfs"])

# 或使用默认黑名单（推荐）
cmd_filter = CommandFilterConfig.allow_all_except()  # 使用 DEFAULT_BLACK_LIST

env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=10),
    work_dir="/path/to/workspace",
    cmd_filter=cmd_filter,
)
```

### 3. 允许所有命令 | Allow All Commands

**⚠️ 不推荐用于生产环境 | Not recommended for production**

```python
from ide4ai.environment.terminal import CommandFilterConfig, PexpectTerminalEnv, EnvironmentArguments

# 允许所有命令（无任何限制）
cmd_filter = CommandFilterConfig.allow_all()

env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=10),
    work_dir="/path/to/workspace",
    cmd_filter=cmd_filter,
)
```

### 4. 默认行为 | Default Behavior

如果不指定 `cmd_filter`，系统会使用默认黑名单模式：

```python
from ide4ai.environment.terminal import PexpectTerminalEnv, EnvironmentArguments

# 不指定 cmd_filter，使用默认黑名单
env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=10),
    work_dir="/path/to/workspace",
)
# 等同于：cmd_filter=CommandFilterConfig.allow_all_except()
```

## 在 PythonIDE 中使用 | Using with PythonIDE

### 白名单模式 | Whitelist Mode

```python
from ide4ai.environment.terminal import CommandFilterConfig
from ide4ai.python_ide.ide import PythonIDE

# 创建白名单配置
cmd_filter = CommandFilterConfig.from_white_list([
    "echo", "ls", "pwd", "cat", "grep", 
    "python", "python3", "pip", "uv"
])

ide = PythonIDE(
    root_dir="/path/to/project",
    project_name="my_project",
    cmd_filter=cmd_filter,
)
```

### 黑名单模式 | Blacklist Mode

```python
from ide4ai.environment.terminal import CommandFilterConfig
from ide4ai.python_ide.ide import PythonIDE

# 使用默认黑名单
ide = PythonIDE(
    root_dir="/path/to/project",
    project_name="my_project",
    # cmd_filter 不指定，使用默认黑名单
)

# 或自定义黑名单
cmd_filter = CommandFilterConfig.allow_all_except(["rm", "dd", "shutdown"])
ide = PythonIDE(
    root_dir="/path/to/project",
    project_name="my_project",
    cmd_filter=cmd_filter,
)
```

## 默认黑名单 | Default Blacklist

系统默认阻止以下危险命令：

```python
DEFAULT_BLACK_LIST = [
    "rm",        # 删除文件
    "rmdir",     # 删除目录
    "dd",        # 磁盘操作
    "mkfs",      # 格式化文件系统
    "format",    # 格式化
    "fdisk",     # 磁盘分区
    "parted",    # 磁盘分区
    "shutdown",  # 关机
    "reboot",    # 重启
    "halt",      # 停机
    "poweroff",  # 关机
    "init",      # 系统初始化
    "telinit",   # 运行级别切换
]
```

## API 参考 | API Reference

### CommandFilterConfig

#### 方法 | Methods

- **`from_white_list(white_list: list[str]) -> CommandFilterConfig`**
  - 从白名单创建配置
  - Create config from whitelist

- **`allow_all_except(black_list: list[str] | None = None) -> CommandFilterConfig`**
  - 创建仅使用黑名单的配置
  - Create config with only blacklist
  - 如果 `black_list` 为 `None`，使用 `DEFAULT_BLACK_LIST`

- **`allow_all() -> CommandFilterConfig`**
  - 创建允许所有命令的配置（不推荐）
  - Create config allowing all commands (not recommended)

- **`is_allowed(command: str) -> bool`**
  - 检查命令是否允许执行
  - Check if command is allowed to execute

- **`get_rejection_reason(command: str) -> str`**
  - 获取命令被拒绝的原因
  - Get reason why command was rejected

## 最佳实践 | Best Practices

1. **生产环境使用白名单**：在生产环境中，建议使用白名单模式，明确指定允许的命令
2. **开发环境使用黑名单**：在开发环境中，可以使用黑名单模式以提供更大的灵活性
3. **定期审查命令列表**：定期审查和更新白名单/黑名单，确保安全性
4. **最小权限原则**：只授予必要的命令权限

1. **Use Whitelist in Production**: In production, use whitelist mode to explicitly specify allowed commands
2. **Use Blacklist in Development**: In development, blacklist mode provides more flexibility
3. **Regular Review**: Regularly review and update whitelist/blacklist for security
4. **Principle of Least Privilege**: Only grant necessary command permissions

## 错误处理 | Error Handling

当命令被拒绝时，会抛出 `ValueError` 异常：

```python
from ide4ai.environment.terminal import CommandFilterConfig, PexpectTerminalEnv, EnvironmentArguments

cmd_filter = CommandFilterConfig.from_white_list(["echo", "ls"])
env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=10),
    work_dir="/tmp",
    cmd_filter=cmd_filter,
)

try:
    env.step({
        "category": "terminal",
        "action_name": "rm",  # 不在白名单中
        "action_args": ["-rf", "/"],
    })
except ValueError as e:
    print(f"命令被拒绝: {e}")
    # 输出: 命令被拒绝: Command 'rm' not in whitelist
```

## 迁移指南 | Migration Guide

如果你之前使用 `cmd_white_list` 参数，现在需要迁移到 `cmd_filter`：

### 旧代码 | Old Code

```python
# ❌ 已废弃
ide = PythonIDE(
    cmd_white_list=["echo", "ls", "pwd"],
    root_dir="/path/to/project",
    project_name="my_project",
)
```

### 新代码 | New Code

```python
# ✅ 推荐
from ide4ai.environment.terminal import CommandFilterConfig

cmd_filter = CommandFilterConfig.from_white_list(["echo", "ls", "pwd"])
ide = PythonIDE(
    root_dir="/path/to/project",
    project_name="my_project",
    cmd_filter=cmd_filter,
)
```

## 示例场景 | Example Scenarios

### 场景 1：AI 代码助手

```python
# 允许常见的开发命令
cmd_filter = CommandFilterConfig.from_white_list([
    "ls", "pwd", "cat", "grep", "find", "head", "tail", "wc",
    "python", "python3", "pip", "uv", "poetry",
    "git", "npm", "yarn", "make",
])
```

### 场景 2：数据分析环境

```python
# 允许数据处理和分析命令
cmd_filter = CommandFilterConfig.from_white_list([
    "python", "python3", "jupyter", "ipython",
    "ls", "pwd", "cat", "head", "tail",
])
```

### 场景 3：受限沙箱环境

```python
# 仅允许最基本的命令
cmd_filter = CommandFilterConfig.from_white_list([
    "echo", "ls", "pwd", "cat",
])
```
