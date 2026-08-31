"""Built-in language profiles and generic profile configuration helpers."""

from __future__ import annotations

from dataclasses import replace

from ide4ai.languages.python import python_language_profile
from ide4ai.lsp.manager import LanguageProfile, LspServerSpec


def default_language_profiles() -> tuple[LanguageProfile, ...]:
    """Return the language profiles bundled with ide4ai."""
    return (python_language_profile(),)


def configured_language_profiles(
    *,
    language_id: str | None = None,
    server_command: tuple[str, ...] | None = None,
    file_extensions: tuple[str, ...] = (),
    root_markers: tuple[str, ...] = (),
) -> tuple[LanguageProfile, ...]:
    """Build profiles for the generic MCP configuration surface.

    Built-in languages retain their language-specific hooks while allowing the
    server command and detection rules to be overridden.  An unknown language
    can be registered without changing ide4ai when its command and extensions
    are supplied by the caller.
    """
    profiles = {profile.language_id: profile for profile in default_language_profiles()}
    target_language = language_id or ("python" if server_command is not None else None)
    if target_language is None:
        return tuple(profiles.values())

    existing = profiles.get(target_language)
    if existing is not None:
        profiles[target_language] = replace(
            existing,
            file_extensions=file_extensions or existing.file_extensions,
            root_markers=root_markers or existing.root_markers,
            server=LspServerSpec(server_command) if server_command is not None else existing.server,
        )
        return tuple(profiles.values())

    if server_command is None:
        raise ValueError(f"Custom LSP language '{target_language}' requires lsp_server_command")
    if not file_extensions:
        raise ValueError(f"Custom LSP language '{target_language}' requires lsp_file_extensions")
    profiles[target_language] = LanguageProfile(
        language_id=target_language,
        file_extensions=file_extensions,
        root_markers=root_markers,
        server=LspServerSpec(server_command),
    )
    return tuple(profiles.values())


__all__ = ["configured_language_profiles", "default_language_profiles", "python_language_profile"]
