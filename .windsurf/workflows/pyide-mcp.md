---
description: Python IDE MCP 封装
---

我们需要将PythonIDE的相关能力封装成一个MCP Server对外提供服务。

PythonIDE相关代码在： @ide4ai/python_ide 下

我们需要在 @ide4ai/a2c_smcp （基类与基础结构定义） 与 @ide4ai/python_ide/a2c_smcp （Python的特化定义）下展开封装

主要封装实现两个大模块：

1. Tools
2. Resource

对于Tools，我们的封装模式如下：

1. 工具所在文件在：ide4ai/a2c_smcp/tools 如果是某个IDE特殊工具，比如Python，会在 @ide4ai/python_ide/a2c_smcp/tools 内封装
2. 实现工具时使用的能力尽可能从 @ide4ai/python_ide/ide.py + @ide4ai/python_ide/workspace.py + @ide4ai/environment/terminal/pexpect_terminal_env.py 及其父类的方法来实现

---

针对工具的测试需要在：tests/integration/a2c_smcp tests/integration/python_ide/a2c_smcp 及其子目录下进行测试验证。