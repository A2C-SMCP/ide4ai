"""Version-aware storage for LSP push and pull diagnostics."""

from __future__ import annotations

import threading
from collections.abc import Mapping

from ide4ai.dtos.diagnostics import DocumentDiagnosticReport


class DiagnosticsRegistry:
    """Keep only diagnostics matching the latest known TextModel version."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._versions: dict[str, int] = {}
        self._reports: dict[str, DocumentDiagnosticReport] = {}
        self._push_reports: dict[str, Mapping[str, object]] = {}

    def track(self, uri: str, version: int) -> None:
        with self._lock:
            if self._versions.get(uri) != version:
                self._reports.pop(uri, None)
                self._push_reports.pop(uri, None)
            self._versions[uri] = version

    def forget(self, uri: str) -> None:
        with self._lock:
            self._versions.pop(uri, None)
            self._reports.pop(uri, None)
            self._push_reports.pop(uri, None)

    def record_pull(self, uri: str, version: int, report: DocumentDiagnosticReport | None) -> bool:
        if report is None:
            return False
        with self._lock:
            if self._versions.get(uri) != version:
                return False
            self._reports[uri] = report
            return True

    def record_push(self, params: Mapping[str, object]) -> bool:
        uri, version = params.get("uri"), params.get("version")
        if not isinstance(uri, str):
            return False
        with self._lock:
            expected = self._versions.get(uri)
            if expected is None or (isinstance(version, int) and version != expected):
                return False
            self._push_reports[uri] = dict(params)
            return True

    def get(self, uri: str) -> DocumentDiagnosticReport | None:
        with self._lock:
            return self._reports.get(uri)

    def get_push(self, uri: str) -> Mapping[str, object] | None:
        with self._lock:
            return self._push_reports.get(uri)
