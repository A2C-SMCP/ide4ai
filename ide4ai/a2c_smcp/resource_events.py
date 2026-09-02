"""Shared identity-bearing events for dynamic MCP Resource updates."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import AnyUrl

from ide4ai.a2c_smcp.projects.models import Project


@dataclass(frozen=True, slots=True)
class ResourceUpdate:
    """One Resource change tied to an exact producer generation."""

    project: Project
    source_id: object
    uri: AnyUrl
