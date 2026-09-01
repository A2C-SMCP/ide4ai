"""Persistent project registry and per-session runtime host."""

from ide4ai.a2c_smcp.projects.errors import (
    ProjectBusyError,
    ProjectConflictError,
    ProjectError,
    ProjectNotFoundError,
    ProjectNotSelectedError,
    ProjectRegistryError,
)
from ide4ai.a2c_smcp.projects.host import ProjectHost
from ide4ai.a2c_smcp.projects.models import Project, ProjectLspConfig
from ide4ai.a2c_smcp.projects.registry import ProjectRegistry
from ide4ai.a2c_smcp.projects.runtime import IDEFactory, ProjectRuntime, create_ide_factory
from ide4ai.a2c_smcp.projects.terminal import (
    EmbeddedTerminalRuntime,
    ProjectTerminalNotAvailableError,
    ProjectTerminalRuntimeManager,
    ProjectTerminalState,
    TerminalRuntimeFactory,
    create_embedded_terminal_runtime,
)

__all__ = [
    "IDEFactory",
    "EmbeddedTerminalRuntime",
    "Project",
    "ProjectBusyError",
    "ProjectConflictError",
    "ProjectError",
    "ProjectHost",
    "ProjectLspConfig",
    "ProjectNotFoundError",
    "ProjectNotSelectedError",
    "ProjectRegistry",
    "ProjectRegistryError",
    "ProjectRuntime",
    "ProjectTerminalNotAvailableError",
    "ProjectTerminalRuntimeManager",
    "ProjectTerminalState",
    "TerminalRuntimeFactory",
    "create_ide_factory",
    "create_embedded_terminal_runtime",
]
