# filename: workspace.py
# @Time    : 2024/4/30 17:08
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import datetime
import json
import os
import subprocess
from collections.abc import Callable, Sequence
from typing import Any, SupportsFloat

from pydantic import AnyUrl, ValidationError

from ai_ide.dtos.base_protocol import LSPResponseMessage
from ai_ide.dtos.workspace_edit import LSPWorkspaceEdit
from ai_ide.environment.workspace.base import BaseWorkspace
from ai_ide.environment.workspace.model import TextModel
from ai_ide.environment.workspace.schema import (
    Position,
    Range,
    SearchResult,
    SingleEditOperation,
    TextEdit,
)
from ai_ide.exceptions import IDEExecutionError
from ai_ide.python_ide.const import (
    DEFAULT_CAPABILITY,
    DEFAULT_SYMBOL_VALUE_SET,
)
from ai_ide.schema import (
    LSP_ACTIONS,
    TEXT_DOCUMENT_ACTIONS,
    WORKSPACE_ACTIONS,
    IDEAction,
    IDEObs,
    LanguageId,
)
from ai_ide.utils import list_directory_tree, render_symbols


def default_python_header_generator(workspace: BaseWorkspace, file_path: str) -> str:
    """
    默认的Python文件头生成器

    Args:
        workspace (BaseWorkspace): 工作环境
        file_path (str): 文件路径

    Returns:
        str: 文件头
    """
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    return (
        f"# -*- coding: utf-8 -*-\n"
        f"# filename : {os.path.basename(file_path)}\n"
        f"# @Time    : {now.strftime('%Y/%m/%d %H:%M')}\n"
        f"# @Author  : TuringFocus\n"
        f"# @Email   : support@turingfocus.com\n"
        f"# @Software: {workspace.project_name}\n"
    )


class PyWorkspace(BaseWorkspace):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.header_generators is None:
            self.header_generators: dict[str, Callable[[BaseWorkspace, str], str]] = {
                ".py": default_python_header_generator,
            }

    def _launch_lsp(self) -> subprocess.Popen:
        """
        启动 Pyright 语言服务器

        注意启动时需要使用Bytes模式，而不是Str模式，即text设置为False。因为LSP协议长度计算是按bytes来计算的。

        Returns:
            subprocess.Popen: Pyright 语言服务器进程 | Pyright language server process
        """
        # 启动 Pyright 语言服务器
        process = subprocess.Popen(
            ["pyright-langserver", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=False,
        )
        return process

    def _initial_lsp(self) -> None:
        """
        初始化 LSP 服务

        Returns:

        """
        msg_id = self.get_lsp_msg_id()
        res = self.send_lsp_msg(
            "initialize",
            {
                "processId": None,
                "workspaceFolders": [
                    {
                        "uri": f"file://{self.root_dir}",
                        "name": self.project_name,
                    },
                ],
                # TODO 参考：https://czq2u5hs17.feishu.cn/docx/HLPLdDMJUoKwdRx6f6wc3kh0nCg?from=from_copylink 这其中文章后最面的TODO进行实现
                "initializationOptions": {
                    "disablePullDiagnostics": True,
                },
                "capabilities": DEFAULT_CAPABILITY,
            },
            message_id=msg_id,
        )
        if res:
            try:
                res_json = LSPResponseMessage.model_validate(json.loads(res))
            except json.JSONDecodeError as e:  # pragma: no cover
                raise ValueError(f"初始化LSP服务失败，返回结果无法解析为json: {res}") from e  # pragma: no cover
            if res_json.error:
                raise ValueError(f"初始化LSP服务失败: {res_json.error}")  # pragma: no cover
            self.send_lsp_msg("initialized")

    def construct_action(self, action: dict) -> IDEAction:
        """
        构建 IDEAction 对象

        Args:
            action (dict): 动作字典 | Action dictionary

        Returns:
            IDEAction: IDEAction 对象 | IDEAction object

        Raises:
            ValueError: 如果动作类别为 "terminal" | If the action category is "terminal"
            ValueError: 如果动作不在支持的动作集合中 | If the action is not in the supported action set
        """
        ide_action = IDEAction.model_validate(action)
        match ide_action.category:
            case "terminal":
                raise ValueError("Workspace不支持terminal的动作类别")
            case "workspace":
                if ide_action.action_name not in WORKSPACE_ACTIONS | TEXT_DOCUMENT_ACTIONS | LSP_ACTIONS:
                    raise ValueError(f"Workspace不支持 {ide_action.action_name} 动作")
                return ide_action
            case _:
                raise ValueError(f"不支持的动作类别 {ide_action.category}")  # pragma: no cover

    def step(self, action: dict) -> tuple[dict, SupportsFloat, bool, bool, dict[str, Any]]:
        """
        执行一个动作

        观察返回：
        1. OpenFile: 返回打开文件的内容
        2. ApplyEdit: 返回编辑的变更记录

        奖励机制：
        1. OpenFile: 成功打印返回100，打开失败返回0
        2. ApplyEdit: 变更成功返回100，失败返回0  TODO 后续需要有更细致的评估方法来评估编辑的质量

        Args:
            action (dict): 动作字典 | Action dictionary

        Returns:
            tuple[dict, SupportsFloat, bool, bool, dict[str, Any]]: 观察、奖励、是否结束、是否成功、额外信息 |
                Observation, Reward, Done, Success, Extra info
        """
        self._assert_not_closed()
        ide_action = self.construct_action(action)
        match ide_action.action_name:
            case "open_file":
                try:
                    if isinstance(ide_action.action_args, dict):
                        text_model = self.open_file(**ide_action.action_args)
                    elif isinstance(ide_action.action_args, str):
                        text_model = self.open_file(uri=ide_action.action_args)
                    else:
                        raise ValueError("open_file 动作参数错误")
                    file_content = text_model.get_simple_view() if self._enable_simple_view_mode else text_model.get_view()
                    return (
                        IDEObs(obs=file_content).model_dump(),
                        100,
                        True,
                        True,
                        {},
                    )
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "apply_edit":
                try:
                    if isinstance(ide_action.action_args, dict):
                        res = self.apply_edit(**ide_action.action_args)
                        # 成功编辑后，读取编辑位置附近的代码并返回，给LLM一个反馈
                        content_after_edit: list[str] = []
                        content_ranges: list[Range] = []
                        for r in ide_action.action_args.get("edits", []):
                            if isinstance(r, dict):
                                edit = SingleEditOperation.model_validate(r)
                                length_of_new_text = len(edit.text.splitlines()) if edit.text else 0
                                range_start_line = edit.range.start_position.line
                                range_end_line = edit.range.end_position.line
                                content_ranges.append(
                                    Range(
                                        start_position=Position(max(1, range_start_line - 3), 1),
                                        end_position=Position(range_end_line + length_of_new_text + 3, 1),
                                    ),
                                )
                        # 对content_ranges进行合并。有交集的合并，无交集独立
                        content_ranges.sort(key=lambda x: x.start_position.line)
                        merged_ranges: list[Range] = []
                        for r in content_ranges:
                            if not merged_ranges:
                                merged_ranges.append(r)
                            else:
                                last_range = merged_ranges[-1]
                                if last_range & r:
                                    last_range |= r
                                else:
                                    merged_ranges.append(r)
                        if merged_ranges:
                            # TODO 这里的展示效果不好，原因是model.get_view不允许传入多个Range，仅允许单个Range，
                            #  这导致文本渲染会有大量重复。mode.get_view需要支持多Range模式
                            content_after_edit.append(
                                self.read_file(
                                    uri=ide_action.action_args["uri"],
                                    with_line_num=True,
                                    code_range=merged_ranges[-1],
                                ),
                            )
                        apply_result: str = (
                            "编辑成功。如果有回滚需求，可以按下面的回滚操作执行。" + "\n".join([repr(e) for e in res]) if res else ""
                        )
                        if content_after_edit:
                            apply_result += "\n编辑后的代码如下（仅返回编辑位置附近的代码。如果想看全部，可以使用read_file工具查看）:\n"
                            apply_result += "\n".join(content_after_edit)
                        return IDEObs(obs=apply_result, original_result=res).model_dump(), 100, True, True, {}
                    else:
                        raise ValueError("apply_edit 动作参数错误")
                except IDEExecutionError as e:
                    raise e
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "save_file":
                try:
                    if isinstance(ide_action.action_args, dict):
                        self.save_file(**ide_action.action_args)
                    elif isinstance(ide_action.action_args, str):
                        self.save_file(uri=ide_action.action_args)
                    else:
                        raise ValueError("save_file 动作参数错误")
                    return IDEObs(obs="保存成功").model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "close_file":
                try:
                    if isinstance(ide_action.action_args, dict):
                        self.close_file(**ide_action.action_args)
                    elif isinstance(ide_action.action_args, str):
                        self.close_file(uri=ide_action.action_args)
                    else:
                        raise ValueError("close_file 动作参数错误")
                    return IDEObs(obs="关闭成功").model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "read_file":
                try:
                    if isinstance(ide_action.action_args, dict):
                        # 构建调用参数
                        if ide_action.action_args.get("code_range"):
                            ide_action.action_args["code_range"] = Range.model_validate(
                                ide_action.action_args["code_range"],
                            )
                        text = self.read_file(**ide_action.action_args)
                    elif isinstance(ide_action.action_args, str):
                        text = self.read_file(uri=ide_action.action_args)
                    else:
                        raise ValueError("read_file 动作参数错误")
                    return IDEObs(obs=text).model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "get_file_symbols":
                try:
                    if isinstance(ide_action.action_args, dict):
                        symbols = self.get_file_symbols(**ide_action.action_args)
                    else:
                        raise ValueError("get_file_symbols 动作参数错误")
                    return IDEObs(obs=symbols).model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "find_in_file":
                try:
                    if isinstance(ide_action.action_args, dict):
                        if ide_action.action_args.get("search_scope"):
                            if isinstance(ide_action.action_args["search_scope"], dict):
                                ide_action.action_args["search_scope"] = Range.model_validate(
                                    ide_action.action_args["search_scope"],
                                )
                            elif isinstance(ide_action.action_args["search_scope"], list):
                                ide_action.action_args["search_scope"] = [
                                    Range.model_validate(r) for r in ide_action.action_args["search_scope"]
                                ]
                        search_res = self.find_in_file(**ide_action.action_args)
                    else:
                        raise ValueError("find_in_file 动作参数错误")
                    return (
                        IDEObs(obs="\n".join([repr(r) for r in search_res])).model_dump(),
                        100,
                        True,
                        True,
                        {},
                    )
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "replace_in_file":
                try:
                    if isinstance(ide_action.action_args, dict):
                        if ide_action.action_args.get("search_scope"):
                            if isinstance(ide_action.action_args["search_scope"], dict):
                                ide_action.action_args["search_scope"] = Range.model_validate(
                                    ide_action.action_args["search_scope"],
                                )
                            elif isinstance(ide_action.action_args["search_scope"], list):
                                ide_action.action_args["search_scope"] = [
                                    Range.model_validate(r) for r in ide_action.action_args["search_scope"]
                                ]
                        replace_res = self.replace_in_file(**ide_action.action_args)
                    else:
                        raise ValueError("replace_in_file 动作参数错误")
                    return (
                        IDEObs(obs="完成替换", original_result=replace_res).model_dump(),
                        100,
                        True,
                        True,
                        {},
                    )
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "create_file":
                try:
                    if isinstance(ide_action.action_args, dict):
                        create_model = self.create_file(**ide_action.action_args)
                    elif isinstance(ide_action.action_args, str):
                        create_model = self.create_file(uri=ide_action.action_args)
                    else:
                        raise ValueError("create_file 动作参数错误")
                    if create_model:
                        return (
                            IDEObs(
                                obs="文件创建成功。\n当前文件内容如下(IDE会自动初始化部分内容):\n"
                                f"{self.read_file(uri=str(create_model.uri), with_line_num=True)}\n"
                                if create_model.get_value()
                                else "文件创建成功",
                            ).model_dump(),
                            100,
                            True,
                            True,
                            {},
                        )
                    else:
                        return IDEObs(obs="文件已存在").model_dump(), 0, True, False, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "insert_cursor":
                try:
                    if isinstance(ide_action.action_args, dict):
                        insert_res = self.insert_cursor(**ide_action.action_args)
                    else:
                        raise ValueError("insert_cursor 动作参数错误")
                    return IDEObs(obs=insert_res).model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "delete_cursor":
                try:
                    if isinstance(ide_action.action_args, dict):
                        delete_res = self.delete_cursor(**ide_action.action_args)
                    else:
                        raise ValueError("delete_cursor 动作参数错误")
                    return IDEObs(obs=delete_res).model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "clear_cursors":
                try:
                    if isinstance(ide_action.action_args, dict):
                        clear_res = self.clear_cursors(**ide_action.action_args)
                    else:
                        raise ValueError("clear_cursors 动作参数错误")
                    return IDEObs(obs=clear_res).model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case "inspect_grammar_err":
                try:
                    if isinstance(ide_action.action_args, dict):
                        inspect_res = self.inspect_grammar_err(**ide_action.action_args)
                    else:
                        raise ValueError("inspect_grammar_err 动作参数错误")
                    return IDEObs(obs=inspect_res).model_dump(), 100, True, True, {}
                except Exception as e:
                    return IDEObs(obs=str(e)).model_dump(), 0, True, False, {}
            case (
                "get_definition_and_implementation"
                | "hover"
                | "find_in_workspace"
                | "replace_in_workspace"
                | "create_files"
                | "delete_files"
                | "rename_file"
                | "delete_file"
            ):
                raise NotImplementedError(f"Action: {ide_action.action_name} 尚未实现")
            case _:
                raise ValueError(f"不支持的动作 {ide_action.action_name}")  # pragma: no cover

    def render(self) -> str:  # type: ignore
        """
        渲染当前工作区状态，主要提取active_models相关信息，最后一个active_models取其view全部内容，之前的active_models取其symbols信息

        Returns:
            str: 以字符串的形式来返回渲染结果
        """
        self._assert_not_closed()
        dir_info = list_directory_tree(self.root_dir, include_dirs=self.expand_folders, recursive=True, indent="- ")
        view = f"当前工作区: {self.project_name}\n\n{dir_info}\n"
        active_models_count = len(self.active_models)
        if active_models_count > 1:
            view += "\n以下是最近使用的文件其结构信息与关键Symbols信息。每个结构跟随一个Range范围，可以使用这个Range+URI查询代码详情:\n"
            for active_view in self.active_models[:-1]:
                uri = active_view.uri
                view += f"文件URI: {uri}\n"
                mid = self.get_lsp_msg_id()
                lsp_res = self.send_lsp_msg(
                    "textDocument/documentSymbol",
                    {"textDocument": {"uri": str(uri)}},
                    message_id=mid,
                )
                if lsp_res:
                    res_model = LSPResponseMessage.model_validate(json.loads(lsp_res))
                    if res_model.error:
                        view += f"获取Symbols信息失败: {res_model.error}\n"  # pragma: no cover
                        continue  # pragma: no cover
                    symbols = res_model.result
                    view += render_symbols(symbols, DEFAULT_SYMBOL_VALUE_SET)  # type: ignore
                    view += "\n"
                else:
                    view += "无法获取Symbols信息\n"  # pragma: no cover
        if active_models_count > 0:
            view += f"当前打开的文件内容如下：\n{self.active_models[-1].get_view()}\n"
        return view

    def open_file(self, *, uri: str) -> TextModel:
        """
        Open a file in the workspace.
        Initial a model instance, add it to self.models and active it

        Args:
            uri (str): The path to the file to be opened.

        Returns:
            TextModel: The model instance representing the opened file.
        """
        self._assert_not_closed()
        if tm := next(filter(lambda model: model.uri == AnyUrl(uri), self.models), None):
            self.active_model(tm.m_id)  # pragma: no cover
            return tm  # pragma: no cover
        text_model = TextModel(language_id=LanguageId.python, uri=AnyUrl(uri))
        self.models.append(text_model)
        self.active_model(text_model.m_id)
        self.send_lsp_msg(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": LanguageId.python.value,
                    "version": text_model.get_version_id(),
                    "text": text_model.get_value(),
                },
            },
        )
        return text_model

    def apply_edit(
        self,
        *,
        uri: str,
        edits: Sequence[SingleEditOperation | dict],
        compute_undo_edits: bool = False,
    ) -> list[TextEdit] | None:
        """
        Apply edits to a file in the workspace.

        Notes:
            注意这个函数不支持 "-1" 形式的Range调用，即不能用负数表示倒数。如果想实现需要在外侧完成转换后再传入。

        Args:
            uri (str): The URI of the file to which the edits should be applied.
            edits (list[SingleEditOperation | dict]): The edits to be applied to the file.
            compute_undo_edits (bool): Whether to compute the undo edits. This parameter is optional and defaults to
                False.

        Returns:
            Optional[list[TextEdit]]: The reverse edits that can be applied to undo the changes.
        """
        self._assert_not_closed()
        text_model = next(filter(lambda model: model.uri == AnyUrl(uri), self.models), None)
        if not text_model:
            text_model = self.open_file(uri=uri)  # pragma: no cover
        try:
            model_edits = [SingleEditOperation.model_validate(edit) if isinstance(edit, dict) else edit for edit in edits]
        except ValidationError as e:
            err_info = (
                f"编辑操作参数错误，具体报错如下:\n{e}\n这类错误经常由Range范围引起，在当前工作区内Range与Position均是1-based。"
                f"不要使用0基索引"
            )
            raise IDEExecutionError(message=err_info, detail_for_llm=err_info) from e
        res = text_model.apply_edits(model_edits, compute_undo_edits)

        self.send_lsp_msg(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": text_model.get_version_id()},
                "contentChanges": [{"range": edit.range.to_lsp_range().model_dump(), "text": edit.text} for edit in model_edits],
            },
        )
        return res

    def rename_file(
        self,
        *,
        old_uri: str,
        new_uri: str,
        overwrite: bool | None = None,
        ignore_if_exists: bool | None = None,
    ) -> bool:
        """
        # TODO 需要与LSP进行信息互通查询到相应的引用关系后，将引用关系变更后，再进行文件重命名。这个过程涉及到LSP互通与异常回滚。目前未实现
        Rename a file.

        Args:
            old_uri:
            new_uri:
            overwrite:
            ignore_if_exists:

        Returns:
            bool: True if the file is successfully renamed, False otherwise.
        """
        raise NotImplementedError(
            "rename_file 需要与LSP进行信息互通查询到相应的引用关系后，将引用关系变更后，再进行文件重命名。这个过程涉及到LSP互通与异常回滚。"
            "目前暂未实现。你可以提示用户使用PyCharm等工具手动重命名文件。",
        )

    def delete_file(
        self,
        *,
        uri: str,
        recursive: bool | None = None,
        ignore_if_not_exists: bool | None = None,
    ) -> bool:
        """
        Deletes a file from the specified URI.

        Args:
            uri: The URI of the file to be deleted.
            recursive: Optional. If set to True, deletes the file recursively along with any directories. If set to
                False, only deletes the file.
            ignore_if_not_exists: Optional. If set to True, no error will be raised if the file does not exist. If set
                to False, an error will be raised if the file does not exist.

        Returns:
            bool: True if the file is successfully deleted, False otherwise.

        Raises:
            NotImplementedError: This method is not implemented yet. It requires communication with LSP to update the
                reference relationships before renaming the file. This process involves LSP communication and exception
                rollback. Currently, it is not implemented. You can suggest the user to manually delete the file using
                tools like PyCharm.

        Example:
            delete_file(uri='/path/to/file.txt')
        """
        # TODO 需要与LSP进行信息互通查询到相应的引用关系后，将引用关系变更后，再进行文件重命名。这个过程涉及到LSP互通与异常回滚。目前未实现
        raise NotImplementedError(
            "delete_file 需要与LSP进行信息互通查询到相应的引用关系后，将引用关系变更后，再进行文件重命名。这个过程涉及到LSP互通与异常回滚。"
            "目前暂未实现。你可以提示用户使用PyCharm等工具手动删除文件。",
        )

    def create_file(
        self,
        *,
        uri: str,
        init_content: str | None = None,
        overwrite: bool | None = None,
        ignore_if_exists: bool | None = None,
    ) -> TextModel | None:
        """
        Create a file at the specified URI.

        Args:
            uri (str): The path where the file will be created.
            init_content (str, optional): The initial content of the file. Defaults to None.
            overwrite (bool, optional): If True, overwrite the file if it exists. Defaults to None.
            ignore_if_exists (bool, optional): If True, do nothing if the file already exists. Defaults to None.

        Returns:
            Optional[TextModel]: The model instance representing the created file.
        """
        self._assert_not_closed()
        if not uri.startswith("file://"):
            uri = f"file://{uri}"  # pragma: no cover
        file_path = uri[7:]

        # Check if the file already exists
        if os.path.exists(file_path):
            if ignore_if_exists:
                return None  # Do nothing as the file exists and we should ignore this situation
            if not overwrite:
                raise FileExistsError(f"The file at {file_path} already exists and overwrite is not set to True.")
            # Overwrite is True, delete the file before creating a new one
            os.remove(file_path)
        # Pyright 目前好像不支持 workspace/willCreateFiles 方法
        # msg_id = self.get_lsp_msg_id()
        # lsp_res_will_create = self.send_lsp_msg("workspace/willCreateFiles", {"files": [{"uri": uri}]}, msg_id)
        # if not lsp_res_will_create:
        #     raise ValueError(f"无法创建文件: {uri}， LSP校验未通过")
        # lsp_res = LSPResponseMessage.model_validate(json.loads(lsp_res_will_create))
        # if lsp_res.error:
        #     raise ValueError(f"无法创建文件: {uri}， LSP校验未通过: {lsp_res.error}")
        # TODO LSP会响应 workspace/willCreateFiles Request，返回的结构中会包括一个workspaceEdit。 \
        #  完成apply_workspace方法的封装后，需要在此调用并响应
        # Create the file
        try:
            # Using 'x' mode to create file will raise an error if the file already exists
            with open(file_path, "x") as file:
                for file_type, header_generator in self.header_generators.items():
                    if file_path.endswith(file_type):
                        header = header_generator(self, file_path)
                        file.write(header)
                        break
            tm = TextModel(language_id=LanguageId.python, uri=AnyUrl(uri))
            # 在文件创建后追加初始化内容（如果存在）
            if init_content:
                tm.apply_edits(
                    [
                        SingleEditOperation(
                            range=Range(
                                start_position=Position(
                                    tm.get_line_count(),
                                    tm.get_line_length(tm.get_line_count()) + 1,
                                ),
                                end_position=Position(tm.get_line_count(), tm.get_line_length(tm.get_line_count()) + 1),
                            ),
                            text=("\n" + init_content) if tm.get_line_count() > 1 else init_content,
                        ),
                    ],
                )
            self.models.append(tm)
            self.active_model(tm.m_id)
            self.send_lsp_msg("workspace/didCreateFiles", {"files": [{"uri": uri}]})
            return tm
        except FileExistsError:
            # If overwrite was True, we already deleted the file, so this should not happen
            return None  # pragma: no cover
        except Exception as e:
            # Handle other possible exceptions, such as permission errors
            raise OSError(f"Failed to create file at {uri}: {str(e)}") from e

    def find_in_file(
        self,
        *,
        uri: str,
        query: str,
        search_scope: Range | list[Range] | None = None,
        is_regex: bool = False,
        match_case: bool = False,
        word_separator: str | None = None,
        capture_matches: bool = True,
        limit_result_count: int | None = None,
    ) -> list[SearchResult]:
        """
        Find a query in a file in the workspace.

        Args:
            uri (str): The URI of the file to search in. | 要搜索的文件的 URI。
            query (str): The query to search for. | 要搜索的查询。
            search_scope: Optional. The range or list of ranges where the search should be performed. If not provided,
                the search will be performed in the full model range. | 可选。指定搜索应在其中进行的范围或范围列表。如果未提供，
                则在整个模型范围内进行搜索。
            is_regex: Optional. Specifies whether the search string should be treated as a regular expression. Default
                is False. | 可选。指定是否应将搜索字符串视为正则表达式。默认为 False。
            match_case: Optional. Specifies whether the search should be case-sensitive. Default is False. | 可选。指定搜
                索是否应区分大小写。默认为 False。
            word_separator: Optional. The separator used to define word boundaries in the search. If not provided, all
                characters are considered as part of a word. | 可选。用于定义搜索中单词边界的分隔符。如果未提供，则所有字符都视为
                单词的一部分。
            capture_matches: Optional. Specifies whether the matched ranges should be captured in the search results.
                Default is False. | 可选。指定是否应在搜索结果中捕获匹配的范围。默认为 False。
            limit_result_count: Optional. The maximum number of search results to return. If not provided, all matches
                will be returned. | 可选。返回的搜索结果的最大数量。如果未提供，将返回所有匹配项。

        Returns:
            A list of Range objects representing the matched ranges. | 表示匹配范围的 Range 对象列表。

        Raises:
            ValueError: If an invalid search scope is provided. | 如果提供了无效的搜索范围。

        """
        text_model = self.get_model(uri)
        if not text_model:
            text_model = TextModel(language_id=LanguageId.python, uri=AnyUrl(uri))
        return text_model.find_matches(
            query,
            search_scope,
            is_regex,
            match_case,
            word_separator,
            capture_matches,
            limit_result_count,
        )

    def apply_workspace_edit(self, *, workspace_edit: LSPWorkspaceEdit) -> Any:
        # TODO 需要实现 apply_workspace_edit 方法
        raise NotImplementedError("apply_workspace_edit 尚未实现")
