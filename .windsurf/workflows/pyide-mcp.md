---
description: IDE MCP 封装
---

我们需要将通用 IDE 与 Workspace 能力封装成一个 MCP Server 对外提供服务。

公共 IDE 与 Workspace 代码分别在：@ide4ai/ide.py 与 @ide4ai/environment/workspace/workspace.py

通用工具与服务实现在 @ide4ai/a2c_smcp；仅真正的 Python 特有工具放在 @ide4ai/python_ide/a2c_smcp。

主要封装实现两个大模块：

1. Tools
2. Resource

对于Tools，我们的封装模式如下：

1. 工具所在文件在：ide4ai/a2c_smcp/tools 如果是某个IDE特殊工具，比如Python，会在 @ide4ai/python_ide/a2c_smcp/tools 内封装
2. 实现工具时优先复用 @ide4ai/ide.py、@ide4ai/environment/workspace/workspace.py 与 @ide4ai/environment/terminal/pexpect_terminal_env.py 的方法

---

针对工具的测试需要在：tests/integration/a2c_smcp tests/integration/python_ide/a2c_smcp 及其子目录下进行测试验证。
