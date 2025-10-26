# AI IDE

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AI IDE** 是一个专为 AI Agent 设计的强大 IDE 环境，提供代码导航、编辑、LSP 支持和终端执行等完整功能。

## ✨ 特性

- 🔍 **智能代码导航** - 基于 LSP 的代码跳转、符号搜索和引用查找
- ✏️ **精确代码编辑** - 支持基于位置的精确编辑操作，带完整的撤销/重做功能
- 🔧 **LSP 集成** - 完整的 Language Server Protocol 支持（Python、TypeScript 等）
- 🖥️ **终端环境** - 本地和 Docker 容器内的命令执行
- 📁 **工作区管理** - 文件系统操作、目录树浏览
- 🎯 **为 AI 优化** - 专门设计的接口，方便 AI Agent 理解和操作代码

## 🎯 设计目标

AI IDE 的核心设计理念是为 AI Agent 提供一个**高内聚、低耦合**的代码操作环境：

- **高内聚**：所有 IDE 功能（编辑、导航、LSP、终端）都集中在统一的接口中
- **低耦合**：独立于任何特定的 AI 框架，可以轻松集成到不同的 Agent 系统
- **Gymnasium 兼容**：实现了 Gymnasium Env 接口，可作为强化学习环境使用

## 📦 安装

### 使用 uv（推荐）

```bash
# 克隆仓库
git clone https://github.com/JQQ/ai-ide.git
cd ai-ide

# 安装依赖
uv sync

# 开发模式安装
uv sync --all-extras
```

### 使用 pip

```bash
pip install ai-ide
```

## 🚀 快速开始

### 基础使用

```python
from ai_ide import PythonIDE, IDEAction

# 创建 Python IDE 实例
ide = PythonIDE(
    cmd_white_list=["poetry", "pytest"],
    root_dir="/path/to/your/project",
    project_name="my_project",
    render_with_symbols=True,
    max_active_models=3,
)

# 打开文件
action = IDEAction(
    category="workspace",
    action_name="open_file",
    action_args={"uri": "file:///path/to/file.py"}
)
obs, reward, done, truncated, info = ide.step(action.model_dump())

# 编辑文件
edit_action = IDEAction(
    category="workspace",
    action_name="edit_file",
    action_args={
        "uri": "file:///path/to/file.py",
        "edits": [{
            "range": {
                "start_position": [10, 1],
                "end_position": [10, 1]
            },
            "text": "# New comment\n"
        }]
    }
)
obs, reward, done, truncated, info = ide.step(edit_action.model_dump())

# 执行命令
cmd_action = IDEAction(
    category="terminal",
    action_name="run_command",
    action_args={"command": "pytest tests/"}
)
obs, reward, done, truncated, info = ide.step(cmd_action.model_dump())
```

### 使用单例模式

```python
from ai_ide import PyIDESingleton

# 获取或创建 IDE 实例
ide = PyIDESingleton(
    root_dir="/path/to/project",
    project_name="my_project"
).ide

# 使用 IDE
# ...
```

## 📚 核心概念

### IDE Actions

AI IDE 支持两类操作：

1. **Workspace Actions** - 工作区操作
   - `open_file` - 打开文件
   - `close_file` - 关闭文件
   - `edit_file` - 编辑文件
   - `save_file` - 保存文件
   - `search_files` - 搜索文件
   - `goto_definition` - 跳转到定义
   - `find_references` - 查找引用
   - `list_directory` - 列出目录

2. **Terminal Actions** - 终端操作
   - `run_command` - 执行命令
   - `get_output` - 获取输出

### Workspace 功能

- **TextModel** - 文本模型，提供高效的文本操作
- **LSP 集成** - 完整的语言服务器支持
- **符号导航** - 类、函数、变量的智能导航
- **代码补全** - 基于 LSP 的代码补全

### Terminal 环境

- **LocalTerminalEnv** - 本地终端执行
- **DockerTerminalEnv** - Docker 容器内执行
- 命令白名单机制，确保安全性

## 🛠️ 开发

### 环境设置

```bash
# 安装开发依赖
uv sync

# 或使用 poe 任务
poe install-dev
```

### 常用命令

项目使用 [poethepoet](https://github.com/nat-n/poethepoet) 管理开发任务：

```bash
# 代码检查
poe lint              # 运行 ruff 检查
poe lint-fix          # 自动修复 lint 问题
poe format            # 格式化代码
poe format-check      # 检查代码格式

# 类型检查
poe typecheck         # 运行 mypy 类型检查

# 测试
poe test              # 运行所有测试
poe test-unit         # 仅运行单元测试
poe test-integration  # 仅运行集成测试
poe test-cov          # 运行测试并生成覆盖率报告
poe test-verbose      # 详细模式运行测试

# 组合任务
poe check             # 运行所有检查（lint + format-check + typecheck）
poe fix               # 自动修复问题（lint-fix + format）
poe pre-commit        # 提交前检查（format + lint-fix + typecheck + test）

# 清理
poe clean             # 清理缓存和临时文件
poe clean-pyc         # 清理 Python 缓存
poe clean-cov         # 清理覆盖率报告
```

### 运行测试

```bash
# 运行所有测试
poe test

# 运行特定测试
pytest tests/test_workspace.py -v

# 生成覆盖率报告
poe test-cov
```

### 代码规范

项目使用以下工具确保代码质量：

- **Ruff** - 快速的 Python linter 和 formatter
- **MyPy** - 静态类型检查
- **Pytest** - 测试框架

提交代码前请运行：

```bash
poe pre-commit
```

## 🏗️ 架构设计

```
ai_ide/
├── base.py                 # IDE 基类
├── schema.py              # 数据模型定义
├── exceptions.py          # 异常类
├── ides.py               # IDE 单例管理
├── utils.py              # 工具函数
├── dtos/                 # LSP 数据传输对象
│   ├── base_protocol.py
│   ├── commands.py
│   ├── file_resource.py
│   ├── text_documents.py
│   └── workspace_edit.py
├── environment/          # 环境实现
│   ├── terminal/        # 终端环境
│   │   ├── base.py
│   │   ├── local_terminal_env.py
│   │   └── docker_terminal_env.py
│   └── workspace/       # 工作区
│       ├── base.py
│       ├── model.py     # 文本模型
│       ├── schema.py    # 工作区数据模型
│       └── utils.py
├── python_ide/          # Python IDE 实现
│   ├── ide.py
│   ├── workspace.py     # Python 工作区（LSP 集成）
│   └── const.py
└── extensions/          # 可选扩展
    ├── tfrobot_tool.py  # TFRobot 集成（需要单独安装 tfrobot）
    └── tfrobot_claude_tool.py
```

## 🔌 扩展集成

AI IDE 提供了扩展机制，可以轻松集成到不同的 AI 框架中。

### TFRobot 集成示例

```python
# 需要先安装 tfrobot
# pip install tfrobot

from ai_ide.extensions.tfrobot_tool import IDETool

tool = IDETool(
    root_dir="/path/to/project",
    project_name="my_project"
)

# 在 TFRobot 中使用
# ...
```

## 📖 文档

- [API 文档](docs/api.md)（待完善）
- [架构设计](docs/architecture.md)（待完善）
- [扩展开发指南](docs/extensions.md)（待完善）

## 🤝 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md)（待创建）了解详情。

### 贡献流程

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- 基于 [Gymnasium](https://gymnasium.farama.org/) 环境接口
- LSP 协议支持基于 [Language Server Protocol](https://microsoft.github.io/language-server-protocol/)
- 灵感来源于 [SWE-agent](https://github.com/princeton-nlp/SWE-agent) 和其他 AI 代码编辑项目

## 📮 联系方式

- 作者：JQQ
- Email：jqq1716@gmail.com
- GitHub：[@JQQ](https://github.com/JQQ)

## 🗺️ 路线图

- [ ] 完善文档和示例
- [ ] 支持更多编程语言（TypeScript、Java、Go 等）
- [ ] 添加更多 LSP 功能（重命名、代码格式化等）
- [ ] 提供 Web UI 界面
- [ ] 性能优化和大型项目支持
- [ ] 更多 AI 框架集成示例

---

**如果这个项目对你有帮助，请给个 ⭐️ Star！**
