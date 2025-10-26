# -*- coding: utf-8 -*-
# filename: workspace_edit.py
# @Time    : 2024/4/29 15:23
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from typing import Optional

from pydantic import BaseModel, Field

from ai_ide.dtos.file_resource import (
    LSPCreateFile,
    LSPDeleteFile,
    LSPRenameFile,
)
from ai_ide.dtos.text_documents import (
    LSPChangeAnnotation,
    LSPTextDocumentEdit,
    LSPTextEdit,
)


class LSPWorkspaceEdit(BaseModel):
    """
    A workspace edit represents changes to many resources managed in the workspace. The edit should either provide
    changes or documentChanges. If the client can handle versioned document edits and if documentChanges are present,
    the latter are preferred over changes.
    """

    changes: Optional[dict[str, list[LSPTextEdit]]] = None

    documentChanges: Optional[
        list[LSPTextDocumentEdit] | list[LSPTextDocumentEdit | LSPCreateFile | LSPRenameFile | LSPDeleteFile]
    ] = None

    change_annotations: Optional[dict[str, LSPChangeAnnotation]] = Field(
        default=None, validation_alias="changeAnnotations"
    )
