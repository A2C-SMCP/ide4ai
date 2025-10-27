# filename: ide.py
# @Time    : 2024/4/16 18:35
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from typing import Any, ClassVar, SupportsFloat

from ide4ai.base import IDE
from ide4ai.environment.terminal.base import EnvironmentArguments
from ide4ai.environment.terminal.local_terminal_env import TerminalEnv
from ide4ai.exceptions import IDEExecutionError
from ide4ai.python_ide.workspace import PyWorkspace
from ide4ai.schema import IDEAction, IDEObs


class PythonIDE(IDE):
    """
    PythonIDE is a gym environment for python ide.

    实现原理是基于Docker容器，在一个容器内跑一个Python版本的slim镜像，然后在这个容器内运行LSP服务，通过LSP服务来实现IDE的功能。
    而PythonIDE当前这个类的封装，在于将通用的能力通过step调用传入到容器内，然后容器内的LSP服务来处理这些能力。

    Attributes:
        name (str): The name of the environment.
        metadata (dict[str, Any]): The metadata of the environment.
        root_dir (str): The root directory of the environment.
        project_name (str): The project name of the environment.
        render_with_symbols (bool): Whether render with symbols.
        max_active_models (int): The max active models of the environment.
    """

    name: ClassVar[str] = "PythonIDE"
    metadata: dict[str, Any] = {"render_modes": ["ansi"]}

    def __init__(
        self,
        cmd_white_list: list[str],
        root_dir: str,
        project_name: str,
        render_with_symbols: bool = True,
        max_active_models: int = 3,
        cmd_time_out: int = 10,
        enable_simple_view_mode: bool = True,
        workspace_setting: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            cmd_white_list,
            root_dir,
            project_name,
            render_with_symbols,
            max_active_models,
            cmd_time_out,
            enable_simple_view_mode,
            workspace_setting,
            *args,
            **kwargs,
        )
        self.workspace = PyWorkspace(
            self.root_dir,
            self.project_name,
            self.render_with_symbols,
            self.max_active_models,
            self.enable_simple_view_mode,
            **self._workspace_setting,
        )

    def init_terminal(self) -> TerminalEnv:
        """
        初始化终端环境

        Returns:
            TerminalEnv: TerminalEnv 对象 | TerminalEnv object
        """

        return TerminalEnv(
            EnvironmentArguments(image_name="local", timeout=self.cmd_time_out),
            self.cmd_white_list,
            self.root_dir,
        )

    def construct_action(self, action: dict) -> IDEAction:
        """
        构建 IDEAction 对象

        Args:
            action (dict): 动作字典 | Action dictionary

        Returns:
            IDEAction: IDEAction 对象 | IDEAction object

        Raises:
            ValueError: 如果动作不在支持的动作集合中 | If the action is not in the supported action set
        """
        ide_action = IDEAction.model_validate(action)
        if ide_action.category == "terminal" and ide_action.action_name not in self.cmd_white_list:
            err = f"Action not in white list: {ide_action.action_args}. Can't run this command now."
            raise IDEExecutionError(message=err, detail_for_llm=err)
        return ide_action

    def step(self, action: dict) -> tuple[dict, SupportsFloat, bool, bool, dict[str, Any]]:
        """
        执行一个动作

        观察返回：
        1. OpenFile: 返回打开文件的内容
        2. ApplyEdit: 返回编辑的变更记录

        奖励机制：
        1. OpenFile: 成功打印返回100，打开失败返回0
        2. ApplyEdit: 变更成功返回100，失败返回0

        Args:
            action (dict): 动作字典 | Action dictionary

        Returns:
            tuple[dict, SupportsFloat, bool, bool, dict[str, Any]]: 观察、奖励、是否结束、是否成功、额外信息 |
                Observation, Reward, Done, Success, Extra info

        Raises:
            ValueError: 如果工作区尚未正常初始化 | If the workspace has not been initialized properly
        """
        ide_action = self.construct_action(action)
        if ide_action.category == "terminal":
            return self.terminal.step(action)
        else:
            if self.workspace:
                return self.workspace.step(action)
            else:
                raise IDEExecutionError(
                    "Workspace is not initialized",
                    detail_for_llm="Workspace is not initialized, initialize workspace first",
                )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[IDEObs, dict[str, Any]]:
        if self.workspace:
            self.workspace.reset(seed=seed, options=options)
        if self.terminals:
            for terminal in self.terminals:
                terminal.reset(seed=seed, options=options)
        return IDEObs(obs="Reset IDE successfully"), {}

    def render(self) -> str:  # type: ignore
        """
        渲染

        Returns:
            str: 渲染结果 | Render result
        """
        content = "IDE Content:\n"
        if self.workspace:
            content += f"当前工作区内容如下:\n{self.workspace.render()}\n"
        if self.active_terminal_index is not None:
            content += f"当前终端内容如下:\n{self.terminal.render()}\n"
        return content
