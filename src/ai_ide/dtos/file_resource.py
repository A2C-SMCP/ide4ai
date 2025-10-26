# -*- coding: utf-8 -*-
# filename: file_resource.py
# @Time    : 2024/4/29 15:03
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LSPCreateFileOptions(BaseModel):
    """
    LSPCreateFileOptions
    """

    # Overwrite existing file.
    overwrite: Optional[bool] = None
    # Ignore if file already exists.
    ignore_if_exists: Optional[bool] = Field(None, validation_alias="ignoreIfExists")


class LSPCreateFile(BaseModel):
    """
    LSPCreateFile
    """

    kind: Literal["create"] = "create"
    # The resource to create.
    uri: str
    # Additional options
    options: Optional[LSPCreateFileOptions] = None
    # An optional annotation identifier describing the operation.
    annotation_id: Optional[str] = Field(None, validation_alias="annotationId")


class LSPRenameFileOptions(BaseModel):
    """
    LSPRenameFileOptions
    """

    # Overwrite target if existing. Overwrite wins over `ignoreIfExists`
    overwrite: Optional[bool] = None
    # Ignores if target exists.
    ignore_if_exists: Optional[bool] = Field(None, validation_alias="ignoreIfExists")


class LSPRenameFile(BaseModel):
    """
    LSPRenameFile
    """

    kind: Literal["rename"] = "rename"
    # The old (existing) location.
    old_uri: str = Field(..., validation_alias="oldUri")
    # The new location.
    new_uri: str = Field(..., validation_alias="newUri")
    # Additional options
    options: Optional[LSPRenameFileOptions] = None
    # An optional annotation identifier describing the operation.
    annotation_id: Optional[str] = Field(None, validation_alias="annotationId")


class LSPDeleteFileOptions(BaseModel):
    """
    LSPDeleteFileOptions
    """

    # Delete the content recursively if a folder is denoted.
    recursive: Optional[bool] = None
    # Ignore the operation if the file doesn't exist.
    ignore_if_not_exists: Optional[bool] = Field(None, validation_alias="ignoreIfNotExists")


class LSPDeleteFile(BaseModel):
    """
    LSPDeleteFile
    """

    kind: Literal["delete"] = "delete"
    # The file to delete.
    uri: str
    # Additional options
    options: Optional[LSPDeleteFileOptions] = None
    # An optional annotation identifier describing the operation.
    annotation_id: Optional[str] = Field(None, validation_alias="annotationId")
