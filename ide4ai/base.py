# filename: base.py
# @Time    : 2024/4/16 19:56
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import atexit
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar, SupportsFloat

import gymnasium as gym
from gymnasium.core import RenderFrame
from typing_extensions import TypedDict

from ide4ai.environment.terminal.base import BaseTerminalEnv
from ide4ai.environment.workspace.base import BaseWorkspace
from ide4ai.schema import IDEObs


class WorkspaceSetting(TypedDict, total=False):
    """
    工作区配置项 / Workspace configuration options

    Attributes:
        header_generators (dict[str, Callable[[BaseWorkspace, str], str]] | None):
            文件头生成器字典，key为文件扩展名（如".py"），value为生成器函数 /
            File header generator dictionary, key is file extension (e.g., ".py"), value is generator function
    """

    header_generators: dict[str, Callable[[BaseWorkspace, str], str]] | None


class IDE(gym.Env, ABC):
    """
    实现原理是基于Docker容器，在一个容器内跑一个Python版本的slim镜像，然后在这个容器内运行LSP服务，通过LSP服务来实现IDE的功能。
    而PythonIDE当前这个类的封装，在于将通用的能力通过step调用传入到容器内，然后容器内的LSP服务来处理这些能力。

    Attributes:
        name (str): 环境名称 / The name of the environment.
        metadata (dict[str, Any]): 环境元数据 / The metadata of the environment.
        root_dir (str): 环境根目录 / The root directory of the environment.
        project_name (str): 项目名称 / The project name of the environment.
        render_with_symbols (bool): 是否使用符号渲染 / Whether render with symbols.
        max_active_models (int): 最大活跃模型数量 / The max active models of the environment.
        cmd_time_out (int): 命令超时时间（秒）/ Command timeout in seconds.
        enable_simple_view_mode (bool): 是否启用简化视图模式 / Whether to enable simple view mode.
        _workspace_setting (WorkspaceSetting | None): 工作区配置项 / Workspace configuration options.
    """

    name: ClassVar[str] = "IDE"
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
        workspace_setting: WorkspaceSetting | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.cmd_white_list = cmd_white_list
        self.cmd_time_out = cmd_time_out
        self.root_dir = root_dir
        self.project_name = project_name
        self.render_with_symbols = render_with_symbols
        self.enable_simple_view_mode = enable_simple_view_mode
        self.max_active_models = max_active_models
        self.terminals: list[BaseTerminalEnv] = []
        self.active_terminal_index: int | None = None
        self.workspace: BaseWorkspace | None = None
        self._workspace_setting = workspace_setting or {}
        # 初始化动作空间与观察空间
        self.action_space = gym.spaces.Dict(
            {
                "category": gym.spaces.Discrete(2),
                "action_name": gym.spaces.Text(100),
                "action_args": gym.spaces.Text(1000),
            },
        )
        self.observation_space = gym.spaces.Dict(
            {
                "created_at": gym.spaces.Text(100),
                "obs": gym.spaces.Text(100000),
            },
        )
        atexit.register(self.close)

    def __del__(self) -> None:
        self.close()

    @property
    def terminal(self) -> BaseTerminalEnv:
        if self.active_terminal_index:
            return self.terminals[self.active_terminal_index]
        else:
            terminal = self.init_terminal()
            self.terminals.append(terminal)
            self.active_terminal(len(self.terminals) - 1)
            return terminal

    @abstractmethod
    def init_terminal(self) -> BaseTerminalEnv: ...

    def active_terminal(self, index: int) -> None:
        self.active_terminal_index = index

    @abstractmethod
    def step(self, action: dict) -> tuple[dict, SupportsFloat, bool, bool, dict[str, Any]]:
        pass

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[IDEObs, dict[str, Any]]:
        return super().reset(seed=seed)

    @abstractmethod
    def render(self) -> RenderFrame | list[RenderFrame] | None:
        pass

    def close(self) -> None:
        for t in self.terminals:
            t.close()
        if self.workspace:
            self.workspace.close()
