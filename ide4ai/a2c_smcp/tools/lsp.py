"""MCP access to language-server status and explicit reload."""

from __future__ import annotations

from typing import Any

from ide4ai.a2c_smcp.tools.base import BaseTool


class LspTool(BaseTool):
    @property
    def name(self) -> str:
        return "Lsp"

    @property
    def description(self) -> str:
        return "查询当前语言服务器状态，或显式重新检测并重载语言服务器。"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["status", "reload"], "default": "status"}},
            "additionalProperties": False,
        }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.ide.workspace is None:
            raise RuntimeError("Workspace is not initialized")
        action = arguments.get("action", "status")
        if action == "reload":
            status = self.ide.workspace.reload_lsp()
        elif action == "status":
            status = self.ide.workspace.lsp_status
        else:
            raise ValueError(f"Unsupported LSP action: {action}")
        return {
            "state": status.state.value,
            "language_id": status.language_id,
            "reason": status.reason,
        }


__all__ = ["LspTool"]
