# IDE4AI

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**IDE4AI** 是为 AI Agent 打造的代码工作环境，提供代码导航、精确编辑、LSP 支持与终端执行等核心能力，便于集成到各类 Agent 系统中。

## ✨ 特性

- 🔍 **智能代码导航**：LSP 加持的跳转、符号搜索、引用查找
- ✏️ **精确代码编辑**：位置级编辑 + 撤销/重做
- 🔧 **LSP 集成**：Python 等语言的 LSP 能力
- 🖥️ **终端环境**：本地/Docker 命令执行
- 📁 **工作区管理**：文件操作与目录树
- 🤖 **A2C-SMCP/MCP 兼容**：接口清晰，易于自动化编排

## 🎯 设计目标

IDE4AI 的核心设计理念是为 AI Agent 提供一个**高内聚、低耦合**的代码操作环境：

- **高内聚**：编辑、导航、LSP、终端统一接口
- **低耦合**：独立于具体 AI 框架，易于集成
- **Gymnasium 兼容**：实现 Env 接口，可用于强化学习

## 📦 安装（使用者）

### ⚠️ 强制依赖：ripgrep (rg)

IDE4AI 的代码搜索工具基于 rg（ripgrep）。未安装 rg 将导致搜索相关能力不可用。

- macOS: `brew install ripgrep`
- Ubuntu/Debian: `sudo apt-get install ripgrep`
- Fedora/RHEL: `sudo dnf install ripgrep`
- Arch: `sudo pacman -S ripgrep`
- Windows: `choco install ripgrep` 或 `scoop install ripgrep`

更多平台与安装方式：见 ripgrep 官方文档
https://github.com/BurntSushi/ripgrep#installation

### 使用 uv（推荐）

```bash
git clone https://github.com/JQQ/ide4ai.git
cd ide4ai
uv sync
```

### 使用 pip

```bash
pip install ide4ai
```

## 🚀 快速开始（使用者）

### 基础用法（最小示例）

```python
from ide4ai import PythonIDE, IDEAction

ide = PythonIDE(root_dir="/path/to/project", project_name="my_project")

# 打开并编辑
open_file = IDEAction(category="workspace", action_name="open_file", action_args={"uri": "file:///path/to/app.py"})
ide.step(open_file.model_dump())

edit = IDEAction(category="workspace", action_name="edit_file", action_args={"uri": "file:///path/to/app.py", "edits": [{"range": {"start_position": [1, 1], "end_position": [1, 1]}, "text": "# hello\n"}]})
ide.step(edit.model_dump())
```

更多示例（导航、终端执行、LSP 能力）请查看 `examples/` 目录与测试用例 `tests/`。

## 📚 核心概念（使用者）

### IDE Actions

IDE4AI 支持两类操作：

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

## 🛠️ 开发（开发者）

### 环境设置

```bash
uv sync --all-groups  # 安装依赖
poe install-dev       # 可选：开发工具安装
```

### 常用命令（精简）

```bash
poe format       # 格式化
poe lint         # Lint 检查
poe typecheck    # 类型检查
poe test         # 运行测试
```

更多任务请运行 `poe -h` 或查看 `pyproject.toml`。

### 运行测试

```bash
poe test
pytest -k "your_case" -v   # 按需选择
```

### 代码规范

- **Ruff**：linter + formatter
- **MyPy**：静态类型
- **Pytest**：测试框架

提交前建议运行：`poe pre-commit`

## 🏗️ 架构设计（开发者）

整体目录与模块说明请参见项目内文档与源码注释：
- `ide4ai/python_ide/`：Python IDE 实现
- `ide4ai/environment/`：终端与工作区环境
- `ide4ai/dtos/`：LSP 数据模型
- `examples/` 与 `tests/`：使用示例与行为参考

## 🔌 扩展集成（使用者/开发者）

通过工具封装可集成到外部 Agent 系统。示例与最佳实践请参考 `examples/` 与对应扩展源码注释。

## 📖 文档

- API 文档（待完善）
- 架构设计（待完善）
- 扩展开发指南（待完善）
 - 代码搜索与 grep 工具用法：`docs/grep_tool_usage.md`

## 🤝 贡献（开发者）

欢迎贡献！本仓库遵循简单直观的协作流程：

- 提交前：确保通过 `poe format`、`poe lint`、`poe typecheck`、`poe test`
- 提交信息：清晰描述动机与影响（建议英文前缀：feat/fix/docs/chore/test/refactor）
- 变更范围：尽量小步提交，并附带必要测试

### 流程

1. Fork 本仓库
2. 基于 `main` 创建分支：`git checkout -b feat/<topic>`
3. 开发与自测：`poe pre-commit`
4. 提交与推送：`git push origin feat/<topic>`
5. 打开 Pull Request，模板中说明背景、变化、测试与影响面

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

## 🗺️ 路线图（简要）

- [ ] 完善文档与示例
- [ ] 支持更多语言（TypeScript、Java、Go 等）
- [ ] 更多 LSP 能力（重命名、格式化等）
- [ ] 提供 Web UI
- [ ] 性能优化与大仓支持
- [ ] 扩展更多 AI 框架示例

---

**如果这个项目对你有帮助，请给个 ⭐️ Star！**
