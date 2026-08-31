"""Language selection and lazy lifecycle management for one workspace LSP."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from lsprotocol import types

from ide4ai.lsp.session import LspSession

LspMode = Literal["auto", "explicit", "disabled"]
SessionInitializer = Callable[[LspSession], None]

_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "deps",
        "vendor",
        "build",
        "dist",
        "target",
        "out",
        ".mypy_cache",
        ".pytest_cache",
        "__pycache__",
    }
)


@dataclass(frozen=True)
class LspServerSpec:
    """How one language server is launched."""

    command: tuple[str, ...]
    env: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("LSP server command cannot be empty")


@dataclass(frozen=True)
class LanguageProfile:
    """Language recognition rules and the server used for that language."""

    language_id: str
    file_extensions: tuple[str, ...]
    root_markers: tuple[str, ...]
    server: LspServerSpec
    client_capabilities: Mapping[str, object] = field(default_factory=dict)
    initialization_options: Mapping[str, object] | None = None
    header_generators: Mapping[str, Callable[[Any, str], str]] = field(default_factory=dict)
    symbol_kinds: tuple[int, ...] = ()
    verbose_directory_tree: Callable[..., str] | None = None
    verbose_minimal_tree: Callable[..., str] | None = None

    def __post_init__(self) -> None:
        if not self.language_id:
            raise ValueError("Language profile id cannot be empty")
        if not self.file_extensions:
            raise ValueError("Language profile must define file extensions")
        if any(not extension.startswith(".") for extension in self.file_extensions):
            raise ValueError("Language profile extensions must start with '.'")


@dataclass(frozen=True)
class LspSettings:
    """Per-workspace LSP selection settings."""

    mode: LspMode = "auto"
    language_id: str | None = None
    ignored_directories: frozenset[str] = field(default_factory=lambda: _IGNORED_DIRECTORIES)

    def __post_init__(self) -> None:
        if self.mode not in ("auto", "explicit", "disabled"):
            raise ValueError(f"Unsupported LSP mode: {self.mode}")
        if self.mode == "explicit" and not self.language_id:
            raise ValueError("Explicit LSP mode requires language_id")
        if self.mode != "explicit" and self.language_id is not None:
            raise ValueError("language_id is only valid in explicit LSP mode")


class LspState(str, Enum):
    DISABLED = "disabled"
    UNDETECTED = "undetected"
    READY = "ready"
    RUNNING = "running"
    UNAVAILABLE = "unavailable"
    CLOSED = "closed"


@dataclass(frozen=True)
class LspStatus:
    """Structured status suitable for callers that can degrade without an LSP."""

    state: LspState
    language_id: str | None = None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.state in (LspState.READY, LspState.RUNNING)


class LanguageRegistry:
    """Small, deterministic language-profile registry."""

    def __init__(self, profiles: Sequence[LanguageProfile] = ()) -> None:
        self._profiles: dict[str, LanguageProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: LanguageProfile) -> None:
        if profile.language_id in self._profiles:
            raise ValueError(f"Language profile already registered: {profile.language_id}")
        self._profiles[profile.language_id] = profile

    def get(self, language_id: str) -> LanguageProfile | None:
        return self._profiles.get(language_id)

    @property
    def profiles(self) -> tuple[LanguageProfile, ...]:
        return tuple(self._profiles.values())


class LspManager:
    """Own lazy LSP selection and exactly one session for a workspace."""

    def __init__(
        self,
        root_dir: str | Path,
        profiles: Sequence[LanguageProfile],
        *,
        settings: LspSettings | None = None,
        request_timeout: float = 10.0,
        initialize_session: SessionInitializer | None = None,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.registry = LanguageRegistry(profiles)
        self.settings = settings or LspSettings()
        self.request_timeout = request_timeout
        self._initialize_session = initialize_session
        self._lock = threading.RLock()
        self._profile = self._select_profile()
        self._session: LspSession | None = None
        self._stopped = False
        self._closed = False
        self._restart_pending = False
        self._auto_restart_used = False
        self._status = self._initial_status()

    @property
    def status(self) -> LspStatus:
        with self._lock:
            return self._status

    @property
    def primary_language_id(self) -> str | None:
        with self._lock:
            return self._profile.language_id if self._profile is not None else None

    @property
    def session(self) -> LspSession | None:
        with self._lock:
            return self._session

    @property
    def profile(self) -> LanguageProfile | None:
        """The fixed primary-language profile for this workspace."""
        with self._lock:
            return self._profile

    def ensure_started(self, *, language_id: str | None = None, semantic: bool = False) -> LspSession | None:
        """Start only for the fixed primary language or an explicit semantic request."""
        with self._lock:
            if self._closed:
                self._status = LspStatus(LspState.CLOSED, reason="LSP manager is closed")
                return None
            if self._stopped:
                return None
            profile = self._profile
            if profile is None:
                return None
            if language_id is None and not semantic:
                return None
            if language_id is not None and language_id != profile.language_id:
                return None
            if self._session is not None and self._session.is_running:
                return self._session
            if self._status.state == LspState.UNAVAILABLE and not self._restart_pending:
                return None
            if self._restart_pending:
                self._auto_restart_used = True
                self._restart_pending = False
            session = LspSession(
                profile.server.command,
                cwd=self.root_dir,
                env=profile.server.env,
                request_timeout=self.request_timeout,
            )
            try:
                session.start()
                self._session = session
                if self._initialize_session is not None:
                    self._initialize_session(session)
            except BaseException as exc:
                session.close()
                if self._session is session:
                    self._session = None
                self._status = LspStatus(LspState.UNAVAILABLE, profile.language_id, str(exc))
                return None
            session.add_close_callback(lambda error: self._on_session_closed(session, error))
            self._status = LspStatus(LspState.RUNNING, profile.language_id)
            return session

    def reload(self) -> LspStatus:
        """Close the selected session and explicitly re-run language selection."""
        with self._lock:
            session = self._session
            self._session = None
            self._stopped = False
            self._restart_pending = False
            self._auto_restart_used = False
            self._profile = self._select_profile()
            self._status = self._initial_status()
            # Keep the lifecycle lock until the old process is fully closed.  A
            # concurrent semantic request must never create a second server.
            if session is not None:
                session.close()
            return self._status

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            session = self._session
            self._session = None
            self._status = LspStatus(LspState.CLOSED, self.primary_language_id)
        if session is not None:
            session.close()

    def stop(self) -> None:
        """Stop the current session without changing the fixed language selection."""
        with self._lock:
            session = self._session
            self._session = None
            self._stopped = True
            if not self._closed:
                self._status = self._initial_status()
        if session is not None:
            session.close()

    def start(self) -> LspSession | None:
        """Allow lazy startup again after an explicit stop."""
        with self._lock:
            self._stopped = False
        return self.ensure_started(semantic=True)

    def language_for_path(self, path: str | Path) -> str | None:
        suffix = Path(path).suffix.lower()
        with self._lock:
            # Once auto detection fixed one primary profile, a shared suffix
            # belongs to that profile for this workspace.  Falling back to
            # registry order here would prevent its own documents from lazily
            # starting the selected server.
            if self._profile is not None and suffix in self._profile.file_extensions:
                return self._profile.language_id
        for profile in self.registry.profiles:
            if suffix in profile.file_extensions:
                return profile.language_id
        return None

    def profile_for_language(self, language_id: str) -> LanguageProfile | None:
        """Return a registered profile without changing workspace selection."""
        return self.registry.get(language_id)

    def did_open(self, session: LspSession, *, uri: str, language_id: str, version: int, text: str) -> None:
        if not self._open_close_enabled(session):
            return
        session.notify(
            types.DidOpenTextDocumentNotification(
                params=types.DidOpenTextDocumentParams(
                    text_document=types.TextDocumentItem(uri=uri, language_id=language_id, version=version, text=text)
                )
            )
        )

    def did_change(
        self,
        session: LspSession,
        *,
        uri: str,
        version: int,
        changes: Sequence[types.TextDocumentContentChangePartial | types.TextDocumentContentChangeWholeDocument],
        full_text: str,
    ) -> None:
        sync_kind = self._sync_kind(session)
        if sync_kind is types.TextDocumentSyncKind.None_:
            return
        selected_changes = changes
        if sync_kind is types.TextDocumentSyncKind.Full:
            selected_changes = (types.TextDocumentContentChangeWholeDocument(text=full_text),)
        session.notify(
            types.DidChangeTextDocumentNotification(
                params=types.DidChangeTextDocumentParams(
                    text_document=types.VersionedTextDocumentIdentifier(uri=uri, version=version),
                    content_changes=list(selected_changes),
                )
            )
        )

    def will_save(self, session: LspSession, *, uri: str) -> None:
        options = self._sync_options(session)
        enabled = options is not None and options.will_save is True
        if not enabled:
            return
        session.notify(
            types.WillSaveTextDocumentNotification(
                params=types.WillSaveTextDocumentParams(
                    text_document=types.TextDocumentIdentifier(uri=uri),
                    reason=types.TextDocumentSaveReason.Manual,
                )
            )
        )

    def did_save(self, session: LspSession, *, uri: str, text: str) -> None:
        options = self._sync_options(session)
        if options is None or not options.save:
            return
        include_text = isinstance(options.save, types.SaveOptions) and options.save.include_text is True
        session.notify(
            types.DidSaveTextDocumentNotification(
                params=types.DidSaveTextDocumentParams(
                    text_document=types.TextDocumentIdentifier(uri=uri), text=text if include_text else None
                )
            )
        )

    def did_close(self, session: LspSession, *, uri: str) -> None:
        if not self._open_close_enabled(session):
            return
        session.notify(
            types.DidCloseTextDocumentNotification(
                params=types.DidCloseTextDocumentParams(text_document=types.TextDocumentIdentifier(uri=uri))
            )
        )

    @staticmethod
    def _sync_options(session: LspSession) -> types.TextDocumentSyncOptions | None:
        capabilities = session.server_capabilities
        if not isinstance(capabilities, types.ServerCapabilities):
            return None
        sync = capabilities.text_document_sync if capabilities is not None else None
        return sync if isinstance(sync, types.TextDocumentSyncOptions) else None

    @classmethod
    def _sync_kind(cls, session: LspSession) -> types.TextDocumentSyncKind:
        capabilities = session.server_capabilities
        if not isinstance(capabilities, types.ServerCapabilities):
            return types.TextDocumentSyncKind.None_
        sync = capabilities.text_document_sync if capabilities is not None else None
        if isinstance(sync, types.TextDocumentSyncKind):
            return sync
        if isinstance(sync, int):
            try:
                return types.TextDocumentSyncKind(sync)
            except ValueError:
                return types.TextDocumentSyncKind.None_
        options = cls._sync_options(session)
        if options is not None:
            return options.change if options.change is not None else types.TextDocumentSyncKind.None_
        return types.TextDocumentSyncKind.None_ if sync is None else types.TextDocumentSyncKind.Incremental

    @classmethod
    def _open_close_enabled(cls, session: LspSession) -> bool:
        capabilities = session.server_capabilities
        if not isinstance(capabilities, types.ServerCapabilities):
            return False
        sync = capabilities.text_document_sync
        if isinstance(sync, (int, types.TextDocumentSyncKind)):
            return cls._sync_kind(session) is not types.TextDocumentSyncKind.None_
        options = cls._sync_options(session)
        return options is not None and options.open_close is True

    def _initial_status(self) -> LspStatus:
        if self.settings.mode == "disabled":
            return LspStatus(LspState.DISABLED, reason="LSP is disabled by settings")
        if self.settings.mode == "explicit" and self._profile is None:
            return LspStatus(
                LspState.UNAVAILABLE,
                self.settings.language_id,
                f"Language profile is not registered: {self.settings.language_id}",
            )
        if self._profile is None:
            return LspStatus(LspState.UNDETECTED, reason="No unambiguous language profile matched the workspace")
        return LspStatus(LspState.READY, self._profile.language_id)

    def _select_profile(self) -> LanguageProfile | None:
        if self.settings.mode == "disabled":
            return None
        if self.settings.mode == "explicit":
            return self.registry.get(self.settings.language_id or "")

        candidates: list[tuple[tuple[int, int, int], LanguageProfile]] = []
        source_counts = self._source_file_counts()
        root_names = {
            entry.name for entry in self.root_dir.iterdir() if _resolves_within_workspace(entry, self.root_dir)
        }
        for profile in self.registry.profiles:
            marker_count = sum(marker in root_names for marker in profile.root_markers)
            source_count = source_counts.get(profile.language_id, 0)
            if marker_count == 0 and source_count == 0:
                continue
            candidates.append(((int(marker_count > 0), marker_count, source_count), profile))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_profile = candidates[0]
        if sum(score == best_score for score, _ in candidates) != 1:
            return None
        return best_profile

    def _source_file_counts(self) -> dict[str, int]:
        counts = {profile.language_id: 0 for profile in self.registry.profiles}
        pending = [self.root_dir]
        visited: set[Path] = set()
        while pending:
            directory = pending.pop()
            try:
                resolved = directory.resolve()
            except OSError:
                continue
            if resolved in visited or not _is_relative_to(resolved, self.root_dir):
                continue
            visited.add(resolved)
            try:
                entries = tuple(directory.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.name in self.settings.ignored_directories and entry.is_dir():
                    continue
                try:
                    if entry.is_dir():
                        pending.append(entry)
                        continue
                    if not entry.is_file() or not _is_relative_to(entry.resolve(), self.root_dir):
                        continue
                except OSError:
                    continue
                suffix = entry.suffix.lower()
                # A suffix can intentionally belong to more than one language
                # (for example C/C++ headers).  Count it for every matching
                # profile so the ranking can correctly detect a tie.
                for profile in self.registry.profiles:
                    if suffix in profile.file_extensions:
                        counts[profile.language_id] += 1
        return counts

    def _on_session_closed(self, session: LspSession, error: BaseException) -> None:
        with self._lock:
            if self._session is session:
                language_id = self._profile.language_id if self._profile is not None else None
                self._session = None
                self._restart_pending = not self._auto_restart_used
                self._status = LspStatus(LspState.UNAVAILABLE, language_id, str(error))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolves_within_workspace(path: Path, root: Path) -> bool:
    try:
        return _is_relative_to(path.resolve(), root)
    except OSError:
        return False
