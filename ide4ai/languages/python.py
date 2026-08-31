"""Python language profile and presentation hooks."""

from __future__ import annotations

import datetime
import os
from typing import TYPE_CHECKING

from ide4ai.languages.python_utils import get_minimal_expanded_tree_with_desc, list_directory_tree_with_desc
from ide4ai.lsp.manager import LanguageProfile, LspServerSpec

if TYPE_CHECKING:
    from ide4ai.environment.workspace.base import BaseWorkspace


PYTHON_SYMBOL_VALUE_SET = [5, 6, 7, 8, 10]

PYTHON_CLIENT_CAPABILITIES: dict[str, object] = {
    "general": {"positionEncodings": ["utf-8", "utf-16"]},
    "textDocument": {
        "synchronization": {"dynamicRegistration": False, "willSave": True, "didSave": True},
        "publishDiagnostics": {
            "relatedInformation": True,
            "versionSupport": True,
            "codeDescriptionSupport": True,
            "dataSupport": True,
        },
        "diagnostic": {"dynamicRegistration": False, "relatedDocumentSupport": True},
        "documentSymbol": {"symbolKind": {"valueSet": PYTHON_SYMBOL_VALUE_SET}},
    },
}


def python_language_profile(command: tuple[str, ...] = ("pyright-langserver", "--stdio")) -> LanguageProfile:
    return LanguageProfile(
        language_id="python",
        file_extensions=(".py", ".pyi"),
        root_markers=("pyproject.toml", "pyrightconfig.json", "setup.py", "requirements.txt", "Pipfile"),
        server=LspServerSpec(command),
        client_capabilities=PYTHON_CLIENT_CAPABILITIES,
        initialization_options={"disablePullDiagnostics": False},
        header_generators={".py": default_python_header_generator},
        symbol_kinds=tuple(PYTHON_SYMBOL_VALUE_SET),
        verbose_directory_tree=list_directory_tree_with_desc,
        verbose_minimal_tree=get_minimal_expanded_tree_with_desc,
    )


def default_python_header_generator(workspace: BaseWorkspace, file_path: str) -> str:
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    return (
        f"# -*- coding: utf-8 -*-\n"
        f"# filename : {os.path.basename(file_path)}\n"
        f"# @Time    : {now.strftime('%Y/%m/%d %H:%M')}\n"
        f"# @Author  : TuringFocus\n"
        f"# @Email   : support@turingfocus.com\n"
        f"# @Software: {workspace.project_name}\n"
    )


__all__ = [
    "PYTHON_CLIENT_CAPABILITIES",
    "PYTHON_SYMBOL_VALUE_SET",
    "default_python_header_generator",
    "python_language_profile",
]
