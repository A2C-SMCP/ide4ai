# -*- coding: utf-8 -*-
# filename: config.py
# @Time    : 2025/10/29 12:01
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Server 配置管理 | MCP Server Configuration Management

该模块负责管理 MCP Server 的配置，包括 IDE 实例的初始化参数
This module manages MCP Server configuration, including IDE instance initialization parameters
"""

from dataclasses import dataclass, field
from typing import Any

from ide4ai.base import WorkspaceSetting


@dataclass
class MCPServerConfig:
    """
    MCP Server 配置类 | MCP Server Configuration Class

    Attributes:
        cmd_white_list: 命令白名单 | Command whitelist
        root_dir: 根目录 | Root directory
        project_name: 项目名称 | Project name
        render_with_symbols: 是否渲染符号 | Whether to render symbols
        max_active_models: 最大活跃模型数 | Maximum active models
        cmd_time_out: 命令超时时间(秒) | Command timeout (seconds)
        enable_simple_view_mode: 是否启用简化视图模式 | Whether to enable simple view mode
        workspace_setting: 工作区设置 | Workspace settings
    """

    cmd_white_list: list[str] = field(default_factory=list)
    root_dir: str = "."
    project_name: str = "mcp-project"
    render_with_symbols: bool = True
    max_active_models: int = 3
    cmd_time_out: int = 10
    enable_simple_view_mode: bool = True
    workspace_setting: WorkspaceSetting | None = None

    def to_ide_kwargs(self) -> dict[str, Any]:
        """
        转换为 IDE 初始化参数 | Convert to IDE initialization parameters

        Returns:
            dict: IDE 初始化参数字典 | IDE initialization parameters dict
        """
        return {
            "cmd_white_list": self.cmd_white_list,
            "root_dir": self.root_dir,
            "project_name": self.project_name,
            "render_with_symbols": self.render_with_symbols,
            "max_active_models": self.max_active_models,
            "cmd_time_out": self.cmd_time_out,
            "enable_simple_view_mode": self.enable_simple_view_mode,
            "workspace_setting": self.workspace_setting,
        }
