# filename: test_base.py
# @Time    : 2024/4/30 16:30
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import subprocess
import tempfile
from collections.abc import Sequence
from json import JSONDecodeError
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from tfrobot.drive.tool.ides.dtos.workspace_edit import LSPWorkspaceEdit
from tfrobot.drive.tool.ides.environment.workspace.base import BaseWorkspace
from tfrobot.drive.tool.ides.environment.workspace.schema import (
    Range,
    SearchResult,
    SingleEditOperation,
    TextEdit,
)
from tfrobot.drive.tool.ides.schema import IDEAction


# Step 1: Define a concrete subclass for testing
class TestWorkspace(BaseWorkspace):
    def apply_workspace_edit(self, *, workspace_edit: LSPWorkspaceEdit) -> Any:
        pass

    def __init__(self, root_dir: str = "faker_dir", project_name: str = "faker_project", *args: Any, **kwargs: Any):
        super().__init__(*args, root_dir=root_dir, project_name=project_name, **kwargs)

    def _initial_lsp(self) -> None:
        pass

    def find_in_file(
        self,
        *,
        uri: str,
        query: str,
        search_scope: Range | list[Range] | None = None,
        is_regex: bool = False,
        match_case: bool = False,
        word_separator: str | None = None,
        capture_matches: bool = True,
        limit_result_count: int | None = None,
    ) -> list[SearchResult]:
        pass

    def apply_edit(
        self,
        *,
        uri: str,
        edits: Sequence[SingleEditOperation | dict],
        compute_undo_edits: bool = False,
    ) -> list[TextEdit] | None:
        pass

    def rename_file(
        self, *, old_uri: str, new_uri: str, overwrite: bool | None = None, ignore_if_exists: bool | None = None
    ):
        pass

    def delete_file(self, *, uri: str, recursive: bool | None = None, ignore_if_not_exists: bool | None = None) -> bool:
        pass

    def create_file(self, *, uri: str, overwrite: bool | None = None, ignore_if_exists: bool | None = None) -> bool:
        pass

    def open_file(self, *, file_path: str) -> None:
        pass

    def _launch_lsp(self) -> subprocess.Popen:
        # Return a MagicMock to simulate the LSP process
        process = MagicMock(spec=subprocess.Popen)
        process.stdin = MagicMock()
        process.stdin.write = MagicMock()
        process.stdin.flush = MagicMock()
        process.stdout = MagicMock()
        # 为 stdout 添加 fileno 方法，并返回一个假的文件描述符
        process.stdout.fileno = MagicMock(return_value=1)
        process.poll = MagicMock(return_value=None)
        return process

    def construct_action(self, action: dict) -> IDEAction:
        # Simple mock implementation
        return IDEAction.model_validate(action)

    def step(self, action: dict) -> tuple[dict, float, bool, bool, dict]:
        # Simple mock implementation
        return {}, 0.0, False, False, {}

    def render(self) -> str:
        # Simple mock implementation
        return "Render output"


# Step 2: Setup Pytest fixtures
@pytest.fixture
def workspace() -> TestWorkspace:
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = TestWorkspace(root_dir=tmp_dir)
        yield ws
        ws.close()


# Step 3: Write tests
def test_workspace_initialization(workspace: TestWorkspace):
    assert workspace._render_with_symbols is True


def test_read_lsp_output_handling(workspace: TestWorkspace):
    with patch("threading.Thread.start"):
        workspace._start_lsp_monitor_thread()
        assert workspace.lsp_output_monitor_thread is not None


def test_kill_lsp(workspace: TestWorkspace):
    workspace.kill_lsp()
    assert workspace.lsp is None


def test_close(workspace: TestWorkspace):
    workspace.close()
    assert workspace.lsp is None
    assert workspace.lsp_output_monitor_thread is None or not workspace.lsp_output_monitor_thread.is_alive()


# Test error handling in send_lsp_msg
def test_send_lsp_msg_without_server_running(workspace):
    workspace.lsp = None  # Simulate LSP server not running
    with pytest.raises(ValueError, match="LSP server is not running."):
        workspace.send_lsp_msg("initialize", {})


def test_send_lsp_msg_json_error(workspace):
    with patch.object(
        workspace.lsp.stdin,
        "write",
        side_effect=JSONDecodeError("Expecting value", "doc", 0),
    ):
        with pytest.raises(JSONDecodeError):
            workspace.send_lsp_msg("method", {"key": "value"})


# Test timeout and response handling in read_response
def test_read_response_timeout(workspace):
    response = workspace.read_response(999, timeout=0.1)  # Assuming 999 is not in lsp_server_response
    assert response is None


def test_read_response_successful(workspace):
    workspace.lsp_server_response[1] = "response"
    assert workspace.read_response(1) == "response"
    assert 1 not in workspace.lsp_server_response


# Test LSP server restart
def test_restart_lsp_server(workspace):
    old_process = workspace.lsp
    workspace.launch_lsp()
    assert workspace.lsp != old_process
    old_process.send_signal.assert_called_once()  # noqa
