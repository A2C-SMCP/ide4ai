# filename: base.py
# @Time    : 2024/4/18 10:48
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
import json
import os.path
import subprocess
import threading
import weakref
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import gymnasium as gym
from gymnasium.core import RenderFrame
from loguru import logger
from lsprotocol import converters, types
from pydantic import AnyUrl
from typing_extensions import SupportsFloat

from ide4ai.dtos.diagnostics import DocumentDiagnosticReport, WorkspaceDiagnosticReport
from ide4ai.dtos.workspace_edit import LSPWorkspaceEdit
from ide4ai.environment.workspace.model import TextModel
from ide4ai.environment.workspace.schema import Position, Range, SearchResult, SingleEditOperation, TextEdit
from ide4ai.lsp.diagnostics import DiagnosticsRegistry
from ide4ai.lsp.errors import LspError
from ide4ai.lsp.manager import LanguageProfile, LspManager, LspSettings, LspStatus
from ide4ai.lsp.session import LspSession
from ide4ai.schema import ACTION_CATEGORY_MAP, IDEAction, IDEObs
from ide4ai.utils import is_subdirectory, list_directory_tree, render_symbols

LSP_CONVERTER = converters.get_converter()


class BaseWorkspace(gym.Env, ABC):
    """
    编辑工程文件的工作区

    1. 逐步支持LSP（当前尚未完全支持）
    2. 当前每个Workspace仅支持单一root_dir与project_name

    Attributes:
        name (str): The name of the environment.
        metadata (dict[str, Any]): The metadata of the environment.
        root_dir (str): The root directory of the workspace.
        project_name (str): The name of the project.
        models (list[Models]): The models of workspace. Models are at the heart of Monaco editor. It's what you interact
            with when managing content. A model represents a file that has been opened. This could represent a file that
            exists on a file system, but it doesn't have to. For example, the model holds the text content, determines
            the language of the content, and tracks the edit history of the content.
    """

    name: ClassVar[str]
    metadata: dict[str, Any] = {"render_modes": ["ansi"]}

    def __init__(
        self,
        root_dir: str,
        project_name: str,
        render_with_symbols: bool = True,
        max_active_models: int = 3,
        enable_simple_view_mode: bool = False,
        header_generators: dict[str, Callable[["BaseWorkspace", str], str]] | None = None,
        shortcut_commands: dict[str, list[str]] | None = None,
        diagnostics_timeout: float = 10.0,
        lsp_settings: LspSettings | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if not os.path.exists(root_dir):
            raise ValueError(f"项目根目录 {root_dir} 不存在")
        if not os.path.realpath(root_dir):
            raise ValueError("必须使用绝对路径作用项目根目录参数")
        self.root_dir = root_dir
        self.expand_folders: set[str] | Literal["all"] = set()
        self.project_name = project_name
        self.models: list[TextModel] = []
        self._active_models: OrderedDict[str, TextModel] = OrderedDict()
        self._lsp_lifecycle_lock = threading.RLock()
        self._lsp_session: LspSession | None = None
        self._diagnostics = DiagnosticsRegistry()
        self._lsp_open_documents: weakref.WeakKeyDictionary[LspSession, set[str]] = weakref.WeakKeyDictionary()
        self._lsp_response_condition = threading.Condition()
        self._lsp_response_cache: OrderedDict[int, str] = OrderedDict()
        self._lsp_response_failures: set[int] = set()
        self._lsp_generation = 0
        self._lsp_response_waiter_count = 0
        self._max_active_models = max_active_models
        self._render_with_symbols = render_with_symbols
        self._enable_simple_view_mode = enable_simple_view_mode
        # 诊断信息拉取超时时间（秒）/ Diagnostics pull timeout in seconds
        self._diagnostics_timeout = diagnostics_timeout
        self._lsp_manager = LspManager(
            self.root_dir,
            self._lsp_profiles(),
            settings=lsp_settings,
            request_timeout=diagnostics_timeout,
            initialize_session=self._initialize_managed_lsp_session,
        )
        self._is_closing = False
        self._is_closed = False
        # 初始化动作空间与观察空间
        self.action_space = gym.spaces.Dict(
            {
                "category": gym.spaces.Discrete(2),
                "action_name": gym.spaces.Text(100),
                "action_args": gym.spaces.Text(1000),
            },
        )
        self._action_category_map = ACTION_CATEGORY_MAP
        self.observation_space = gym.spaces.Dict(
            {
                "created_at": gym.spaces.Text(100),
                "obs": gym.spaces.Text(100000),
            },
        )
        self.header_generators: dict[str, Callable[[BaseWorkspace, str], str]] | None = header_generators
        self.shortcut_commands: dict[str, list[str]] | None = shortcut_commands

    def get_lsp_msg_id(self) -> int:
        """
        Get the next available message id for the Language Server Protocol (LSP) server.

        Returns:
            int: The next available message id.
        """
        return self._require_lsp_session().next_request_id()

    @property
    def lsp_status(self) -> LspStatus:
        """Return the selected language server state without starting it."""
        return self._lsp_manager.status

    def reload_lsp(self) -> LspStatus:
        """Explicitly re-detect the primary language without eager startup."""
        status = self._lsp_manager.reload()
        with self._lsp_lifecycle_lock:
            self._lsp_session = None
            self._invalidate_lsp_responses()
        return status

    def launch_lsp(self) -> None:
        """
        Launch the Language Server Protocol (LSP) server. Relaunch the LSP server if it is already running.

        Returns:
            None
        """
        if self._is_closed or self._is_closing:
            raise ValueError("Cannot launch LSP for a closed Workspace")
        if self._lsp_manager.session is not None:
            self._lsp_manager.reload()
        self._lsp_manager.start()

    def send_lsp_msg(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        message_id: int | None = None,
    ) -> str | None:
        """
        Send a message to the Language Server Protocol (LSP) server.

        通过stdin发送消息给LSP server

        Raises:
            ValueError: If the LSP server is not running.

        Args:
            method (str): The method of the message.
            params (dict[str, Any]): The parameters of the message. This parameter is optional and defaults to None.
            message_id (int): The message id. This parameter is optional and defaults to None. Request messages should
                include a message id. Notification messages should not include a message id.

        Returns:
            Optional[str]: The response of the LSP server.
        """
        with self._lsp_lifecycle_lock:
            session = self._require_lsp_session()
            generation = self._lsp_generation
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        if message_id is not None:
            message["id"] = message_id
            with self._lsp_response_condition:
                self._lsp_response_cache.pop(message_id, None)
                self._lsp_response_failures.discard(message_id)
            try:
                response = session.request(message, dict[str, Any], timeout=self._diagnostics_timeout)
            except BaseException:
                with self._lsp_response_condition:
                    if self._lsp_session is session and self._lsp_generation == generation:
                        self._lsp_response_cache.pop(message_id, None)
                        if len(self._lsp_response_failures) >= 1000:
                            self._lsp_response_failures.pop()
                        self._lsp_response_failures.add(message_id)
                        self._lsp_response_condition.notify_all()
                raise
            serialized = json.dumps(response)
            with self._lsp_response_condition:
                if self._lsp_session is session and self._lsp_generation == generation:
                    if len(self._lsp_response_cache) >= 1000:
                        self._lsp_response_cache.popitem(last=False)
                    self._lsp_response_cache[message_id] = serialized
                    self._lsp_response_condition.notify_all()
            return serialized
        session.notify(message)
        return None

    @abstractmethod
    def _initial_lsp(self) -> None:
        """
        初始化 LSP 服务

        Returns:

        """
        ...

    def read_response(self, request_id: int, timeout: float | None = 1) -> str | None:
        """Read a completed response without polling.

        ``send_lsp_msg`` remains synchronous, but responses are retained once
        for callers that use the historical send-then-read public API.
        """
        with self._lsp_response_condition:
            self._lsp_response_waiter_count += 1
            self._lsp_response_condition.notify_all()
            try:
                generation = self._lsp_generation
                available = self._lsp_response_condition.wait_for(
                    lambda: request_id in self._lsp_response_cache
                    or request_id in self._lsp_response_failures
                    or generation != self._lsp_generation,
                    timeout=timeout,
                )
                if not available or request_id in self._lsp_response_failures or generation != self._lsp_generation:
                    self._lsp_response_failures.discard(request_id)
                    return None
                return self._lsp_response_cache.pop(request_id)
            finally:
                self._lsp_response_waiter_count -= 1
                self._lsp_response_condition.notify_all()

    def read_notification(self, method: str, uri: str, timeout: float = 0.05) -> str | None:
        """
        Read the notification of the Language Server Protocol (LSP) server.

        Args:
            method (str): The method of the notification.
            uri (str): The URI of the notification about resource.
            timeout (float): The timeout value in seconds. This parameter is optional and defaults to 1.

        Returns:
            Optional[str]: The notification of the LSP server.
        """
        try:
            notification = self._require_lsp_session().wait_for_notification(method, uri=uri, timeout=timeout)
        except TimeoutError:
            return None
        return json.dumps(notification)

    def pull_diagnostics(
        self,
        uri: str | None = None,
        previous_result_id: str | None = None,
        previous_result_ids: list[dict[str, str]] | None = None,
        timeout: float = 1.0,
    ) -> DocumentDiagnosticReport | WorkspaceDiagnosticReport | None:
        """
        主动拉取诊断信息 / Pull diagnostics actively

        支持两种模式：
        1. 文档诊断（Document Diagnostics）：当提供 uri 参数时，拉取单个文档的诊断信息
        2. 工作区诊断（Workspace Diagnostics）：当 uri 为 None 时，拉取整个工作区的诊断信息

        Supports two modes:
        1. Document Diagnostics: Pull diagnostics for a single document when uri is provided
        2. Workspace Diagnostics: Pull diagnostics for entire workspace when uri is None

        Args:
            uri (str | None): 文档的URI，如果为None则拉取工作区诊断 / Document URI, pull workspace diagnostics if None
            previous_result_id (str | None): 上一次文档诊断的结果ID / Previous result ID for document diagnostics
            previous_result_ids (list[dict[str, str]] | None): 上一次工作区诊断的结果ID列表 /
                Previous result IDs for workspace diagnostics
            timeout (float): 超时时间（秒）/ Timeout in seconds

        Returns:
            DocumentDiagnosticReport | WorkspaceDiagnosticReport | None: 诊断报告，如果失败则返回None /
                Diagnostic report, or None if failed

        Examples:
            # 拉取单个文档的诊断 / Pull diagnostics for a single document
            doc_diagnostics = workspace.pull_diagnostics(uri="file:///path/to/file.py")

            # 拉取整个工作区的诊断 / Pull diagnostics for entire workspace
            workspace_diagnostics = workspace.pull_diagnostics()

            # 使用上一次的结果ID进行增量拉取 / Incremental pull with previous result ID
            doc_diagnostics = workspace.pull_diagnostics(
                uri="file:///path/to/file.py",
                previous_result_id="previous-id-123"
            )
        """
        from ide4ai.dtos.diagnostics import (
            RelatedFullDocumentDiagnosticReport,
            RelatedUnchangedDocumentDiagnosticReport,
        )

        session = self._require_lsp_session()
        request_id = session.next_request_id()
        try:
            if uri is not None:
                model = self.get_model(uri)
                if model is None:
                    return None
                requested_version = model.get_version_id()
                document_response = session.request(
                    types.DocumentDiagnosticRequest(
                        id=request_id,
                        params=types.DocumentDiagnosticParams(
                            text_document=types.TextDocumentIdentifier(uri=uri),
                            previous_result_id=previous_result_id,
                        ),
                    ),
                    types.DocumentDiagnosticResponse,
                    timeout=timeout,
                )
                result = document_response.result
                if result is None:
                    return None
                raw_result = LSP_CONVERTER.unstructure(result)
                if not isinstance(raw_result, dict):
                    logger.error("获取到非法文档诊断数据: {}", raw_result)
                    return None
                if raw_result.get("kind") == "full":
                    report: DocumentDiagnosticReport = RelatedFullDocumentDiagnosticReport.model_validate(raw_result)
                elif raw_result.get("kind") == "unchanged":
                    report = RelatedUnchangedDocumentDiagnosticReport.model_validate(raw_result)
                else:
                    logger.error("获取到未知文档诊断类型: {}", raw_result)
                    return None
                return report if self._diagnostics.record_pull(uri, requested_version, report) else None

            workspace_response = session.request(
                types.WorkspaceDiagnosticRequest(
                    id=request_id,
                    params=types.WorkspaceDiagnosticParams(
                        previous_result_ids=[
                            types.PreviousResultId(uri=item["uri"], value=item["value"])
                            for item in (previous_result_ids or [])
                        ]
                    ),
                ),
                types.WorkspaceDiagnosticResponse,
                timeout=timeout,
            )
            if workspace_response.result is None:
                return None
            raw_result = LSP_CONVERTER.unstructure(workspace_response.result)
            if not isinstance(raw_result, dict):
                logger.error("获取到非法工作区诊断数据: {}", raw_result)
                return None
            return WorkspaceDiagnosticReport.model_validate(raw_result)
        except LspError as exc:
            target = uri if uri else "workspace"
            logger.warning("拉取诊断信息失败 / Pull diagnostics failed for {}: {}", target, exc)
            return None

    def _lsp_command(self) -> Sequence[str]:
        """
        Return the command used to launch the Language Server Protocol server.

        Subclasses should override this hook. During the #18 transition, a
        subclass that only implements the historical ``_launch_lsp`` hook is
        still supported by discovering the command from that temporary
        process and immediately reclaiming it.

        Returns:
            Sequence[str]: Executable and arguments for the language server.
        """
        legacy_process = self._launch_lsp()
        command = legacy_process.args
        legacy_process.terminate()
        try:
            legacy_process.wait(timeout=self._diagnostics_timeout)
        except subprocess.TimeoutExpired:
            legacy_process.kill()
            legacy_process.wait(timeout=self._diagnostics_timeout)
        if isinstance(command, str):
            return (command,)
        if not isinstance(command, Sequence) or not all(isinstance(part, str) for part in command):
            raise TypeError("Legacy _launch_lsp() process must expose a string command in Popen.args")
        return tuple(cast(Sequence[str], command))

    def _lsp_profiles(self) -> Sequence[LanguageProfile]:
        """Return registered language profiles; subclasses opt in during #19."""
        return ()

    def _initialize_managed_lsp_session(self, session: LspSession) -> None:
        with self._lsp_lifecycle_lock:
            self._lsp_session = session
        session.add_close_callback(lambda error: self._on_lsp_session_closed(session, error))
        session.add_notification_handler("textDocument/publishDiagnostics", self._record_push_diagnostics)
        self._initial_lsp()
        self._sync_open_documents(session)

    def _record_push_diagnostics(self, message: dict[str, Any]) -> None:
        params = message.get("params")
        if isinstance(params, dict):
            self._diagnostics.record_push(params)

    def _track_document_version(self, uri: str, model: TextModel) -> None:
        self._diagnostics.track(uri, model.get_version_id())

    def _sync_open_documents(self, session: LspSession) -> None:
        for model in self.models:
            self._sync_open_document(session, model)

    def _sync_open_document(self, session: LspSession, model: TextModel) -> None:
        uri = str(model.uri)
        language_id = self._lsp_manager.language_for_path(Path(uri.removeprefix("file://")))
        if language_id is None or language_id != self._lsp_manager.primary_language_id:
            return
        session_documents = self._lsp_open_documents.setdefault(session, set())
        if uri in session_documents:
            return
        self._lsp_manager.did_open(
            session,
            uri=uri,
            language_id=language_id,
            version=model.get_version_id(),
            text=model.get_value(),
        )
        session_documents.add(uri)

    def _notify_lsp_change(
        self,
        session: LspSession,
        model: TextModel,
        changes: Sequence[types.TextDocumentContentChangePartial | types.TextDocumentContentChangeWholeDocument],
    ) -> None:
        self._lsp_manager.did_change(
            session,
            uri=str(model.uri),
            version=model.get_version_id(),
            changes=changes,
            full_text=model.get_value(),
        )

    def _close_lsp_document(self, session: LspSession | None, uri: str) -> None:
        self._diagnostics.forget(uri)
        if session is None:
            return
        documents = self._lsp_open_documents.get(session)
        if documents is None or uri not in documents:
            return
        self._lsp_manager.did_close(session, uri=uri)
        documents.discard(uri)

    def _ensure_lsp_for_uri(self, uri: str, *, semantic: bool = False) -> LspSession | None:
        path = Path(uri[7:]) if uri.startswith("file://") else Path(uri)
        language_id = self._lsp_manager.language_for_path(path)
        return self._lsp_manager.ensure_started(language_id=language_id, semantic=semantic)

    def _language_id_for_uri(self, uri: str) -> str:
        path = Path(uri[7:]) if uri.startswith("file://") else Path(uri)
        return self._lsp_manager.language_for_path(path) or "plaintext"

    def _launch_lsp(self) -> subprocess.Popen[bytes]:
        """Legacy LSP process hook retained until the public switch in #21."""
        raise NotImplementedError("Workspace subclasses must implement _lsp_command() or legacy _launch_lsp()")

    def _require_lsp_session(self) -> LspSession:
        session = self._lsp_manager.ensure_started(semantic=True)
        if session is None or not session.is_running:
            raise ValueError("LSP server is not running.")
        return session

    def get_model(self, uri: str) -> TextModel | None:
        """
        Get a model by URI.

        Args:
            uri (str): The URI of the model to be retrieved.

        Returns:
            Optional[TextModel]: The model instance.
        """
        return next(filter(lambda m: m.uri == AnyUrl(uri), self.models), None)

    @property
    def active_models(self) -> list[TextModel]:
        """
        Get the active models.

        Returns:
            list[TextModel]: The active models.
        """
        return list(self._active_models.values())

    def active_model(self, model_id: str) -> None:
        """
        激活一个Model

        Args:
            model_id (str): Model的ID

        Returns:
            None
        """
        if len(self._active_models) >= self._max_active_models:
            self._active_models.popitem(last=False)  # Remove the oldest item
        if not any(m.m_id == model_id for m in self.models):
            raise ValueError(f"Model with ID {model_id} does not exist in models, open it first.")
        self._active_models[model_id] = next(filter(lambda m: m.m_id == model_id, self.models))
        self._active_models.move_to_end(model_id)  # Ensure the latest added/activated model is at the end

    def deactivate_model(self, model_id: str) -> None:
        """
        取消激活一个Model

        Args:
            model_id (str): Model的ID

        Returns:
            None
        """
        if model_id in self._active_models:
            del self._active_models[model_id]

    def clear_active_models(self) -> None:
        """
        清空所有激活的Model

        Returns:
            None
        """
        self._active_models.clear()

    def kill_lsp(self) -> None:
        """
        Kill the Language Server Protocol (LSP) server.

        Returns:
            None
        """
        with self._lsp_lifecycle_lock:
            self._lsp_session = None
            self._invalidate_lsp_responses()
            self._lsp_manager.stop()

    def _on_lsp_session_closed(self, session: LspSession, error: BaseException) -> None:
        del error
        with self._lsp_response_condition:
            if self._lsp_session is session:
                self._invalidate_lsp_responses_locked()

    def _invalidate_lsp_responses(self) -> None:
        with self._lsp_response_condition:
            self._invalidate_lsp_responses_locked()

    def _invalidate_lsp_responses_locked(self) -> None:
        self._lsp_generation += 1
        self._lsp_response_cache.clear()
        self._lsp_response_failures.clear()
        self._lsp_response_condition.notify_all()

    def __del__(self) -> None:
        """

        Method Name: __del__

        Description:
        This method is called when the object is about to be destroyed and deallocated from memory. It invokes the
        `close()` method to perform any necessary cleanup operations.

        Parameters:
        self: The object instance on which the method is being called.

        Return Type:
        None

        """
        try:
            self.close()
        except Exception as e:
            # 在析构函数中捕获所有异常，避免影响垃圾回收
            # Catch all exceptions in destructor to avoid affecting garbage collection
            logger.error(f"析构时关闭环境出错 / Error closing environment in destructor: {e}")

    @abstractmethod
    def construct_action(self, action: dict) -> IDEAction:
        """
        Construct an instance of the IDEAction class from the provided action.

        Args:
            action (dict): A dictionary containing the action to be constructed.

        Returns:
            IDEAction: An instance of the IDEAction class representing the constructed action.
        """
        ...

    @abstractmethod
    def step(self, action: dict) -> tuple[dict, SupportsFloat, bool, bool, dict[str, Any]]:
        """
        执行一个动作

        Args:
            action (dict): An instance of the IDEAction class representing the action to be performed.

        Returns:
            A tuple containing the following elements:
            - An instance of the IDEObs class representing the observation after performing the action.
            - An instance of SupportsFloat representing the reward obtained after performing the action.
            - A boolean value indicating whether the current episode is done or not.
            - A boolean value indicating whether the action performed was successful or not.
            - A dictionary containing additional information about the action performed.

        """
        # Format action to be compatible with the IDEAction class
        ...

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[IDEObs, dict[str, Any]]:
        """
        重置环境
        将打开的文件关闭
        折叠所有展开的文件夹

        Args:
            seed: An integer value indicating the seed to be used for resetting. The seed is optional and defaults to
                None.

            options: A dictionary containing additional options for the reset operation. This parameter is optional and
                     defaults to None.

        Returns:
            A tuple containing two elements:
            1. An instance of the IDEObs class representing the initial
        """
        self._assert_not_closed()
        session = self._lsp_manager.session
        for m in self.models:
            self._close_lsp_document(session, str(m.uri))
            m.dispose()
        self.models.clear()
        self.clear_active_models()
        return super().reset(seed=seed)

    @abstractmethod
    def render(self, *, verbose: bool = False) -> RenderFrame | list[RenderFrame] | None:
        """
        渲染当前工作区状态 | Render current workspace state

        Args:
            verbose (bool): 是否使用详细模式。True时返回包含Python包/模块描述的丰富信息，False时返回简化版本
                           | Whether to use verbose mode. True returns rich info with Python package/module descriptions,
                           False returns simplified version

        Returns:
            RenderFrame | list[RenderFrame] | None: 渲染结果 | Render result
        """
        ...

    def close(self) -> None:
        """
        关闭环境

        Args:
            self: The current instance of the class.

        Returns:
            None
        """
        with self._lsp_lifecycle_lock:
            # 防止重复关闭
            if self._is_closed or self._is_closing:
                return

            self._is_closing = True

            try:
                # 清理所有模型
                for m in self.models:
                    try:
                        m.dispose()
                    except Exception as e:
                        logger.error(f"清理模型时出错 / Error disposing model: {e}")
                self.models.clear()

                self.kill_lsp()
                self._lsp_manager.close()
            except Exception as e:
                logger.error(f"关闭环境时出错 / Error closing environment: {e}")
            finally:
                self._is_closed = True
                self._is_closing = False

    def _assert_not_closed(self) -> bool:
        """
        Assert that the environment is not closed.

        Returns:
            bool: True if the environment is not closed, False otherwise.
        """
        if self._is_closed:
            raise ValueError("Environment is closed.")
        return True

    @abstractmethod
    def open_file(self, *, uri: str) -> TextModel:
        """
        Open a file in the workspace.
        Initial a model instance, add it to self.models and active it

        Args:
            uri (str): The uri to the file to be opened.

        Returns:
            TextModel: The model instance representing the opened file.
        """
        ...

    def save_file(self, *, uri: str) -> None:
        """
        Save a file in the workspace.

        Args:
            uri (str): The URI of the file to be saved.

        Returns:
            None
        """
        self._assert_not_closed()
        tm = next(filter(lambda m: m.uri == AnyUrl(uri), self.models), None)
        if tm:
            session = self._ensure_lsp_for_uri(uri)
            if session is not None:
                self._lsp_manager.will_save(session, uri=uri)
            tm.save()
            if session is not None:
                self._lsp_manager.did_save(session, uri=uri, text=tm.get_value())

    @abstractmethod
    def apply_edit(
        self,
        *,
        uri: str,
        edits: Sequence[SingleEditOperation | dict],
        compute_undo_edits: bool = False,
    ) -> tuple[list[TextEdit] | None, DocumentDiagnosticReport | None]:
        """
        Apply edits to a file in the workspace.

        Args:
            uri (str): The URI of the file to which the edits should be applied.
            edits (list[SingleEditOperation | dict]): The edits to be applied to the file.
            compute_undo_edits (bool): Whether to compute the undo edits. This parameter is optional and defaults to
                False.

        Returns:
            tuple[Optional[list[TextEdit]], Optional[DocumentDiagnosticReport]]:
                - The reverse edits that can be applied to undo the changes / 可用于撤销更改的反向编辑
                - Diagnostics result after editing / 编辑后的诊断结果
        """
        ...

    @abstractmethod
    def apply_workspace_edit(self, *, workspace_edit: LSPWorkspaceEdit) -> Any:
        """
        Apply a workspace edit to the workspace.

        Args:
            workspace_edit (LSPWorkspaceEdit): The workspace edit to be applied.

        Returns:
            Any: The result of applying the workspace edit.
        """
        ...

    @abstractmethod
    def rename_file(
        self,
        *,
        old_uri: str,
        new_uri: str,
        overwrite: bool | None = None,
        ignore_if_exists: bool | None = None,
    ) -> bool:
        """
        Rename a file in the workspace.

        Args:
            old_uri (str): 旧的URI信息
            new_uri (str): 新的URI信息
            overwrite (Optional[bool]): 如果文件存在是否覆盖。优先级高于ignore_if_exists
            ignore_if_exists (Optional[bool]): 如果文件存在是否忽略

        Returns:
            bool: 操作是否成功
        """
        ...

    @abstractmethod
    def delete_file(
        self,
        *,
        uri: str,
        recursive: bool | None = None,
        ignore_if_not_exists: bool | None = None,
    ) -> bool:
        """
        Delete a file in the workspace.

        Args:
            uri (str): The URI of the file to be deleted.
            recursive (Optional[bool]): Whether to delete the content recursively if a folder is denoted.
            ignore_if_not_exists (Optional[bool]): Whether to ignore the operation if the file does not exist.

        Returns:
            bool: True if the file was deleted successfully, False otherwise.
        """
        ...

    @abstractmethod
    def create_file(
        self,
        *,
        uri: str,
        overwrite: bool | None = None,
        ignore_if_exists: bool | None = None,
    ) -> tuple[TextModel | None, DocumentDiagnosticReport | None]:
        """
        Create a file in the workspace.

        Args:
            uri (str): The URI of the file to be created.
            overwrite (Optional[bool]): Whether to overwrite the target if it already exists.
            ignore_if_exists (Optional[bool]): Whether to ignore the operation if the file already exists.

        Returns:
            tuple[Optional[TextModel], Optional[DocumentDiagnosticReport]]:
                - The model instance representing the created file / 创建的文件模型实例
                - Diagnostics result after creation / 创建后的诊断结果
        """
        ...

    def close_file(self, *, uri: str) -> None:
        """
        Close a file in the workspace.

        Args:
            uri (str): The URI of the file to be closed.

        Returns:
            None
        """
        tm = next(filter(lambda m: m.uri == AnyUrl(uri), self.models), None)
        if tm:
            tm.dispose()
            self.deactivate_model(tm.m_id)
            self.models.remove(tm)
            session = self._ensure_lsp_for_uri(uri)
            self._close_lsp_document(session, uri)

    def read_file(
        self,
        *,
        uri: str,
        with_line_num: bool = True,
        code_range: Range | None = None,
    ) -> str:
        """
        Read the content of a file in the workspace.

        Notes:
            if current workspace enable simple view mode, with_line_num will be ignored, the response of this function
            will always contain line number.

        Args:
            uri (str): The URI of the file to be read.
            with_line_num (bool): 是否带有行号。默认为True。
            code_range (Optional[Range]): The range of the code to be read. This parameter is optional and defaults to
                None.

        Returns:
            str: The content of the file.
        """
        tm: TextModel | None = next(filter(lambda m: m.uri == AnyUrl(uri), self.models), None)
        if tm:
            return (
                tm.get_view(with_line_num, code_range)
                if not self._enable_simple_view_mode
                else tm.get_simple_view(code_range)
            )
        else:
            tm = self.open_file(uri=uri)
            return (
                tm.get_view(with_line_num, code_range)
                if not self._enable_simple_view_mode
                else tm.get_simple_view(code_range)
            )

    def expand_folder(self, *, uri: str) -> str:
        """
        Expand a folder in the workspace.

        Args:
            uri (str): The URI of the folder to be expanded.

        Returns:
            str: The directory info after expanding the folder.
        """
        if not uri.startswith("file://"):
            raise ValueError("URI must start with 'file://'")
        folder_path = uri[7:]
        if not os.path.realpath(folder_path) or not os.path.exists(folder_path):
            raise ValueError(f"Invalid folder path: {folder_path}")
        if not is_subdirectory(folder_path, self.root_dir):
            raise ValueError(f"Folder path {folder_path} is not a subdirectory of the root directory {self.root_dir}")
        if self.expand_folders != "all":
            self.expand_folders.add(folder_path)
        return list_directory_tree(folder_path, include_dirs=self.expand_folders, recursive=True)

    def glob_files(
        self,
        *,
        pattern: str,
        path: str | None = None,
    ) -> list[dict]:
        """
        使用通配符模式匹配文件 / Match files using glob pattern

        支持通配符模式，如 "**/*.js" 或 "src/**/*.ts"
        按修改时间排序返回匹配的文件路径

        Supports wildcard patterns like "**/*.js" or "src/**/*.ts"
        Returns matched file paths sorted by modification time

        Args:
            pattern (str): 用于匹配文件的通配符模式 / Glob pattern for matching files
            path (str | None): 要搜索的目录。若未指定，将使用工作区根目录 /
                              Directory to search. If not specified, uses workspace root

        Returns:
            List[dict]: 匹配的文件列表，每个包含路径和修改时间 /
                       List of matched files with path and modification time

        Examples:
            # 查找所有 Python 文件 / Find all Python files
            workspace.glob_files(pattern="**/*.py")

            # 在特定目录查找 / Search in specific directory
            workspace.glob_files(pattern="*.js", path="src")

            # 递归查找 TypeScript 文件 / Recursively find TypeScript files
            workspace.glob_files(pattern="**/*.ts")
        """
        self._assert_not_closed()

        # 确定搜索路径 / Determine search path
        search_path = Path(path) if path else Path(self.root_dir)

        # 如果是相对路径，转换为相对于工作区根目录的绝对路径 / If relative path, convert to absolute path relative to workspace root
        if not search_path.is_absolute():
            search_path = Path(self.root_dir) / search_path

        # 验证路径是否存在 / Validate path exists
        if not search_path.exists():
            raise ValueError(f"搜索路径不存在 / Search path does not exist: {search_path}")

        # 确保搜索路径在工作区内 / Ensure search path is within workspace
        if not is_subdirectory(str(search_path), self.root_dir):
            raise ValueError(f"搜索路径必须在工作区根目录内 / Search path must be within workspace root: {search_path}")

        # 执行 glob 匹配 / Perform glob matching
        matched_files = []
        for file_path in search_path.glob(pattern):
            if file_path.is_file():
                try:
                    mtime = os.path.getmtime(file_path)
                    matched_files.append(
                        {
                            "uri": f"file://{file_path.absolute()}",
                            "path": str(file_path.relative_to(self.root_dir)),
                            "mtime": mtime,
                        },
                    )
                except (OSError, ValueError) as e:
                    # 跳过无法访问的文件 / Skip inaccessible files
                    logger.warning(f"无法访问文件 / Cannot access file {file_path}: {e}")
                    continue

        # 按修改时间降序排序（最新的在前）/ Sort by modification time descending (newest first)
        matched_files.sort(key=lambda x: cast(float, x["mtime"]), reverse=True)

        return matched_files

    def collapse_folder(self, *, uri: str) -> str:
        """
        Collapse a folder in the workspace.

        Args:
            uri (str): The URI of the folder to be collapsed.

        Returns:
            None

        Raises:
            ValueError: If the URI does not start with 'file://' or the folder path is not expanded.
        """
        if not uri.startswith("file://"):
            raise ValueError("URI must start with 'file://'")
        folder_path = uri[7:]
        if self.expand_folders == "all":
            self.expand_folders = set()
        if folder_path in self.expand_folders:
            self.expand_folders.remove(folder_path)
        else:
            raise ValueError(f"Folder path {folder_path} is not expanded")
        return list_directory_tree(folder_path, include_dirs=self.expand_folders, recursive=True)

    def get_file_symbols(self, *, uri: str, kinds: list[int]) -> str:
        """
        Get the symbols in a file in the workspace.

        Args:
            uri (str): The URI of the file to get the symbols from.
            kinds (list[int]): The kinds of symbols to get.

        Returns:
            str: The symbols in the file.
        """
        self._assert_not_closed()
        session = self._require_lsp_session()
        try:
            response = session.request(
                types.DocumentSymbolRequest(
                    id=session.next_request_id(),
                    params=types.DocumentSymbolParams(text_document=types.TextDocumentIdentifier(uri=uri)),
                ),
                types.DocumentSymbolResponse,
            )
        except LspError as exc:
            return str(exc)
        if response.result is None:
            return "获取文件符号失败"
        raw_symbols = LSP_CONVERTER.unstructure(response.result)
        if not isinstance(raw_symbols, list):
            return "获取文件符号失败"
        res = render_symbols(cast(list[dict], raw_symbols), kinds)
        return res + "\n以上是文件的符号信息，每个信息后面跟着的是符号的位置信息，可以通过此位置信息与URI查询具体代码。"

    @abstractmethod
    def find_in_path(
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
        """
        在工作区中的文件或文件夹内查找查询字符串 / Find a query in a file or folder in the workspace.

        Args:
            uri (str): 要搜索的文件或文件夹的 URI。如果是文件夹，将递归搜索其中的所有文件 /
                      The URI of the file or folder to search in. If it's a folder, will recursively search all files within.
            query (str): 要搜索的查询字符串 / The query to search for.
            search_scope: 可选。指定搜索应在其中进行的范围或范围列表。仅当 uri 是文件时有效。如果未提供，
                则在整个文件范围内进行搜索 / Optional. The range or list of ranges where the search should be performed.
                Only valid when uri is a file. If not provided, the search will be performed in the full file range.
            is_regex: 可选。指定是否应将搜索字符串视为正则表达式。默认为 False /
                     Optional. Specifies whether the search string should be treated as a regular expression. Default is False.
            match_case: 可选。指定搜索是否应区分大小写。默认为 False /
                       Optional. Specifies whether the search should be case-sensitive. Default is False.
            word_separator: 可选。用于定义搜索中单词边界的分隔符。如果未提供，则所有字符都视为单词的一部分 /
                          Optional. The separator used to define word boundaries in the search. If not provided,
                          all characters are considered as part of a word.
            capture_matches: 可选。指定是否应在搜索结果中捕获匹配的文本内容。默认为 True /
                           Optional. Specifies whether the matched text should be captured in the search results. Default is True.
            limit_result_count: 可选。返回的搜索结果的最大数量。如果未提供，将返回所有匹配项 /
                              Optional. The maximum number of search results to return. If not provided, all matches will be returned.

        Returns:
            表示匹配结果的 SearchResult 对象列表。每个结果包含匹配的范围和文本（如果 capture_matches 为 True）/
            A list of SearchResult objects representing the matched results. Each result contains the matched range
            and text (if capture_matches is True).

        Raises:
            ValueError: 如果提供了无效的 URI 或搜索范围 / If an invalid URI or search scope is provided.

        Examples:
            # 在单个文件中搜索 / Search in a single file
            results = workspace.find_in_path(uri="file:///path/to/file.py", query="def")

            # 在文件夹中递归搜索 / Recursively search in a folder
            results = workspace.find_in_path(uri="file:///path/to/folder", query="TODO", match_case=True)

            # 使用正则表达式搜索 / Search with regex
            results = workspace.find_in_path(uri="file:///path/to/file.py", query=r"\\bclass\\s+\\w+", is_regex=True)
        """
        ...

    def replace_in_file(
        self,
        *,
        uri: str,
        query: str,
        replacement: str,
        search_scope: Range | list[Range] | None = None,
        is_regex: bool = False,
        match_case: bool = False,
        word_separator: str | None = None,
        compute_undo_edits: bool = False,
    ) -> tuple[list[TextEdit] | None, DocumentDiagnosticReport | None]:
        """
        在工作区的文件中替换查询字符串。
        Replace a query with a specified string in a file in the workspace.

        Args:
            uri (str): 要在其中执行替换的文件的 URI。| The URI of the file to perform the replacement in.
            query (str): 要搜索的查询字符串。| The query string to search for.
            replacement (str): 用于替换查询的字符串。| The string to replace the query with.
            search_scope: 可选。指定替换应在其中进行的范围或范围列表。如果未提供，则在整个模型范围内进行替换。|
                Optional. The range or list of ranges where the replacement should be performed. If not
                provided, the replacement will be performed in the full model range.
            is_regex: 可选。指定是否应将查询字符串视为正则表达式。默认为 False。|
                Optional. Specifies whether the query string should be treated as a regular expression. Default is False.
            match_case: 可选。指定替换是否应区分大小写。默认为 False。|
                Optional. Specifies whether the replacement should be case-sensitive. Default is False.
            word_separator: 可选。用于定义搜索和替换中单词边界的分隔符。如果未提供，则所有字符都视为单词的一部分。|
                Optional. The separator used to define word boundaries for the search and replacement. If
                not provided, all characters are considered as part of a word.
            compute_undo_edits: 可选。决定是否计算撤销编辑。默认为 False。|
                Optional. Specifies whether to compute the undo edits. Default is False.

        Returns:
            tuple[Optional[list[TextEdit]], Optional[DocumentDiagnosticReport]]:
                - 可用于撤销更改的反向编辑 / The reverse edits that can be applied to undo the changes
                - 编辑后的诊断结果 / Diagnostics result after editing
        """
        search_res = self.find_in_path(
            uri=uri,
            query=query,
            search_scope=search_scope,
            is_regex=is_regex,
            match_case=match_case,
            word_separator=word_separator,
        )
        if not search_res:
            return None, None
        edits = [SingleEditOperation(range=sr.range, text=replacement) for sr in search_res]
        undo_edits, diagnostics = self.apply_edit(uri=uri, edits=edits, compute_undo_edits=compute_undo_edits)
        return undo_edits, diagnostics

    def insert_cursor(self, *, uri: str, key: str, position: Position) -> str:
        """
        Inserts a cursor at the specified position in the given file.

        Args:
            uri (str): The URI of the file to insert the cursor into.
            key (str): The key associated with the cursor.
            position (Position): The position where the cursor should be inserted.

        Returns:
            str: The content near the inserted cursor.

        Raises:
            AssertionError: If the file is closed.
        """
        self._assert_not_closed()
        model = self.get_model(uri)
        if not model:
            model = self.open_file(uri=uri)
        near_content = model.insert_cursor(key=key, position=position)
        return near_content

    def delete_cursor(self, *, uri: str, key: str) -> str:
        """
        Args:
            uri (str): A string representing the URI of the file to perform the delete operation on.
            key (str): A string representing the key of the cursor to be deleted.

        Returns:
            str: A string representing the content near the deleted cursor position.

        Raises:
            AssertionError: If the database is closed.
            FileNotFoundError: If the specified file does not exist.

        """
        self._assert_not_closed()
        model = self.get_model(uri)
        if not model:
            model = self.open_file(uri=uri)
        near_content = model.delete_cursor(key=key)
        return near_content

    def clear_cursors(self, *, uri: str) -> str:
        """
        Clears all cursors in the given model.

        Args:
            uri (str): The URI of the model.

        Returns:
            str: The result of clearing the cursors.
        """
        self._assert_not_closed()
        model = self.get_model(uri)
        if not model:
            model = self.open_file(uri=uri)
        return model.clear_cursors()
