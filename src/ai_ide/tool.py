# -*- coding: utf-8 -*-
# filename: tool.py
# @Time    : 2024/5/13 14:52
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import copy
from typing import Any, ClassVar, NamedTuple, Optional, cast

import overrides
from cachetools import LRUCache, cachedmethod
from cachetools.keys import hashkey
from pydantic import BaseModel, Field, GetJsonSchemaHandler, PrivateAttr, TypeAdapter, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema as cs
from typing_extensions import Self

from tfrobot.brain.chain.llms.chat_llm import ChatLLM
from tfrobot.drive.tool.base import BaseTool
from ai_ide.environment.workspace.model import TextModel
from ai_ide.environment.workspace.schema import Position, Range, SingleEditOperation
from ai_ide.ides import PyIDESingleton
from ai_ide.python_ide.ide import PythonIDE
from ai_ide.schema import IDEAction
from tfrobot.registry.utils import generate_register_name
from tfrobot.schema.drive.tool.base import MessageMeta, ToolReturn
from ai_ide.exceptions import IDEExecutionError

CMD_WHITE_LIST: list[str] = ["poetry"]


def convert_edit_range_to_range(edit_range: dict | BaseModel, model: TextModel) -> Range:
    """
    Convert an edit range to a range.

    Edit range can include -1 to represent the end of the file. This function converts the negative indices to positive

    Args:
        edit_range (dict | BaseModel): The edit range to be converted.
        model (TextModel): The model to which the edit range belongs.

    Returns:
        Range: The converted range.
    """

    def adjust_line(sl: int, lc: int) -> int:
        if sl == 0:
            raise IDEExecutionError(message="编辑操作参数错误", detail_for_llm="编辑操作参数错误，Range范围不允许使用0基索引，请改用1-based")
        if abs(sl) > lc:
            raise IDEExecutionError(
                message="编辑操作参数错误",
                detail_for_llm=f"编辑操作参数错误，Range起始行数超出文件行数，当前文件行数为:{lc}。"
                f"这种情况一般出现在想在文件最后追加内容的场景下，一般解决方法是向追加的text前添加一个'\\n'换行符。然后插入位置改为({sl - 1}, -1),即在上一行的行尾追加。",
            )
        return sl if sl > 0 else lc + sl + 1

    def adjust_char(sc: int, al: int) -> int:
        if sc == 0:
            raise IDEExecutionError(message="编辑操作参数错误", detail_for_llm="编辑操作参数错误，Position范围不允许使用0基索引，请改用1-based")
        sll = model.get_line_length(al)
        if abs(sc) > sll + 1:
            raise IDEExecutionError(
                message="编辑操作参数错误",
                detail_for_llm=f"编辑操作参数错误，Position起始列数超出行长度。第{sc}长度为:{sll}",
            )
        return sc if sc > 0 else sll + sc + 2

    if isinstance(edit_range, BaseModel):
        edit_range = edit_range.model_dump()
    line_count = model.get_line_count()
    # 校验与设置开始行
    start_line: int = edit_range["start_position"][0]
    start_line = adjust_line(start_line, line_count)
    # 校验与设置开始列
    star_character: int = edit_range["start_position"][1]
    star_character = adjust_char(star_character, start_line)
    # 校验与设置结束行
    end_line: int = edit_range["end_position"][0]
    end_line = adjust_line(end_line, line_count)
    # 校验与设置结束列
    end_character: int = edit_range["end_position"][1]
    end_character = adjust_char(end_character, end_line)
    start_position = Position(line=start_line, character=star_character)
    valid_start_pos = model.validate_position(start_position)
    if start_position != valid_start_pos:
        raise IDEExecutionError(
            message="编辑操作参数错误",
            detail_for_llm=f"编辑操作参数错误，start_position是个非法位置。距离它最近的合法位置是:{valid_start_pos}。你可以考虑基于此位置，重新修改一下你的编辑内容",
        )
    end_position = Position(line=end_line, character=end_character)
    valid_end_pos = model.validate_position(end_position)
    if end_position != valid_end_pos:
        raise IDEExecutionError(
            message="编辑操作参数错误",
            detail_for_llm=f"编辑操作参数错误，end_position是个非法位置。距离它最近的合法位置是:{valid_end_pos}。你可以考虑基于此位置，重新修改一下你的编辑内容",
        )
    return Range(
        start_position=valid_start_pos,
        end_position=valid_end_pos,
    )


def construct_single_edit_operation(edit: dict, model: TextModel) -> SingleEditOperation:
    """
    通过字典信息构建SingleEditOperation，因为字典参数中Range有可能允许以负数表示倒序，所以需要结合model进行转换

    因为Range范围是1-based，所以需要将负数转换为正数，同时需要校验Range范围是否合法。

    Args:
        edit (dict): 编辑操作的字典信息。注意这个字典的结构取决于：file://tfrobotv2/drive/tool/ides/tool.py 这里的ApplyEditParameters定义
        model (TextModel): 编辑操作的model

    Returns:
        SingleEditOperation: 编辑操作对象

    Raises:
        IDEExecutionError: 如果非整行替换，会抛出异常。目前通过实践发现，如果让LLM自行决定替换范围，它经常会数错列数，导致替换失败。我们利用其特点对操作做此改进，对于非整行替换直接拒绝掉。杜绝列数异常
    """
    if edit["range"]["start_position"][1] not in [1, -1] or edit["range"]["end_position"][1] not in [1, -1]:
        raise IDEExecutionError(
            message="编辑操作参数错误",
            detail_for_llm="编辑操作参数错误，目前只支持整行替换或者在行首与行尾插入内容，不支持对行内的部分内容进行替换。"
            "开始位置与结束位置的character必须为1或者-1，可以跨多行。请重新修改你的工具调用参数。",
        )
    return SingleEditOperation(
        range=convert_edit_range_to_range(edit["range"], model),
        text=edit["new_text"],
    )


def _collapse_tool_return(origin: str, length: int = 100, collapse_str: str = "...", tips: str = "已省略") -> str:
    """
    Collapse the tool return content to a certain length.

    Args:
        origin: The original content.
        length: The length of the content after collapse.
        collapse_str: The string used to replace the content that is not displayed.
        tips: The tips of the collapse.

    Returns:
        The collapsed content.
    """
    if len(origin) <= length:
        return origin
    return f"{origin[:length // 2]}{collapse_str}{tips}{collapse_str}{origin[-length // 2:]}"


class IDETerminalParameter(BaseModel):
    """
    Tool that provides Terminal command execution
    """

    cmd: str
    args: Optional[list[str]] = None


class PyIDETerminalTool(BaseTool):
    """
    Tool that provides Terminal command execution
    """

    name: ClassVar[str] = "TerminalTool"
    description: ClassVar[str] = (
        f"终端命令需要按list[str]传入cmd与args，因为其底层实现是基于Python subprocess.Popen。当前支持的命令为:{CMD_WHITE_LIST}\n"
        f"比如'ls -l .'命令，执行参数为['ls', '-l', '.']。"
    )
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[IDETerminalParameter]] = TypeAdapter(IDETerminalParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        cmd = kwargs.get("cmd", args[0] if len(args) > 0 else None)
        action_args = kwargs.get("args", args[1] if len(args) > 1 else None)
        if not cmd:
            raise ValueError("cmd is required")
        ide_action = IDEAction(category="terminal", action_name=cmd, action_args=action_args)
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(
            origin=obs["obs"],
            msg_meta=MessageMeta(
                done=done, success=success, summary=_collapse_tool_return(obs["obs"]), tool_name=self.name
            ),
        )

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class OpenFileParameter(BaseModel):
    """
    Tool that provides open file functionality
    """

    uri: str


class PyIDEOpenFile(BaseTool):
    """
    Tool that provides open file functionality
    """

    name: ClassVar[str] = "OpenFileTool"
    description: ClassVar[str] = "Open file in IDE Env, return the file content, and you can edit it by other IDETools."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[OpenFileParameter]] = TypeAdapter(OpenFileParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        ide_action = IDEAction(category="workspace", action_name="open_file", action_args={"uri": uri})
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(
            origin=obs["obs"],
            msg_meta=MessageMeta(
                done=done,
                success=success,
                duplicate_call_warn=False,
                summary=_collapse_tool_return(obs["obs"], length=1_000),
                tool_name=self.name,
            ),
        )

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class EditPosition(NamedTuple):
    line: int
    character: int

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: cs.CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        """
        增强Pydantic 获取 JsonSchema的方法，将Position的line和character字段的类型改为integer

        如果不带上item的类型说明，GPT API会报错

        Args:
            core_schema:
            handler:

        Returns:

        """
        sch = handler(core_schema)
        json_schema = handler.resolve_ref_schema(sch)
        json_schema["items"] = {"type": "integer"}
        return json_schema


class EditPosition2(BaseModel):
    line: int
    after_str: Optional[str] = Field(None, description="after_str不可以与before_str同时指定。如果二者均为None，则表示取值行首")
    before_str: Optional[str] = Field(None, description="before_str不可以与after_str同时指定。如果二者均为None，则表示取值行首")

    @model_validator(mode="after")
    def validate_after_str(self) -> Self:
        if self.after_str is not None and self.before_str is not None:
            raise ValueError("after_str and before_str cannot be set at the same time.")
        return self


class EditRange(BaseModel):
    start_position: EditPosition = Field(
        title="开始位置",
        description="开始位置坐标，格式为 (line, character)，注意是1-based，同时支持'-1'这种负数表示倒数形式",
    )
    end_position: EditPosition = Field(
        title="结束位置",
        description="结束位置坐标，格式为 (line, character)，注意是1-based，同时支持'-1'这种负数表示倒数形式",
    )


class EditOperation(BaseModel):
    """
    Tool that provides edit operation functionality
    """

    range: EditRange
    new_text: str


class ApplyEditParameter(BaseModel):
    """
    Tool that provides apply edit functionality
    """

    uri: str
    edits: list[EditOperation]
    compute_undo_edits: bool = False
    auto_save: bool = True


class PyIDEApplyEdit(BaseTool):
    """
    Tool that provides apply edit functionality
    """

    name: ClassVar[str] = "ApplyEditTool"
    description: ClassVar[str] = (
        "When using ApplyEdit, note that ranges (both line and character positions) are 1-based. "
        "Additionally, please adhere to best practices in code editing, such as avoiding modifications "
        "that could disrupt the module declaration or encoding declaration at the beginning of the file."
    )
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[ApplyEditParameter]] = TypeAdapter(ApplyEditParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        edits = cast(list[EditOperation], kwargs.get("edits", args[1] if len(args) > 1 else []))
        model_edits: list[dict] = []
        if edits:
            t_model = self._ide.workspace.open_file(uri=uri)  # type: ignore
            model_edits = [construct_single_edit_operation(edit.model_dump(), t_model).model_dump() for edit in edits]
        compute_undo_edits = kwargs.get("compute_undo_edits", args[2] if len(args) > 2 else False)
        auto_save = kwargs.get("auto_save", True)
        ide_action = IDEAction(
            category="workspace",
            action_name="apply_edit",
            action_args={"uri": uri, "edits": model_edits, "compute_undo_edits": compute_undo_edits},
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        if auto_save:
            ide_action = IDEAction(category="workspace", action_name="save_file", action_args={"uri": uri})
            _, _, done, success, _ = self._ide.step(ide_action.model_dump())
            if not success:
                raise ValueError("Auto save failed.")
        return ToolReturn(
            origin=obs["obs"],
            msg_meta=MessageMeta(
                done=done, success=success, summary=_collapse_tool_return(obs["obs"], length=300), tool_name=self.name
            ),
        )

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class SimpleEditOperation(BaseModel):
    start_line: int = Field(
        ...,
        title="起始行号",
        description="1-based 的行号（支持负数表示倒数），包含该行",
    )
    end_line: int = Field(
        ...,
        title="结束行号",
        description="1-based 的行号（支持负数表示倒数），必须 >= 起始行号，包含该行。如果仅替换一行，起始行号与结束行号相同",
    )
    new_text: str = Field(
        "",
        title="新文本内容",
        description="替换后的完整文本内容（可包含多行），将完全替换指定行范围的内容。不指定表示删除指定范围",
    )


class SimpleApplyEditParameter(BaseModel):
    """
    简化的代码编辑工具参数，支持多行整体替换
    """

    uri: str
    edits: list[SimpleEditOperation]


class PyIDEApplySimpleEdit(BaseTool):
    """
    简化的代码编辑工具，支持基于行号的整块替换
    """

    name: ClassVar[str] = "SimpleEditTool"
    description: ClassVar[str] = "支持基于行号的整块代码替换工具。行号为 1-based（负数表示倒数），" "编辑操作将完全替换指定行范围的内容。注意保持代码结构的完整性。"
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[SimpleApplyEditParameter]] = TypeAdapter(SimpleApplyEditParameter)
    _ide: PythonIDE = PrivateAttr()

    # 以下属性与原工具保持一致
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    @staticmethod
    def _convert_edit(edit: SimpleEditOperation, model: TextModel) -> dict:
        """将简化版编辑操作转换为标准编辑操作"""
        # 获取文件总行数用于处理负数行号
        total_lines = model.get_line_count()
        start_char = 1
        end_char = -1
        # 兼容如果start_line超过文件行数，表示直接在文件末尾追加，同时自动在new_text前添加一个换行符
        if edit.start_line > total_lines:
            edit.new_text = "\n" + edit.new_text
            edit.start_line = total_lines
            start_char = -1  # 从行尾开始

        # 计算实际行号（处理负数）
        start_line = edit.start_line if edit.start_line > 0 else total_lines + edit.start_line + 1
        end_line = edit.end_line if edit.end_line > 0 else total_lines + edit.end_line + 1

        # 确保行号有效性
        start_line = max(1, min(start_line, total_lines))
        end_line = max(start_line, min(end_line, total_lines))

        # 构造标准编辑范围（从起始行首到结束行尾）
        return {
            "range": {
                "start_position": (start_line, start_char),
                "end_position": (end_line, end_char),
            },
            "new_text": edit.new_text,
        }

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if args else None)
        edits: list[SimpleEditOperation] = kwargs.get("edits", args[1] if len(args) > 1 else [])
        model_edits = []
        if edits:
            # 打开文件并转换编辑操作
            t_model = self._ide.workspace.open_file(uri=uri)  # type: ignore
            model_edits = [
                construct_single_edit_operation(self._convert_edit(edit, t_model), t_model).model_dump()
                for edit in edits
            ]

        # 应用编辑（固定参数）
        ide_action = IDEAction(
            category="workspace",
            action_name="apply_edit",
            action_args={"uri": uri, "edits": model_edits, "compute_undo_edits": False},  # 固定参数
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())

        # 自动保存（固定开启）
        ide_action = IDEAction(category="workspace", action_name="save_file", action_args={"uri": uri})
        _, _, save_done, save_success, _ = self._ide.step(ide_action.model_dump())

        if not save_success:
            raise RuntimeError("文件自动保存失败")

        return ToolReturn(
            origin=obs["obs"],
            msg_meta=MessageMeta(
                done=done and save_done,
                success=success and save_success,
                summary=_collapse_tool_return(obs["obs"], length=300),
                tool_name=self.name,
            ),
        )

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class SaveFileParameter(BaseModel):
    """
    Tool that provides save file functionality
    """

    uri: str


class PyIDESaveFile(BaseTool):
    """
    Tool that provides save file functionality
    """

    name: ClassVar[str] = "SaveFileTool"
    description: ClassVar[str] = "Save file in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[SaveFileParameter]] = TypeAdapter(SaveFileParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        ide_action = IDEAction(category="workspace", action_name="save_file", action_args={"uri": uri})
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(
            origin=obs["obs"],
            msg_meta=MessageMeta(
                done=done, success=success, summary=_collapse_tool_return(obs["obs"]), tool_name=self.name
            ),
        )

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class InspectGrammarParameter(BaseModel):
    """
    Tool that provides inspect grammar functionality
    """

    uris: list[str]


class PyIdeInspectGrammar(BaseTool):
    """
    Tool that provides inspect grammar functionality
    """

    name: ClassVar[str] = "InspectGrammarErrTool"
    description: ClassVar[str] = "Inspect grammar err of file in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[InspectGrammarParameter]] = TypeAdapter(InspectGrammarParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uris = kwargs.get("uris", args[0] if len(args) > 0 else None)
        ide_action = IDEAction(category="workspace", action_name="inspect_grammar_err", action_args={"uris": uris})
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class CloseFileParameter(BaseModel):
    """
    Tool that provides close file functionality
    """

    uri: str


class PyIDECloseFile(BaseTool):
    """
    Tool that provides close file functionality
    """

    name: ClassVar[str] = "CloseFileTool"
    description: ClassVar[str] = "Close file in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[CloseFileParameter]] = TypeAdapter(CloseFileParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        ide_action = IDEAction(category="workspace", action_name="close_file", action_args={"uri": uri})
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class ReadFileParameter(BaseModel):
    """
    Tool that provides read file functionality
    """

    uri: str
    with_line_num: bool = True
    code_range: Optional[EditRange] = None


class PyIDEReadFile(BaseTool):
    """
    Tool that provides read file functionality
    """

    name: ClassVar[str] = "ReadFileTool"
    description: ClassVar[str] = "Read file in IDE Env, read part of the file by code_range."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[ReadFileParameter]] = TypeAdapter(ReadFileParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    enable_simple_view_mode: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
            enable_simple_view_mode=self.enable_simple_view_mode,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        with_line_num = kwargs.get("with_line_num", args[1] if len(args) > 1 else True)
        code_range = kwargs.get("code_range", args[2] if len(args) > 2 else None)
        code_range = code_range.model_dump() if isinstance(code_range, EditRange) else code_range

        model = self._ide.workspace.open_file(uri=uri)  # type: ignore
        if not code_range:
            code_range = model.get_full_model_range().model_dump()

        model_range = convert_edit_range_to_range(code_range, model)

        ide_action = IDEAction(
            category="workspace",
            action_name="read_file",
            action_args={"uri": uri, "with_line_num": with_line_num, "code_range": model_range},
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(
            origin=obs["obs"],
            msg_meta=MessageMeta(
                done=done,
                success=success,
                duplicate_call_warn=False,
                summary=_collapse_tool_return(
                    obs["obs"], length=1_000, tips="已省略中间内容，你可以再次调用ReadFileTool查看内容，同时你可以指定code_scope以获取更精确的内容"
                ),
                tool_name=self.name,
            ),
        )

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class GetFileSymbolsParameter(BaseModel):
    """
    Tool that provides get file symbols functionality
    """

    uri: str
    kinds: Optional[list[int]] = None


class PyIDEGetFileSymbols(BaseTool):
    """
    Tool that provides get file symbols functionality
    """

    name: ClassVar[str] = "GetFileSymbolsTool"
    description: ClassVar[str] = "Get file symbols in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[GetFileSymbolsParameter]] = TypeAdapter(GetFileSymbolsParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        kinds = kwargs.get("kinds", args[1] if len(args) > 1 else None)
        ide_action = IDEAction(
            category="workspace", action_name="get_file_symbols", action_args={"uri": uri, "kinds": kinds}
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class FindInFileParameter(BaseModel):
    """
    Tool that provides find in file functionality
    """

    uri: str
    query: str
    search_scope: EditRange | list[EditRange] | None = None
    is_regex: bool = False
    match_case: bool = False
    word_separator: Optional[str] = None
    capture_matches: bool = True
    limit_result_count: Optional[int] = None


class PyIDEFindInFile(BaseTool):
    """
    Tool that provides find in file functionality
    """

    name: ClassVar[str] = "FindInFileTool"
    description: ClassVar[str] = "Find in file(specify by uri) in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[FindInFileParameter]] = TypeAdapter(FindInFileParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        query = kwargs.get("query", args[1] if len(args) > 1 else None)
        search_scope = kwargs.get("search_scope", args[2] if len(args) > 2 else None)
        if search_scope:
            t_model = self._ide.workspace.open_file(uri=uri)  # type: ignore
            if isinstance(search_scope, dict):
                search_scope = convert_edit_range_to_range(search_scope, t_model)
            elif isinstance(search_scope, list):
                search_scope = [convert_edit_range_to_range(x, t_model) for x in search_scope]
        is_regex = kwargs.get("is_regex", args[3] if len(args) > 3 else False)
        match_case = kwargs.get("match_case", args[4] if len(args) > 4 else False)
        word_separator = kwargs.get("word_separator", args[5] if len(args) > 5 else None)
        capture_matches = kwargs.get("capture_matches", args[6] if len(args) > 6 else True)
        limit_result_count = kwargs.get("limit_result_count", args[7] if len(args) > 7 else None)
        ide_action = IDEAction(
            category="workspace",
            action_name="find_in_file",
            action_args={
                "uri": uri,
                "query": query,
                "search_scope": search_scope,
                "is_regex": is_regex,
                "match_case": match_case,
                "word_separator": word_separator,
                "capture_matches": capture_matches,
                "limit_result_count": limit_result_count,
            },
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class ReplaceInFileParameter(BaseModel):
    """
    Tool that provides replace in file functionality
    """

    uri: str
    query: str
    replacement: str
    search_scope: EditRange | list[EditRange] | None = None
    is_regex: bool = False
    match_case: bool = False
    word_separator: Optional[str] = None


class PyIDEReplaceInFile(BaseTool):
    """
    Tool that provides replace in file functionality
    """

    name: ClassVar[str] = "ReplaceInFileTool"
    description: ClassVar[str] = "Replace in file(specify by uri) in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[ReplaceInFileParameter]] = TypeAdapter(ReplaceInFileParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        query = kwargs.get("query", args[1] if len(args) > 1 else None)
        replacement = kwargs.get("replacement", args[2] if len(args) > 2 else None)
        search_scope = kwargs.get("search_scope", args[3] if len(args) > 3 else None)
        if search_scope:
            t_model = self._ide.workspace.open_file(uri=uri)  # type: ignore
            if isinstance(search_scope, dict):
                search_scope = convert_edit_range_to_range(search_scope, t_model)
            elif isinstance(search_scope, list):
                search_scope = [convert_edit_range_to_range(x, t_model) for x in search_scope]
        is_regex = kwargs.get("is_regex", args[4] if len(args) > 4 else False)
        match_case = kwargs.get("match_case", args[5] if len(args) > 5 else False)
        word_separator = kwargs.get("word_separator", args[6] if len(args) > 6 else None)
        ide_action = IDEAction(
            category="workspace",
            action_name="replace_in_file",
            action_args={
                "uri": uri,
                "query": query,
                "replacement": replacement,
                "search_scope": search_scope,
                "is_regex": is_regex,
                "match_case": match_case,
                "word_separator": word_separator,
            },
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)


class InsertCursorParameter(BaseModel):
    """
    Tool that provides insert cursor functionality
    """

    uri: str
    key: str
    position: EditPosition | EditPosition2


class PyIDEInsertCursor(BaseTool):
    """
    Tool that provides insert cursor functionality
    """

    name: ClassVar[str] = "InsertCursorTool"
    description: ClassVar[str] = "Insert cursor in file(specify by uri) in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[InsertCursorParameter]] = TypeAdapter(InsertCursorParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        key = kwargs.get("key", args[1] if len(args) > 1 else None)
        position = kwargs.get("position", args[2] if len(args) > 2 else None)

        # 判断如果是EditPosition2类型，转换为EditPosition
        line: int
        character: int
        if isinstance(position, dict):
            after_str = position.get("after_str")
            before_str = position.get("before_str")
            line = position["line"]
            t_model = self._ide.workspace.open_file(uri=uri)  # type: ignore
            line_content = t_model.get_line_content(line)
            if after_str:
                character = line_content.find(after_str) + len(after_str) + 1
            elif before_str:
                character = line_content.find(before_str) + 1
            else:
                character = 1
            position = EditPosition(line=line, character=character)
        elif isinstance(position, tuple):
            line = position[0]
            character = position[1]
            t_model = self._ide.workspace.open_file(uri=uri)  # type: ignore
            line_count = t_model.get_line_count()
            if line == 0:
                raise IDEExecutionError(f"line should be 1-based, but got {line}")
            if abs(line) > line_count:
                raise IDEExecutionError(f"line {line} is out of range, total line count is {line_count}")
            line = line if line > 0 else line_count + line + 1
            line_length = t_model.get_line_length(line)
            if character == 0:
                raise IDEExecutionError(f"character should be 1-based, but got {character}")
            if abs(character) > line_length + 1:
                raise IDEExecutionError(
                    f"character {character} is out of range, total character count is {line_length}, "
                    f"the end of line cursor index is {line_length + 1}"
                )
            character = character if character > 0 else line_length + character + 2
            position = EditPosition(line=line, character=character)

        ide_action = IDEAction(
            category="workspace",
            action_name="insert_cursor",
            action_args={
                "uri": uri,
                "key": key,
                "position": position,
            },
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any) -> Any:
        return self._run(*args)


class DeleteCursorParameter(BaseModel):
    """
    Tool that provides delete cursor functionality
    """

    uri: str
    key: str


class PyIDEDeleteCursor(BaseTool):
    """
    Tool that provides delete cursor functionality
    """

    name: ClassVar[str] = "DeleteCursorTool"
    description: ClassVar[str] = "Delete cursor in file(specify by uri) in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[DeleteCursorParameter]] = TypeAdapter(DeleteCursorParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        key = kwargs.get("key", args[1] if len(args) > 1 else None)
        ide_action = IDEAction(
            category="workspace",
            action_name="delete_cursor",
            action_args={
                "uri": uri,
                "key": key,
            },
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any) -> Any:
        return self._run(*args)


class ClearCursorParameter(BaseModel):
    """
    Tool that provides clear cursor functionality
    """

    uri: str


class PyIDEClearCursor(BaseTool):
    """
    Tool that provides clear cursor functionality
    """

    name: ClassVar[str] = "ClearCursorTool"
    description: ClassVar[str] = "Clear cursor in file(specify by uri) in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[ClearCursorParameter]] = TypeAdapter(ClearCursorParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        ide_action = IDEAction(
            category="workspace",
            action_name="clear_cursor",
            action_args={
                "uri": uri,
            },
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any) -> Any:
        return self._run(*args)


class CreateFileParameter(BaseModel):
    """
    Tool that provides create file functionality
    """

    uri: str
    init_content: Optional[str] = Field(None, description="Initial content of the file")
    overwrite: Optional[bool] = None
    ignore_if_exists: Optional[bool] = None


class PyIDECreateFile(BaseTool):
    """
    Tool that provides create file functionality
    """

    name: ClassVar[str] = "CreateFileTool"
    description: ClassVar[str] = "Create file in IDE Env."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[CreateFileParameter]] = TypeAdapter(CreateFileParameter)
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        ide = PyIDESingleton(
            cmd_white_list=self.cmd_white_list,
            root_dir=self.root_dir,
            project_name=self.project_name,
            render_with_symbols=self.render_with_symbols,
            max_active_models=self.max_active_models,
            cmd_time_out=self.cmd_time_out,
        ).ide
        setattr(self, "_ide", ide)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        uri = kwargs.get("uri", args[0] if len(args) > 0 else None)
        init_content = kwargs.get("init_content", args[1] if len(args) > 1 else None)
        overwrite = kwargs.get("overwrite", args[1] if len(args) > 1 else None)
        ignore_if_exists = kwargs.get("ignore_if_exists", args[2] if len(args) > 2 else None)
        ide_action = IDEAction(
            category="workspace",
            action_name="create_file",
            action_args={
                "uri": uri,
                "init_content": init_content,
                "overwrite": overwrite,
                "ignore_if_exists": ignore_if_exists,
            },
        )
        obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
        save_action = IDEAction(category="workspace", action_name="save_file", action_args={"uri": uri})
        _, _, done, success, _ = self._ide.step(save_action.model_dump())
        if not success:
            raise ValueError("Auto save failed.")
        return ToolReturn(origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name))

    async def _async_run(self, *args: Any) -> Any:
        return self._run(*args)


class AIEditorJobDesParameter(BaseModel):
    """
    Tool that provides AICoderJobDes functionality
    """

    job_des: str


class PyAIEditor(BaseTool):
    """
    Tool that provides AIEditor functionality
    """

    name: ClassVar[str] = "AIEditorTool"
    description: ClassVar[
        str
    ] = "AIEditor in IDE Env, describe your requirement in natural language, AIEditor will get things done for you."
    version: ClassVar[str] = "0.0.1"
    params_schema: ClassVar[TypeAdapter[AIEditorJobDesParameter]] = TypeAdapter(AIEditorJobDesParameter)
    _editor: Any = PrivateAttr()
    _tools: list[BaseTool] = PrivateAttr(default_factory=list)
    root_dir: str
    project_name: str
    # 创建缓存实例
    _tool_cache: LRUCache = PrivateAttr(LRUCache(maxsize=128))

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        self.add_tools(self.default_tools)
        setattr(self, "_editor", self.construct_chains())

    @property
    def default_tools(self) -> list[BaseTool]:
        """
        Default tools for AIEditor. Subclass can override this method to provide custom tools.

        Returns:
            list[BaseTool]: list of default tools
        """
        # 使用Chains来模拟一个Editor的编辑思维链
        terminal_tool = PyIDETerminalTool(root_dir=self.root_dir, project_name=self.project_name)
        open_file_tool = PyIDEOpenFile(root_dir=self.root_dir, project_name=self.project_name)
        apply_edit_tool = PyIDEApplyEdit(root_dir=self.root_dir, project_name=self.project_name)
        save_file_tool = PyIDESaveFile(root_dir=self.root_dir, project_name=self.project_name)
        read_file_tool = PyIDEReadFile(root_dir=self.root_dir, project_name=self.project_name)
        create_file_tool = PyIDECreateFile(root_dir=self.root_dir, project_name=self.project_name)
        tools = [
            terminal_tool,
            open_file_tool,
            apply_edit_tool,
            save_file_tool,
            read_file_tool,
            create_file_tool,
        ]
        return tools

    @cachedmethod(lambda self: self._tool_cache, key=lambda self: hashkey(tuple(self._tools)))
    def get_tool_map(self) -> dict[str, BaseTool]:
        """
        Get the tool map | 获取工具映射

        Returns:
            dict[str, BaseTool]: 工具映射 | tool map
        """
        return {generate_register_name(tool): tool for tool in self._tools}

    @property
    def tool_map(self) -> dict[str, BaseTool]:
        """
        Get the tool map | 获取工具映射

        Returns:
            dict[str, BaseTool]: 工具映射 | tool map
        """
        return self.get_tool_map()

    def add_tool(self, tool: BaseTool) -> None:
        """
        Add a tool to the drive | 添加工具到驱动

        Args:
            tool(BaseTool): 工具 | tool
        """
        # 如果当前驱动中已经存在了工具类，需要抛出异常
        if generate_register_name(tool) in self.tool_map.keys():
            raise ValueError(f"Tool {tool.name} already exists in drive")
        if self._neural:
            self._neural.register(tool)
        self._tools.append(tool)

    def add_tools(self, tools: list[BaseTool]) -> None:
        """
        Add a list of tools to the drive | 添加工具列表到驱动

        Args:
            tools(list[BaseTool]): 工具列表 | tools
        """
        for tool in tools:
            self.add_tool(tool)

    def remove_tool(self, tool: BaseTool) -> None:
        """
        Remove a tool from the drive | 从驱动中移除工具

        Args:
            tool(BaseTool): 工具 | tool

        Returns:

        """
        self._tools.remove(tool)
        if self._neural:
            tool.disconnect_from_neural(self._neural)

    def get_action_llm(self) -> ChatLLM:
        """
        Get the action LLM | 获取动作LLM

        Returns:
            ChatLLM: 动作LLM | action LLM
        """
        from tfrobot.brain.chain.llms.anthropic import ToolsBetaClaude

        return ToolsBetaClaude(name="claude-3-haiku-20240307")

    @staticmethod
    def get_tool_use_examples() -> list[str]:
        """
        Get the tool use examples | 获取工具使用示例

        Returns:
            list[str]: 工具使用示例 | tool use examples
        """
        return [
            "在 project_root_dir 目录下，新建一个 const.py 文件。你可以使用 {'uri': 'file:///{replace_by_real_project_root_"
            "path}/const.py'} 来调用 create_file 工具",
            "添加对openai SDK的依赖。你可以使用 {'cmd': 'poetry', 'args': ['add', 'openai']} 来调用 terminal 工具",
            "替换项目根目录下const.py文件第一行的内容为 '# -*- coding: utf-8 -*-' 你可以使用 \n"
            "{\n"
            "  'uri': 'file:///{replace_by_real_project_root_path}/const.py',\n"
            "  'edits': [\n"
            "    {\n"
            "      'range': {'start_position': (1, 1), 'end_position': (1, -1)},\n"
            "      'text': '# -*- coding: utf-8 -*-'\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "来调用 apply_edit 工具",
        ]

    def construct_chains(self) -> Any:
        from tfrobot.brain.chain.chain import Chain
        from tfrobot.brain.chain.chain_structures.sequence_chains import SeqChains
        from tfrobot.brain.chain.prompt.example_selector.ngram_overlap_selector import NGramExampleSelector
        from tfrobot.brain.chain.prompt.examples_prompt import (
            JINJA2_TEMPLATE,
            DefaultExampleParamsSch,
            ExamplesPrompt,
        )
        from tfrobot.brain.chain.prompt.template.jinja2_template import Jinja2PromptTemplate
        from tfrobot.schema.brain.chain.chain_schema import ChainResult
        from tfrobot.schema.message.conversation.message_dto import TextMessage
        from tfrobot.schema.types import Locale
        from tfrobot.schema.users import BaseUser

        generate_action_llm = self.get_action_llm()
        generate_action_prompt = ExamplesPrompt(  # noqa
            selector=NGramExampleSelector(),
            template=Jinja2PromptTemplate(
                templates={
                    Locale.EN: "You can call tools to edit text in file or manage workspace. Here are some examples:\n"
                    + JINJA2_TEMPLATE
                    + f"\nSome requirements may not be completed in one tool call, you can call step by step, "
                    f"after each call, the tool will return the call result, you can take the next action according to "
                    f"the call result. For example, create a file in the first step, and then insert text in the second"
                    f"step.\n Note that all file URIs need to be identified using file://xxx (LSP specification). All "
                    f"Range and Position locations are 1-based.\nCurrent project directory is: {self.root_dir}",
                    Locale.ZH: "你可以调用工具来解决一些文本编辑与工作区管理的问题。以下是一些示例:\n"
                    + JINJA2_TEMPLATE
                    + f"\n有些要求可能无法通过一次工具调用就完成，你可以按步骤调用，每次调用后，工具会返回调用结果，你可以根据调用结果采取下一步行为。比如第一步创建文件，第二步再插入文本。\n"
                    f"注意所有的文件URI需要使用 file://xxx 来标识（LSP规范）。所有的Range与Position定位均是1-based。同时需要注意，在编辑文件时尽量不要破坏文件头部注释信息\n"
                    f"当前的项目目录为:{self.root_dir}",
                },
                params_schema=TypeAdapter(DefaultExampleParamsSch),
            ),
        )
        for example in self.get_tool_use_examples():
            generate_action_prompt.add_example(example)
        generate_action_llm.system_msg_prompt = [generate_action_prompt]

        def validate_generate_chain_res(res: ChainResult) -> tuple[bool, Optional[TextMessage]]:
            if any(intermediate_msg.tool_calls for intermediate_msg in res.chain_run_context.intermediate_msgs):
                # 判断过程中存在工具调用，说明已经执行了某些命令。
                return True, None
            else:
                # 没有工具调用，说明没有生成任何操作
                return False, TextMessage(
                    content="Not any action has been generated. You should use tool to solve the job problem.",
                    role="user",
                    creator=BaseUser(name="IDEEditor", uid="1"),
                )

        generate_action_chain = Chain(
            llm=generate_action_llm, max_iterations=15, max_tokens=128_000, validate_result=validate_generate_chain_res
        )

        chains = SeqChains(chains=[generate_action_chain])
        return chains

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        from tfrobot.schema.message.conversation.message_dto import TextMessage
        from tfrobot.schema.users import BaseUser

        job_des = kwargs.get("job_des", args[0] if len(args) > 0 else None)
        result = self._editor.run(
            current_input=TextMessage(role="user", creator=BaseUser(name="Focus", uid="1"), content=repr(job_des)),
            tools=self._tools,
        )
        return result.content

    async def _async_run(self, *args: Any) -> Any:
        return self._run(*args)


class PyGPTEditor(PyAIEditor):
    """
    Python AI Editor by GPT API
    """

    name: ClassVar[str] = "GPTEditorTool"
    model: str = "gpt-3.5-turbo-0125"

    @overrides.override
    def get_action_llm(self) -> ChatLLM:
        from tfrobot.brain.chain.llms.openai import GPT

        return GPT(name=self.model)


class PyOllamaEditor(PyAIEditor):
    """
    Python AI Editor by Ollama API
    """

    name: ClassVar[str] = "OllamaEditorTool"
    model: str = "qwq"

    @property
    def default_tools(self) -> list[BaseTool]:
        """
        Default tools for AIEditor. Subclass can override this method to provide custom tools.

        Returns:
            list[BaseTool]: list of default tools
        """
        # 使用Chains来模拟一个Editor的编辑思维链
        apply_edit_tool = PyIDEApplySimpleEdit(
            root_dir=self.root_dir, project_name=self.project_name
        )  # ollama使用SimpleEdit降低大模型心智负担
        create_file_tool = PyIDECreateFile(root_dir=self.root_dir, project_name=self.project_name)
        tools = [
            apply_edit_tool,
            create_file_tool,
        ]
        return tools

    @staticmethod
    def get_tool_use_examples() -> list[str]:
        """
        Get the tool use examples | 获取工具使用示例

        Returns:
            list[str]: 工具使用示例 | tool use examples
        """
        return [
            "在 project_root_dir 目录下，新建一个 const.py 文件。你可以使用 {'uri': 'file:///{replace_by_real_project_root_"
            "path}/const.py'} 来调用 create_file 工具",
        ]

    @overrides.override
    def get_action_llm(self) -> ChatLLM:
        """
        Get the action LLM | 获取动作LLM

        Returns:
            ChatLLM: 动作LLM | action LLM
        """
        from tfrobot.brain.chain.llms.ollama import Ollama

        return Ollama(name=self.model, timeout=120)  # QWQ模型是推理模型，运行时间较长，因此适当加大时间
