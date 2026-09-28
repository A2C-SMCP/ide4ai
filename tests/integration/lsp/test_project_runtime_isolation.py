"""Real project/Workspace/Pyright lifecycle acceptance for issues #23 and #26."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from lsprotocol import types

from ide4ai.a2c_smcp.projects import ProjectHost, ProjectLspConfig, ProjectRegistry, create_ide_factory


@pytest.mark.timeout(40)
def test_two_real_project_lsps_are_lazy_retained_isolated_and_closed(tmp_path):
    roots = [tmp_path / name for name in ("first", "second")]
    for index, root in enumerate(roots):
        root.mkdir()
        (root / "main.py").write_text(f"class Project{index}:\n    value = {index}\n")
    instances = []
    factory = create_ide_factory({"render_with_symbols": False})

    def create(record):
        ide = factory(record)
        instances.append(ide)
        return ide

    host = ProjectHost(ProjectRegistry(tmp_path / "projects.json"), create)
    records = [
        host.create_project(name=root.name, root_dir=root, lsp=ProjectLspConfig(mode="explicit", language_id="python"))
        for root in roots
    ]
    sessions = []
    initial_threads = set(threading.enumerate())
    try:
        host.switch_project(records[1].name)
        host.switch_project(records[0].name)
        assert instances == []
        for index, record in enumerate(records):
            host.switch_project(record.name)
            with host.lease_current() as (_, ide):
                workspace = ide.workspace
                assert workspace._lsp_manager.session is None
                model = workspace.open_file(uri=(roots[index] / "main.py").as_uri())
                assert f"Project{index}" in model.get_value()
                session = workspace._require_lsp_session()
                sessions.append(session)
                symbols = session.request(
                    types.DocumentSymbolRequest(
                        id=session.next_request_id(),
                        params=types.DocumentSymbolParams(
                            text_document=types.TextDocumentIdentifier(uri=str(model.uri))
                        ),
                    ),
                    types.DocumentSymbolResponse,
                )
                assert symbols.result and {item.name for item in symbols.result} == {f"Project{index}", "value"}
        assert sessions[0] is not sessions[1]
        assert all(session.is_running for session in sessions)

        host.switch_project(records[0].name)
        with host.lease_current() as (captured, first):
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(host.switch_project, records[1].name).result(timeout=5)
            assert captured == records[0]
            assert first is instances[0]
            assert first.workspace._lsp_manager.session is sessions[0]
            assert host.current_project == records[1]
        host.unload_current()
        assert not sessions[1].is_running
        assert sessions[0].is_running
        host.switch_project(records[0].name)
        with host.lease_current() as (_, first_again):
            assert first_again is instances[0]
            assert first_again.workspace._lsp_manager.session is sessions[0]
    finally:
        host.close()
    assert all(session.returncode is not None and not session.is_running for session in sessions)
    assert not [
        thread
        for thread in threading.enumerate()
        if thread not in initial_threads and thread.name.startswith("ide4ai-lsp")
    ]
