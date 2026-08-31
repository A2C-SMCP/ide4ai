# filename: __init__.py
# @Time    : 2025/11/03 20:25
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP (Model Context Protocol) 基础模块 | MCP Base Module

提供通用的 MCP Server 实现，支持多语言 IDE 扩展
Provides generic MCP Server implementation, supporting multi-language IDE extensions
"""

from typing import TYPE_CHECKING, Any

from .config import MCPServerConfig
from .server import BaseMCPServer

if TYPE_CHECKING:
    from .cli import IDEMCPServer


def __getattr__(name: str) -> Any:
    """Load the concrete CLI server lazily so ``python -m ...cli`` stays clean."""
    if name == "IDEMCPServer":
        from .cli import IDEMCPServer

        return IDEMCPServer
    raise AttributeError(name)


__all__ = [
    "BaseMCPServer",
    "IDEMCPServer",
    "MCPServerConfig",
]
