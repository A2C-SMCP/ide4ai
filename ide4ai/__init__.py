"""
AI IDE - A powerful IDE environment designed for AI agents to interact with code.

This package provides a comprehensive IDE environment that AI agents can use to:
- Navigate and understand code structure
- Edit files with LSP support
- Execute commands in terminal environments
- Manage workspaces and projects

Main Components:
- BaseIDE: Abstract IDE environment class
- IDE: Concrete language-profile-driven IDE implementation
- Workspace: Workspace management
- BaseTerminalEnv: Terminal environment interface
"""

from ide4ai.base import BaseIDE
from ide4ai.environment.workspace.workspace import Workspace
from ide4ai.exceptions import IDEExecutionError, IDEProtocolError
from ide4ai.ide import IDE
from ide4ai.ides import IDEInstance, IDESingleton
from ide4ai.schema import IDEAction, IDEObs, LanguageId

__version__ = "0.1.0rc0"

__all__ = [
    "IDE",
    "BaseIDE",
    "Workspace",
    "IDESingleton",
    "IDEInstance",
    "IDEAction",
    "IDEObs",
    "LanguageId",
    "IDEExecutionError",
    "IDEProtocolError",
]
