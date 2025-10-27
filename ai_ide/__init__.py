"""
AI IDE - A powerful IDE environment designed for AI agents to interact with code.

This package provides a comprehensive IDE environment that AI agents can use to:
- Navigate and understand code structure
- Edit files with LSP support
- Execute commands in terminal environments
- Manage workspaces and projects

Main Components:
- IDE: Base IDE environment class
- PythonIDE: Python-specific IDE implementation
- BaseWorkspace: Workspace management
- BaseTerminalEnv: Terminal environment interface
"""

from ai_ide.base import IDE
from ai_ide.exceptions import IDEExecutionError, IDEProtocolError
from ai_ide.ides import IDESingleton, PyIDESingleton
from ai_ide.python_ide.ide import PythonIDE
from ai_ide.schema import IDEAction, IDEObs, LanguageId

__version__: str = "0.1.0"
__all__ = [
    "IDE",
    "PythonIDE",
    "IDESingleton",
    "PyIDESingleton",
    "IDEAction",
    "IDEObs",
    "LanguageId",
    "IDEExecutionError",
    "IDEProtocolError",
]
