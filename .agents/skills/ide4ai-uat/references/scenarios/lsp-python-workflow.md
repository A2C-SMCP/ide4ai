# lsp-python-workflow

## 目标

验证 Python 项目的 LSP 配置能够通过项目注册持久表达，并可从 Inspector 查询和显式重载。

## 前置状态

- 使用 `prepare_run.py --scenario lsp-python-workflow` 新建运行目录。
- 前置检查必须确认 `pyright-langserver` 可执行；缺失时结果为 `BLOCKED`，不得改用假服务冒充验收。
- 项目名为 `uat-python-lsp`，根目录为 `workspace_dir`。

## 步骤与断言

### 1. 创建显式 Python 项目

通过 `project_create` 提交：

```json
{
  "name": "uat-python-lsp",
  "root_dir": "<manifest.workspace_dir>",
  "lsp": {
    "mode": "explicit",
    "language_id": "python"
  }
}
```

断言创建成功，返回配置保持 `explicit` 和 `python`。刷新 Tools 后确认 `Lsp` 可见。保存 `01-python-project.png`。

### 2. 创建 Python 文件

用 `Write` 创建 `<workspace_dir>/main.py`；先通过 `Enlarge Content` 在多行编辑器中填写：

```python
def answer() -> int:
    return 42
```

断言写入成功。保存 `02-python-file.png`。

### 3. 查询 LSP 状态

调用 `Lsp`，参数 `action` 为 `status`。

断言没有 MCP error，`language_id` 为 `python`，`state` 为 `ready` 或 `running`，且没有不可用原因。保存 `03-lsp-status.png`。

### 4. 显式重载

调用 `Lsp`，参数 `action` 为 `reload`，然后再次调用 `status`。

断言重载结果的语言仍为 `python`，状态为 `ready` 或 `running`；再次查询不会变为 `unavailable`。保存 `04-lsp-reloaded.png`。

### 5. 验证配置可见性

调用 `project_list`，断言项目的 LSP 配置仍为显式 Python，当前项目未变化。保存 `05-lsp-project-state.png`。

## 非目标

本场景不验证补全、跳转、诊断内容、LSP 崩溃自恢复、其他语言或自定义 Server 命令。
