"""Project registry and runtime domain errors."""


class ProjectError(RuntimeError):
    """Base class for project host errors."""


class ProjectConflictError(ProjectError):
    """A project name or canonical root already exists."""


class ProjectNotFoundError(ProjectError):
    """The requested project does not exist."""


class ProjectNotSelectedError(ProjectError):
    """No project is selected in the current MCP session."""


class ProjectBusyError(ProjectError):
    """A project has active calls and cannot be released safely."""


class ProjectRegistryError(ProjectError):
    """The persisted registry cannot be read or written safely."""
