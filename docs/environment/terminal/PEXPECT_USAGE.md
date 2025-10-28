# PexpectTerminalEnv 使用指南 | PexpectTerminalEnv Usage Guide

## 概述 | Overview

`PexpectTerminalEnv` 是基于 `pexpect` 库实现的终端环境,相比于 `TerminalEnv`,它提供了以下增强功能:

`PexpectTerminalEnv` is a terminal environment implementation based on the `pexpect` library. Compared to `TerminalEnv`, it provides the following enhancements:

### 主要优势 | Key Advantages

1. **持久会话 | Persistent Session**
   - 维持一个持久的 shell 进程
   - 环境变量和状态在命令间保持
   - Maintains a persistent shell process
   - Environment variables and state persist across commands

2. **虚拟环境支持 | Virtual Environment Support**
   - 可以在初始化时激活虚拟环境
   - 后续所有命令都在虚拟环境中执行
   - Can activate virtual environment during initialization
   - All subsequent commands execute within the virtual environment

3. **真实 Shell 行为 | Authentic Shell Behavior**
   - `cd`、`export` 等内置命令正常工作
   - 支持 shell 脚本和管道
   - Built-in commands like `cd`, `export` work correctly
   - Supports shell scripts and pipes

4. **交互式支持 | Interactive Support**
   - 支持需要用户输入的命令(未来扩展)
   - Supports commands requiring user input (future extension)

## 安装依赖 | Installation

首先需要安装 `pexpect`:

First, install `pexpect`:

```bash
pip install pexpect
# 或 | or
uv add pexpect
# 或 | or
poetry add pexpect
```

## 基本使用 | Basic Usage

### 1. 创建基础终端环境 | Create Basic Terminal Environment

```python
from ide4ai.environment.terminal.base import EnvironmentArguments
from ide4ai.environment.terminal.pexpect_terminal_env import PexpectTerminalEnv

# 配置参数 | Configure parameters
args = EnvironmentArguments(
    image_name="local",
    timeout=30  # 命令超时时间(秒) | Command timeout (seconds)
)

# 命令白名单 | Command whitelist
white_list = ["echo", "ls", "cat", "python", "pip", "git"]

# 创建环境 | Create environment
env = PexpectTerminalEnv(
    args=args,
    white_list=white_list,
    work_dir="/path/to/your/project"
)

# 执行命令 | Execute command
action = {
    "category": "terminal",
    "action_name": "echo",
    "action_args": ["Hello, World!"]
}

obs, reward, done, success, info = env.step(action)
print(obs["obs"])  # 输出: Hello, World!

# 关闭环境 | Close environment
env.close()
```

### 2. 使用虚拟环境 | Using Virtual Environment

这是 `PexpectTerminalEnv` 的核心功能之一:

This is one of the core features of `PexpectTerminalEnv`:

#### 使用 venv | Using venv

```python
env = PexpectTerminalEnv(
    args=args,
    white_list=white_list,
    work_dir="/path/to/your/project",
    init_venv="source .venv/bin/activate"  # 激活 venv | Activate venv
)

# 现在所有 Python 命令都在虚拟环境中执行
# Now all Python commands execute in the virtual environment
action = {
    "category": "terminal",
    "action_name": "python",
    "action_args": ["-c", "import sys; print(sys.prefix)"]
}

obs, _, _, _, _ = env.step(action)
# 输出会显示虚拟环境路径 | Output will show virtual environment path
```

#### 使用 uv | Using uv

```python
env = PexpectTerminalEnv(
    args=args,
    white_list=["uv", "python", "pip"],
    work_dir="/path/to/your/project",
    init_venv="source .venv/bin/activate"  # uv 创建的虚拟环境 | venv created by uv
)

# 或者使用 uv run (如果 uv 支持) | Or use uv run (if supported by uv)
action = {
    "category": "terminal",
    "action_name": "uv",
    "action_args": ["run", "python", "--version"]
}
```

#### 使用 poetry | Using poetry

```python
env = PexpectTerminalEnv(
    args=args,
    white_list=["poetry", "python", "pip"],
    work_dir="/path/to/your/project",
    init_venv="source $(poetry env info --path)/bin/activate"
)

# 或者直接使用 poetry run | Or use poetry run directly
action = {
    "category": "terminal",
    "action_name": "poetry",
    "action_args": ["run", "python", "--version"]
}
```

### 3. 持久会话特性 | Persistent Session Features

#### 环境变量保持 | Environment Variable Persistence

```python
# 设置环境变量 | Set environment variable
env.set_env_var("MY_VAR", "my_value")

# 获取环境变量 | Get environment variable
value = env.get_env_var("MY_VAR")
print(value)  # 输出: my_value

# 在后续命令中使用 | Use in subsequent commands
action = {
    "category": "terminal",
    "action_name": "echo",
    "action_args": ["$MY_VAR"]
}
obs, _, _, _, _ = env.step(action)
print(obs["obs"])  # 输出: my_value
```

#### 目录切换 | Directory Change

```python
# 切换目录 | Change directory
output, success = env.change_dir(path="./subdir")

if success:
    print(f"Current directory: {env.current_dir}")
    
    # 后续命令在新目录中执行 | Subsequent commands execute in new directory
    action = {
        "category": "terminal",
        "action_name": "pwd",
        "action_args": []
    }
    obs, _, _, _, _ = env.step(action)
    print(obs["obs"])  # 显示新目录路径 | Shows new directory path
```

### 4. 命令历史和渲染 | Command History and Rendering

```python
# 执行多个命令 | Execute multiple commands
commands = [
    {"category": "terminal", "action_name": "echo", "action_args": ["Command 1"]},
    {"category": "terminal", "action_name": "echo", "action_args": ["Command 2"]},
    {"category": "terminal", "action_name": "echo", "action_args": ["Command 3"]},
]

for cmd in commands:
    env.step(cmd)

# 渲染最近的命令历史 | Render recent command history
output = env.render()
print(output)
# 显示最近 3 条命令及其输出 | Shows last 3 commands and their output
```

### 5. 重置环境 | Reset Environment

```python
# 执行一些操作 | Perform some operations
env.step({"category": "terminal", "action_name": "echo", "action_args": ["test"]})

# 重置环境 | Reset environment
obs, info = env.reset()

# 环境被重置,命令历史清空,shell 重新初始化
# Environment is reset, command history cleared, shell reinitialized
print(obs.obs)  # 输出: Reset environment successfully
```

## 在 PythonIDE 中使用 | Using in PythonIDE

修改 `PythonIDE` 以支持 `PexpectTerminalEnv`:

Modify `PythonIDE` to support `PexpectTerminalEnv`:

```python
from ide4ai.base import IDE
from ide4ai.environment.terminal.pexpect_terminal_env import PexpectTerminalEnv

class PythonIDE(IDE):
    def __init__(
        self,
        cmd_white_list: list[str],
        root_dir: str,
        project_name: str,
        init_venv: str | None = None,  # 新增参数 | New parameter
        **kwargs
    ):
        super().__init__(
            cmd_white_list,
            root_dir,
            project_name,
            **kwargs
        )
        self.init_venv = init_venv
    
    def init_terminal(self) -> PexpectTerminalEnv:
        """初始化终端环境 | Initialize terminal environment"""
        return PexpectTerminalEnv(
            EnvironmentArguments(image_name="local", timeout=self.cmd_time_out),
            self.cmd_white_list,
            self.root_dir,
            init_venv=self.init_venv  # 传入虚拟环境初始化命令 | Pass venv init command
        )

# 使用示例 | Usage example
ide = PythonIDE(
    cmd_white_list=["python", "pip", "pytest"],
    root_dir="/path/to/project",
    project_name="my_project",
    init_venv="source .venv/bin/activate"  # 激活虚拟环境 | Activate venv
)
```

## 实际应用场景 | Practical Use Cases

### 场景 1: 在虚拟环境中运行测试 | Scenario 1: Run Tests in Virtual Environment

```python
env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=60),
    white_list=["pytest", "python"],
    work_dir="/path/to/project",
    init_venv="source .venv/bin/activate"
)

# 运行测试 | Run tests
action = {
    "category": "terminal",
    "action_name": "pytest",
    "action_args": ["tests/", "-v"]
}

obs, reward, done, success, _ = env.step(action)
print(f"Tests {'passed' if success else 'failed'}")
print(obs["obs"])
```

### 场景 2: 安装依赖并验证 | Scenario 2: Install Dependencies and Verify

```python
env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=120),
    white_list=["pip", "python"],
    work_dir="/path/to/project",
    init_venv="source .venv/bin/activate"
)

# 安装依赖 | Install dependencies
install_action = {
    "category": "terminal",
    "action_name": "pip",
    "action_args": ["install", "requests"]
}
env.step(install_action)

# 验证安装 | Verify installation
verify_action = {
    "category": "terminal",
    "action_name": "python",
    "action_args": ["-c", "import requests; print(requests.__version__)"]
}
obs, _, _, success, _ = env.step(verify_action)

if success:
    print(f"requests version: {obs['obs']}")
```

### 场景 3: 使用 uv 管理项目 | Scenario 3: Manage Project with uv

```python
env = PexpectTerminalEnv(
    args=EnvironmentArguments(image_name="local", timeout=60),
    white_list=["uv", "python"],
    work_dir="/path/to/project",
    init_venv="source .venv/bin/activate"  # uv 创建的虚拟环境 | venv created by uv
)

# 使用 uv 添加依赖 | Add dependency with uv
action = {
    "category": "terminal",
    "action_name": "uv",
    "action_args": ["add", "httpx"]
}
env.step(action)

# 运行脚本 | Run script
action = {
    "category": "terminal",
    "action_name": "uv",
    "action_args": ["run", "python", "main.py"]
}
obs, _, _, _, _ = env.step(action)
```

## 注意事项 | Notes

1. **命令白名单 | Command Whitelist**
   - 始终使用白名单限制可执行的命令
   - 避免安全风险
   - Always use whitelist to restrict executable commands
   - Avoid security risks

2. **超时设置 | Timeout Settings**
   - 根据命令类型设置合理的超时时间
   - 长时间运行的命令需要更长的超时
   - Set reasonable timeout based on command type
   - Long-running commands need longer timeout

3. **虚拟环境路径 | Virtual Environment Path**
   - 确保虚拟环境激活命令正确
   - 可以使用相对路径或绝对路径
   - Ensure venv activation command is correct
   - Can use relative or absolute paths

4. **错误处理 | Error Handling**
   - 检查 `success` 标志判断命令是否成功
   - 查看 `obs["obs"]` 获取详细输出
   - Check `success` flag to determine if command succeeded
   - Check `obs["obs"]` for detailed output

5. **资源清理 | Resource Cleanup**
   - 使用完毕后调用 `env.close()`
   - 避免资源泄漏
   - Call `env.close()` when done
   - Avoid resource leaks

## 与 TerminalEnv 的对比 | Comparison with TerminalEnv

| 特性 | TerminalEnv | PexpectTerminalEnv |
|------|-------------|-------------------|
| 实现方式 | subprocess.Popen | pexpect.spawn |
| 会话持久性 | ❌ 每个命令独立进程 | ✅ 持久 shell 会话 |
| 虚拟环境支持 | ❌ 难以实现 | ✅ 原生支持 |
| 环境变量保持 | ❌ 不保持 | ✅ 保持 |
| cd 命令 | ❌ 需要特殊处理 | ✅ 原生支持 |
| 交互式命令 | ❌ 不支持 | ✅ 支持(可扩展) |
| 性能 | 稍快(单次命令) | 稍慢(启动开销) |
| 适用场景 | 简单独立命令 | 需要状态保持的场景 |

## 故障排查 | Troubleshooting

### 问题 1: Shell 初始化失败 | Issue 1: Shell Initialization Failed

```python
# 错误: Failed to initialize shell
# 解决: 检查 shell 路径是否正确
env = PexpectTerminalEnv(
    ...,
    shell="/bin/bash"  # 或 /bin/zsh, /bin/sh
)
```

### 问题 2: 虚拟环境未激活 | Issue 2: Virtual Environment Not Activated

```python
# 验证虚拟环境是否激活 | Verify venv activation
which_python = env.get_env_var("VIRTUAL_ENV")
print(f"Virtual env: {which_python}")

# 或执行命令检查 | Or check with command
action = {
    "category": "terminal",
    "action_name": "which",
    "action_args": ["python"]
}
obs, _, _, _, _ = env.step(action)
print(obs["obs"])  # 应该显示虚拟环境中的 python 路径
```

### 问题 3: 命令超时 | Issue 3: Command Timeout

```python
# 增加超时时间 | Increase timeout
args = EnvironmentArguments(
    image_name="local",
    timeout=120  # 增加到 120 秒 | Increase to 120 seconds
)
```

## 总结 | Summary

`PexpectTerminalEnv` 提供了更强大和灵活的终端环境,特别适合需要:
- 虚拟环境管理
- 状态保持
- 复杂命令序列

的场景。

`PexpectTerminalEnv` provides a more powerful and flexible terminal environment, especially suitable for scenarios requiring:
- Virtual environment management
- State persistence
- Complex command sequences
