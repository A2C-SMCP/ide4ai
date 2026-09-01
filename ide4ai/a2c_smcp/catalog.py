"""Dynamic MCP tool and resource catalog primitives."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from mcp.types import CallToolResult, Resource, Tool

from ide4ai.a2c_smcp.projects import Project


class ToolBindingNotAvailableError(RuntimeError):
    """A binding's captured project disappeared before invocation began."""


@dataclass(frozen=True)
class CatalogChanges:
    """List-change notifications caused by a successful tool call."""

    tools: bool = False
    resources: bool = False


@dataclass(frozen=True)
class ToolCallOutcome:
    """A structured tool result plus any catalog invalidation it caused."""

    result: dict[str, Any] | CallToolResult
    changes: CatalogChanges = CatalogChanges()


ToolInvoker = Callable[[dict[str, Any]], Awaitable[ToolCallOutcome]]
ResourceReader = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class ToolBinding:
    definition: Tool
    invoke: ToolInvoker


@dataclass(frozen=True)
class ResourceBinding:
    definition: Resource
    read: ResourceReader


class ToolProvider(Protocol):
    """Composable source for tools visible in one project-state snapshot."""

    def bindings(self, current_project: Project | None) -> Iterable[ToolBinding]: ...


class ResourceProvider(Protocol):
    """Composable source for resources visible in one project-state snapshot."""

    def bindings(self, current_project: Project | None) -> Iterable[ResourceBinding]: ...


class DynamicToolCatalog:
    def __init__(self, providers: Sequence[ToolProvider]) -> None:
        self._providers = tuple(providers)

    def bindings(self, current_project: Project | None) -> tuple[ToolBinding, ...]:
        by_name: dict[str, ToolBinding] = {}
        for provider in self._providers:
            for binding in provider.bindings(current_project):
                name = binding.definition.name
                if name in by_name:
                    raise ValueError(f"Duplicate MCP tool name: {name}")
                by_name[name] = binding
        return tuple(sorted(by_name.values(), key=lambda item: (item.definition.name.casefold(), item.definition.name)))

    def find(self, current_project: Project | None, name: str) -> ToolBinding | None:
        return next((binding for binding in self.bindings(current_project) if binding.definition.name == name), None)


class DynamicResourceCatalog:
    def __init__(self, providers: Sequence[ResourceProvider]) -> None:
        self._providers = tuple(providers)

    def bindings(self, current_project: Project | None) -> tuple[ResourceBinding, ...]:
        by_base_uri: dict[str, ResourceBinding] = {}
        for provider in self._providers:
            for binding in provider.bindings(current_project):
                base_uri = _resource_base_key(str(binding.definition.uri))
                if base_uri in by_base_uri:
                    raise ValueError(f"Duplicate MCP resource base URI: {base_uri}")
                by_base_uri[base_uri] = binding
        return tuple(sorted(by_base_uri.values(), key=lambda item: str(item.definition.uri)))

    def find(self, current_project: Project | None, uri: str) -> ResourceBinding | None:
        requested_base = _resource_base_key(uri)
        for binding in self.bindings(current_project):
            if _resource_base_key(str(binding.definition.uri)) == requested_base:
                return binding
        return None


def _resource_base_key(uri: str) -> str:
    parsed = urlparse(uri)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
