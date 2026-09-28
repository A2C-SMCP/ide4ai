# project-code-edit-loop

## 目标

验证 AI Agent 在一个真实 Inspector 会话中完成“创建代码、定位目标、读取上下文、精确修改、再次验证”的日常编辑闭环。

## 前置状态

- 使用 `prepare_run.py --scenario project-code-edit-loop` 新建运行目录。
- `projects.json` 在连接前不存在。
- 项目名为 `uat-code-loop`，根目录为清单的 `workspace_dir`。
- 目标文件为 `<workspace_dir>/app.py`。

## 步骤与断言

### 1. 建立项目

连接 `ide4ai-local`，通过 `project_create` 创建项目并显式刷新 Tools。

断言连接成功，项目工具和 `Write`、`Glob`、`Grep`、`Read`、`Edit` 均可见。保存 `01-code-tools.png`。

### 2. 创建代码

调用 `Write` 创建 `app.py`。内容包含换行，先通过 `Enlarge Content` 在多行编辑器中填写：

```python
def greeting(name: str) -> str:
    # TODO: personalize greeting
    return "hello"


print(greeting("ide4ai"))
```

断言结果 `success` 为 `true`，随后用 `Read` 确认完整内容。保存 `02-created-file.png`。

### 3. 定位目标

- 用 `Glob` 搜索 `**/*.py`，断言结果包含 `app.py`。
- 用 `Grep` 搜索 `TODO`，使用 `content` 输出和行号，断言结果只命中 `app.py` 中的目标注释。

保存 `03-located-code.png`。

### 4. 精确编辑

调用 `Edit`，文件路径使用清单中的绝对路径 `<workspace_dir>/app.py`，把唯一的代码片段：

```python
return "hello"
```

替换为：

```python
return f"hello, {name}"
```

断言 `success` 为 `true` 且 `replacements_made` 为 `1`。再次调用 `Read`，确认工作区中的新逻辑存在且原 return 已消失。`Edit` 更新的是 IDE 工作区模型；本场景不使用基于磁盘搜索的 `Grep` 判断编辑后的内存态。保存 `04-edited-code.png`。

### 5. 验证工作区视图

刷新并读取 IDE Window Resource，断言 URI 以 `window://` 开头，内容属于 `uat-code-loop` 且目录包含 `app.py`。保存 `05-code-window-resource.png`。

## 非目标

本场景不启动 Terminal、不执行代码、不验证 LSP 语义能力，也不覆盖多项目切换。
