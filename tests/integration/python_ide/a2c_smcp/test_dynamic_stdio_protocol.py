"""Real stdio MCP regression coverage for the dynamic project catalog."""

from __future__ import annotations

import os
import sys
from typing import Any

import mcp.types as types
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
@pytest.mark.timeout(20)
async def test_stdio_catalog_changes_and_stale_tool_error(tmp_path) -> None:
    project_root = tmp_path / "project"
    second_root = tmp_path / "second-project"
    project_root.mkdir()
    second_root.mkdir()
    notifications: list[str] = []

    async def handle_message(message: Any) -> None:
        if isinstance(message, types.ServerNotification):
            notifications.append(message.root.method)

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ide4ai.a2c_smcp.cli"],
        cwd=os.getcwd(),
        env={
            **os.environ,
            "TRANSPORT": "stdio",
            "PROJECT_REGISTRY_PATH": str(tmp_path / "projects.json"),
        },
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream, message_handler=handle_message) as client:
            initialized = await client.initialize()
            assert initialized.capabilities.tools is not None
            assert initialized.capabilities.tools.listChanged is True
            assert initialized.capabilities.resources is not None
            assert initialized.capabilities.resources.listChanged is True

            initial_tools = await client.list_tools()
            assert [tool.name for tool in initial_tools.tools] == [
                "project_create",
                "project_delete",
                "project_list",
                "project_switch",
            ]
            assert (await client.list_resources()).resources == []

            missing = await client.call_tool("project_switch", {"name": "does-not-exist"})
            assert missing.isError is True
            assert missing.structuredContent is not None
            assert missing.structuredContent["error"]["code"] == "PROJECT_NOT_FOUND"
            malformed = await client.call_tool("project_switch", {"project_id": "not-a-uuid"})
            assert malformed.isError is True
            assert malformed.structuredContent is not None
            assert malformed.structuredContent["error"]["code"] == "TOOL_INPUT_VALIDATION_FAILED"
            assert notifications == []

            created = await client.call_tool(
                "project_create",
                {"name": "stdio-project", "root_dir": str(project_root)},
            )
            assert created.isError is False
            assert created.structuredContent is not None
            project_id = created.structuredContent["project"]["id"]
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()

            selected_tools = await client.list_tools()
            selected_names = {tool.name for tool in selected_tools.tools}
            assert {"Glob", "Lsp", "project_unload"} <= selected_names
            invalid = await client.call_tool("Glob", {})
            assert invalid.isError is True
            assert invalid.structuredContent is not None
            assert invalid.structuredContent["error"]["code"] == "TOOL_INPUT_VALIDATION_FAILED"
            unloaded_after_invalid = await client.call_tool("project_unload", {})
            assert unloaded_after_invalid.structuredContent is not None
            assert unloaded_after_invalid.structuredContent["unloaded"] is False
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()
            resources = await client.list_resources()
            assert len(resources.resources) == 1
            assert str(resources.resources[0].uri).startswith(f"window://{project_id}")
            rendered = await client.read_resource(resources.resources[0].uri)
            assert rendered.contents

            second = await client.call_tool(
                "project_create",
                {"name": "second-project", "root_dir": str(second_root)},
            )
            assert second.structuredContent is not None
            second_id = second.structuredContent["project"]["id"]
            await client.call_tool("project_list", {})
            assert notifications == []

            switched = await client.call_tool("project_switch", {"project_id": second_id})
            assert switched.isError is False
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()

            deleted_second = await client.call_tool("project_delete", {"project_id": second_id})
            assert deleted_second.isError is False
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()

            deleted_first = await client.call_tool("project_delete", {"project_id": project_id})
            assert deleted_first.isError is False
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()
            # Even arguments invalid under the old cached Glob schema must report
            # disappearance, rather than an SDK input-validation error.
            stale = await client.call_tool("Glob", {})
            assert stale.isError is True
            assert stale.structuredContent is not None
            assert stale.structuredContent["error"]["code"] == "TOOL_NOT_AVAILABLE_FOR_CURRENT_PROJECT"
