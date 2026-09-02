"""Event-driven bridge from synchronous Resource producers to MCP sessions."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import anyio
from pydantic import AnyUrl

from ide4ai.a2c_smcp.catalog import ResourceUpdateListener
from ide4ai.a2c_smcp.projects import ProjectHost
from ide4ai.a2c_smcp.resource_events import ResourceUpdate

_UPDATE_DEBOUNCE_SECONDS = 0.1


class ResourceUpdateSession(Protocol):
    async def send_resource_updated(self, uri: AnyUrl) -> None: ...


@dataclass(frozen=True, slots=True)
class _PendingResourceUpdate:
    update: ResourceUpdate
    selection_generation: int


class ResourceUpdateHub:
    """Coalesce producer-thread events and notify subscribed async sessions."""

    def __init__(
        self,
        host: ProjectHost,
        subscribe_source: Callable[[ResourceUpdateListener], Callable[[], None]],
        is_update_current: Callable[[ResourceUpdate], bool],
    ) -> None:
        self._host = host
        self._subscribe_source = subscribe_source
        self._is_update_current = is_update_current
        self._changed = threading.Event()
        self._lock = threading.RLock()
        self._sessions: dict[int, tuple[ResourceUpdateSession, set[str]]] = {}
        self._pending_updates: dict[tuple[object, str], _PendingResourceUpdate] = {}
        self._unsubscribe_source: Callable[[], None] | None = None
        self._stopped = True

    def connect(self) -> None:
        """Connect once for one MCP Server lifespan."""

        with self._lock:
            if self._unsubscribe_source is not None:
                raise RuntimeError("Resource update hub is already connected")
            self._changed.clear()
            self._stopped = False
            self._unsubscribe_source = self._subscribe_source(self.publish)

    def subscribe(self, session: ResourceUpdateSession, uri: AnyUrl) -> None:
        with self._lock:
            existing = self._sessions.get(id(session))
            if existing is None:
                self._sessions[id(session)] = (session, {str(uri)})
            else:
                existing[1].add(str(uri))

    def unsubscribe(self, session: ResourceUpdateSession, uri: AnyUrl) -> None:
        with self._lock:
            existing = self._sessions.get(id(session))
            if existing is None:
                return
            existing[1].discard(str(uri))
            if not existing[1]:
                self._sessions.pop(id(session), None)

    def publish(self, update: ResourceUpdate) -> None:
        """Accept a Runtime event on its producer thread without blocking it."""

        selection = self._host.selection_snapshot()
        if (
            selection.project is None
            or selection.project.id != update.project.id
            or not self._is_update_current(update)
        ):
            return
        with self._lock:
            if self._stopped:
                return
            self._pending_updates[(update.source_id, str(update.uri))] = _PendingResourceUpdate(
                update,
                selection.generation,
            )
            self._changed.set()

    def stop(self) -> None:
        """Disconnect producers and wake the async worker for bounded shutdown."""

        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            unsubscribe_source = self._unsubscribe_source
            self._unsubscribe_source = None
            self._sessions.clear()
            self._pending_updates.clear()
        if unsubscribe_source is not None:
            unsubscribe_source()
        self._changed.set()

    async def run(self) -> None:
        """Send coalesced updates until :meth:`stop` is called."""

        while True:
            await anyio.to_thread.run_sync(self._changed.wait)
            with self._lock:
                if self._stopped:
                    return
            await anyio.sleep(_UPDATE_DEBOUNCE_SECONDS)
            with self._lock:
                if self._stopped:
                    return
                pending_updates = tuple(self._pending_updates.values())
                self._pending_updates.clear()
                self._changed.clear()
                sessions = tuple(
                    (session, frozenset(subscriptions)) for session, subscriptions in self._sessions.values()
                )
            for pending in pending_updates:
                update = pending.update
                selection = self._host.selection_snapshot()
                if (
                    selection.project is None
                    or selection.project.id != update.project.id
                    or selection.generation != pending.selection_generation
                    or not self._is_update_current(update)
                ):
                    continue
                uri_str = str(update.uri)
                uri = AnyUrl(uri_str)
                for session, subscriptions in sessions:
                    if uri_str not in subscriptions:
                        continue
                    try:
                        await session.send_resource_updated(uri)
                    except Exception:
                        self._discard_session(session)

    def _discard_session(self, session: ResourceUpdateSession) -> None:
        with self._lock:
            self._sessions.pop(id(session), None)
