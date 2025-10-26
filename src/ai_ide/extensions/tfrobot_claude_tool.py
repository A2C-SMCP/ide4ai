# -*- coding: utf-8 -*-
# filename: claude_tool.py
# @Time    : 2025/4/24 19:17
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
Claude有自己的Editor微调模型。因此可以通过定制其专有工具的方式实现更好的调用
可以参考：https://docs.anthropic.com/en/docs/build-with-claude/tool-use/text-editor-tool
"""
import copy
import inspect
from collections import deque
from typing import Any, AsyncIterator, ClassVar, DefaultDict, Iterator, Literal, Optional, cast

from pydantic import Field, PrivateAttr, TypeAdapter
from spacy.pipeline.ner import defaultdict

from tfrobot.drive.tool.base import BaseTool, wrap_tool_return
from ai_ide.environment.workspace.schema import TextEdit
from ai_ide.ides import PyIDESingleton
from ai_ide.python_ide.ide import PythonIDE
from ai_ide.schema import IDEAction
from ai_ide.tool import (
    CMD_WHITE_LIST,
    EditOperation,
    EditPosition,
    EditRange,
    _collapse_tool_return,
    construct_single_edit_operation,
    convert_edit_range_to_range,
)
from tfrobot.schema.drive.tool.base import MessageMeta, ToolReturn
from ai_ide.exceptions import IDEProtocolError
from tfrobot.schema.types import is_attribute_value


class ClaudeEditorTool(BaseTool):
    """
    Claude Editor Tool
    """

    name: ClassVar[str] = "str_replace_editor"
    description: ClassVar[str] = "Claude Editor Tool"
    type: ClassVar[Literal["function", "text_editor_20250124"]] = "text_editor_20250124"
    tool_version: str = "0.0.1"
    params_schema: ClassVar[dict | TypeAdapter | None] = None
    _ide: PythonIDE = PrivateAttr()
    cmd_white_list: list[str] = Field(default_factory=lambda: copy.copy(CMD_WHITE_LIST))
    root_dir: str
    project_name: str
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10
    # 至多保存10个撤销动作 先进后出
    _undo_stack: DefaultDict[str, deque[list[TextEdit]]] = PrivateAttr(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=10))
    )

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
        """
        依据：https://docs.anthropic.com/zh-CN/docs/build-with-claude/tool-use/text-editor-tool#view
        实现工具开发

        Args:
            *args (Any): 位置参数
            **kwargs (Any): 关键字参数

        Returns:
            Any: 工具执行结果
        """
        assert not args, "args should be empty, all parameters should be passed in kwargs"
        command = kwargs.get("command")
        uri = cast(str, kwargs.get("path"))
        if uri:
            kwargs["path"] = uri if uri.startswith("file://") else f"file://{uri}"
        match command:
            case "view":
                uri = kwargs["path"]
                with_line_num = kwargs.get("with_line_num", True)
                code_range: Optional[dict] = None
                if kwargs.get("view_range"):
                    start_line, end_line = kwargs["view_range"]
                    code_range = {
                        "start_position": [start_line, 0],
                        "end_position": [end_line, -1],
                    }

                model = self._ide.workspace.open_file(uri=uri)  # type: ignore
                # 如果不指定范围则查看全部
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
            case "str_replace":
                uri = kwargs["path"]
                query = kwargs.get("old_str")
                replacement = kwargs.get("new_str")
                ide_action = IDEAction(
                    category="workspace",
                    action_name="replace_in_file",
                    action_args={"uri": uri, "query": query, "replacement": replacement, "compute_undo_edits": True},
                )
                obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
                if obs.get("original_result"):
                    self._undo_stack[uri].append(obs["original_result"])
                ide_action = IDEAction(category="workspace", action_name="save_file", action_args={"uri": uri})
                _, _, done, success, _ = self._ide.step(ide_action.model_dump())
                if not success:
                    raise ValueError("Auto save failed.")
                return ToolReturn(
                    origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name)
                )
            case "create":
                uri = str(kwargs.get("uri", args[0] if len(args) > 0 else None))
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
                return ToolReturn(
                    origin=obs["obs"], msg_meta=MessageMeta(done=done, success=success, tool_name=self.name)
                )
            case "insert":
                uri = kwargs["path"]
                insert_line = cast(int, kwargs["insert_line"])
                edits: list[EditOperation] = [
                    EditOperation(
                        range=EditRange(
                            start_position=EditPosition(insert_line + 1, 1),
                            end_position=EditPosition(insert_line + 1, 1),
                        ),
                        new_text=kwargs["new_str"],
                    )
                ]
                model_edits: list[dict] = []
                if edits:
                    t_model = self._ide.workspace.open_file(uri=uri)  # type: ignore
                    model_edits = [
                        construct_single_edit_operation(edit.model_dump(), t_model).model_dump() for edit in edits
                    ]
                ide_action = IDEAction(
                    category="workspace",
                    action_name="apply_edit",
                    action_args={"uri": uri, "edits": model_edits, "compute_undo_edits": True},
                )
                obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
                if obs.get("original_result"):
                    self._undo_stack[uri].append(obs["original_result"])
                ide_action = IDEAction(category="workspace", action_name="save_file", action_args={"uri": uri})
                _, _, done, success, _ = self._ide.step(ide_action.model_dump())
                if not success:
                    raise ValueError("Auto save failed.")
                return ToolReturn(
                    origin=obs["obs"],
                    msg_meta=MessageMeta(
                        done=done,
                        success=success,
                        summary=_collapse_tool_return(obs["obs"], length=300),
                        tool_name=self.name,
                    ),
                )
            case "undo_edit":
                uri = kwargs["path"]
                text_edits = self._undo_stack[uri].pop()
                if not text_edits:
                    raise ValueError("No undo edits available.")
                undo_model_edits = [TextEdit.model_validate(edit).to_single_edit_operation() for edit in text_edits]
                ide_action = IDEAction(
                    category="workspace",
                    action_name="apply_edit",
                    action_args={"uri": uri, "edits": undo_model_edits, "compute_undo_edits": False},
                )
                obs, _, done, success, _ = self._ide.step(ide_action.model_dump())
                ide_action = IDEAction(category="workspace", action_name="save_file", action_args={"uri": uri})
                _, _, done, success, _ = self._ide.step(ide_action.model_dump())
                if not success:
                    raise ValueError("Auto save failed.")
                return ToolReturn(
                    origin=obs["obs"],
                    msg_meta=MessageMeta(
                        done=done,
                        success=success,
                        summary=_collapse_tool_return(obs["obs"], length=300),
                        tool_name=self.name,
                    ),
                )

        return None

    async def _async_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._run(*args, **kwargs)

    def run(
        self,
        tool_params: dict = inspect.Parameter.empty,  # type: ignore
        **kwargs: Any,
    ) -> ToolReturn | Iterator[ToolReturn]:
        """
        执行工具的逻辑，并验证`tool_params`，然后返回`_run`方法的结果。

        Executes the tool's logic, validates `tool_params`, and then returns the result of the `_run` method.

        此方法首先验证`tool_params`是否遵循指定的参数模式，然后调用`_run`方法执行具体操作，并返回结果。结果可以是单个`ToolReturn`类型的实例或这些实例的迭代器。

        This method first validates whether `tool_params` adheres to the specified parameter schema, then calls the
        `_run` method to perform specific actions, and returns the results. The result can be either a single instance
        of type `ToolReturn` or an iterator of these instances.

        在 Python 3.7+ 中，如果一个生成器直接或间接在执行过程中抛出 StopIteration 异常，它会被解释为一个 RuntimeError，
        以避免与生成器正常结束信号（生成器自然耗尽）混淆。这个改变主要是为了改进和统一异步和同步代码的行为。

        背景

        在旧版本的 Python 中，生成器可以抛出 StopIteration 来提早结束生成器。然而，这可能导致混淆，因为 StopIteration 通常由
        next() 函数自动抛出以表示迭代器已耗尽。为了避免这种情况，在 PEP 479 中建议改变生成器抛出 StopIteration 的处理方式，
        使其变为 RuntimeError。

        所以在此不会再重新抛出Stop异常，而是使用break正常结束迭代器

        在此使用while True,配合next()方法与 __anext__()方法来实现循环迭代主要是为了捕获最终抛出的StopIteration/StopAsyncIteration异常。
        以满足用户在封装工具时使用 return结尾的写法。因为有时候用户封装迭代器，不仅使用yield，也会使用return语句。而return语句会触发上述异常。

        Args:
            tool_params (JsonTypes): 工具参数，遵循指定的参数模式。Tool parameters, adhering to the specified params schema.
            **kwargs (Dict[str, Any]): 任意的关键字参数，提供额外的配置选项。Any additional keyword arguments providing extra
                configuration options.

        Returns:
            Union[ToolReturn, Iterator[ToolReturn]]: `_run`方法的执行结果，可能是单个结果或结果的迭代器。The execution result
                of the `_run` method, which may be a single result or an iterator of results.

        """
        if self._neural:
            kwargs["neural"] = self._neural
        try:
            tool_kwargs = tool_params
            if self.merge_context:
                # 如果是自行开发的方法，并且严禁接收 **kwargs。需要关闭merge_context，否则会触发函数调用参数错误
                tool_kwargs.update(kwargs)
            observation = self._run(**tool_kwargs)
        except (Exception, KeyboardInterrupt) as e:  # pragma: no cover
            raise e  # pragma: no cover
        if is_attribute_value(observation):
            meta = MessageMeta(tool_name=self.tool_name, arguments=str(tool_params))
            observation = ToolReturn(
                origin=observation,
                result_for_llm=self.__class__.format_output(observation, self) if observation else None,
                msg_meta=meta,
            )
        elif isinstance(observation, Iterator):

            def iterate_with_call_id_update() -> Iterator[ToolReturn]:
                while True:
                    try:
                        ob = next(observation)
                        yield wrap_tool_return(
                            ob, self.tool_name, tool_params, lambda obs: self.__class__.format_output(obs, self)
                        )
                    except StopIteration as si:
                        final_return = si.value
                        if final_return:
                            final_return = wrap_tool_return(
                                final_return,
                                self.tool_name,
                                tool_params,
                                lambda obs: self.__class__.format_output(obs, self),
                            )
                            yield final_return  # 直接使用 yield 返回最后一个值
                        break  # 正常结束迭代器

            return iterate_with_call_id_update()

        if not isinstance(observation, ToolReturn) and not isinstance(observation, Iterator):
            raise IDEProtocolError(f"Invalid tool return type {type(observation)}", protocol="tool_return_schema")
        return observation

    async def async_run(
        self,
        tool_params: dict = inspect.Parameter.empty,  # type: ignore
        **kwargs: Any,
    ) -> ToolReturn | AsyncIterator[ToolReturn] | Iterator[ToolReturn]:
        """
        异步验证工具参数并执行工具的异步运行方法。

        Asynchronously validates tool parameters and executes the tool's async run method.

        首先验证`tool_params`是否符合`params_schema`定义。若验证通过，则调用`_async_run`方法并返回其结果。

        First, it validates whether `tool_params` conform to the `params_schema` definition. If validation passes,
        it calls the `_async_run` method and returns its result.

        在 Python 3.7+ 中，如果一个生成器直接或间接在执行过程中抛出 StopIteration 异常，它会被解释为一个 RuntimeError，
        以避免与生成器正常结束信号（生成器自然耗尽）混淆。这个改变主要是为了改进和统一异步和同步代码的行为。

        背景

        在旧版本的 Python 中，生成器可以抛出 StopIteration 来提早结束生成器。然而，这可能导致混淆，因为 StopIteration 通常由
        next() 函数自动抛出以表示迭代器已耗尽。为了避免这种情况，在 PEP 479 中建议改变生成器抛出 StopIteration 的处理方式，
        使其变为 RuntimeError。

        所以在此不会再重新抛出Stop异常，而是使用break正常结束迭代器

        在此使用while True,配合next()方法与 __anext__()方法来实现循环迭代主要是为了捕获最终抛出的StopIteration/StopAsyncIteration异常。
        以满足用户在封装工具时使用 return结尾的写法。因为有时候用户封装迭代器，不仅使用yield，也会使用return语句。而return语句会触发上述异常。

        Args:
            tool_params (JsonTypes): 工具参数，遵循指定的参数模式。Tool parameters, adhering to the
                specified params schema.
            **kwargs (Dict[str, Any]): 任意的关键字参数，提供额外的配置选项。Any additional keyword arguments providing extra
                configuration options.

        Returns:
            ToolReturn | AsyncIterator[ToolReturn] | Iterator[ToolReturn]: `_run`方法的执行结果，可能是单个结果或结果的迭代器。
                The execution result of the `_run` method, which may be a single result or an iterator of results.

        """
        if self._neural:
            kwargs["neural"] = self._neural
        try:
            tool_kwargs = tool_params
            if self.merge_context:
                # 如果是自行开发的方法，并且严禁接收 **kwargs。需要关闭merge_context，否则会触发函数调用参数错误
                tool_kwargs.update(kwargs)
            a_run = self._async_run(**tool_kwargs)
            # async 装饰的函数有可能有两种类型，一种是awaitable类型，可以直接使用await拦截。另一种是生成器，需要使用async for 来进行拦截
            if inspect.isawaitable(a_run):
                observation = await a_run
            elif inspect.isasyncgen(a_run):
                observation = a_run
            else:
                raise IDEProtocolError(
                    f"Invalid async run return type {type(a_run)} for tool {self.tool_name}",
                    protocol="tool_return_schema",
                )
        except (Exception, KeyboardInterrupt) as e:  # pragma: no cover
            raise e  # pragma: no cover
        if is_attribute_value(observation):
            meta = MessageMeta(tool_name=self.tool_name, arguments=str(tool_params))
            observation = ToolReturn(
                origin=observation, result_for_llm=self.__class__.format_output(observation, self), msg_meta=meta
            )
        elif isinstance(observation, AsyncIterator):

            async def async_iterate_with_tool_return_construct() -> AsyncIterator[ToolReturn]:
                async for ob in observation:
                    if is_attribute_value(ob):
                        msg_meta = MessageMeta(tool_name=self.tool_name, arguments=str(tool_params))
                        yield ToolReturn(
                            origin=ob,
                            result_for_llm=self.__class__.format_output(ob, self) if ob else None,
                            msg_meta=msg_meta,
                        )
                    else:
                        yield ob

            return async_iterate_with_tool_return_construct()
        elif isinstance(observation, Iterator):

            def iterate_with_call_id_update() -> Iterator[ToolReturn]:
                while True:
                    try:
                        ob = next(observation)
                        yield wrap_tool_return(
                            ob, self.tool_name, tool_params, lambda obs: self.__class__.format_output(obs, self)
                        )
                    except StopIteration as si:
                        final_return = si.value
                        if final_return:
                            final_return = wrap_tool_return(
                                final_return,
                                self.tool_name,
                                tool_params,
                                lambda obs: self.__class__.format_output(obs, self),
                            )
                            yield final_return  # 直接使用 yield 返回最后一个值
                        break  # 正常结束迭代器

            return iterate_with_call_id_update()

        if not isinstance(observation, (ToolReturn, AsyncIterator, Iterator)):
            raise IDEProtocolError(f"Invalid async tool return type {type(observation)}", protocol="tool_return_schema")
        return observation
