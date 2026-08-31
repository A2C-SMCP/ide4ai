from __future__ import annotations

from ide4ai.dtos.diagnostics import RelatedFullDocumentDiagnosticReport
from ide4ai.lsp.diagnostics import DiagnosticsRegistry


def test_registry_drops_stale_push_and_pull_diagnostics() -> None:
    registry = DiagnosticsRegistry()
    uri = "file:///workspace/main.py"
    report = RelatedFullDocumentDiagnosticReport(kind="full", items=[])
    registry.track(uri, 2)

    assert registry.record_push({"uri": uri, "version": 1, "diagnostics": []}) is False
    assert registry.get_push(uri) is None
    assert registry.record_pull(uri, 1, report) is False
    assert registry.get(uri) is None

    assert registry.record_push({"uri": uri, "version": 2, "diagnostics": []}) is True
    assert registry.get_push(uri) == {"uri": uri, "version": 2, "diagnostics": []}
    assert registry.record_pull(uri, 2, report) is True
    assert registry.get(uri) is report

    registry.track(uri, 3)
    assert registry.get(uri) is None
    assert registry.get_push(uri) is None


def test_registry_forget_discards_document_state() -> None:
    registry = DiagnosticsRegistry()
    uri = "file:///workspace/main.py"
    registry.track(uri, 1)
    assert registry.record_push({"uri": uri, "version": 1, "diagnostics": []}) is True

    registry.forget(uri)

    assert registry.get_push(uri) is None
    assert registry.record_push({"uri": uri, "version": 1, "diagnostics": []}) is False
