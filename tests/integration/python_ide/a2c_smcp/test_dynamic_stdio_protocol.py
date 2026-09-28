"""Real stdio MCP regression coverage for the dynamic project catalog."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import anyio
import mcp.types as types
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import McpError
from pydantic import AnyUrl

SHELL_OVERVIEW_URI = "window://io.github.a2c-smcp.tfbash/shell-overview"


@pytest.mark.asyncio
@pytest.mark.timeout(40)
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
            assert initialized.capabilities.resources.subscribe is True

            initial_tools = await client.list_tools()
            assert [tool.name for tool in initial_tools.tools] == [
                "project_create",
                "project_delete",
                "project_list",
                "project_switch",
            ]
            switch_tool = next(tool for tool in initial_tools.tools if tool.name == "project_switch")
            assert switch_tool.inputSchema["required"] == ["name"]
            assert set(switch_tool.inputSchema["properties"]) == {"name"}
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
            assert "id" not in created.structuredContent["project"]
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()

            selected_tools = await client.list_tools()
            selected_names = {tool.name for tool in selected_tools.tools}
            assert {"Glob", "Lsp", "terminal_start", "project_unload"} <= selected_names
            assert "Bash" not in selected_names
            assert not any(name.startswith("shell_") for name in selected_names)

            terminal_enabled = await client.call_tool(
                "terminal_start",
                {"startup_command": "export IDE4AI_STARTUP=ready"},
            )
            assert terminal_enabled.isError is False
            assert terminal_enabled.structuredContent is not None
            assert terminal_enabled.structuredContent["terminal"] == {
                "enabled": True,
                "state": "open",
                "root_dir": str(project_root),
                "configuration": {
                    "cwd": str(project_root),
                    "shell": None,
                    "startup_command_configured": True,
                    "environment_override_count": 0,
                    "command_timeout_ms": 120_000,
                    "shutdown_grace_ms": 3_000,
                    "close_timeout_ms": 5_000,
                },
            }
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()

            enabled_names = {tool.name for tool in (await client.list_tools()).tools}
            assert {name for name in enabled_names if name.startswith("shell_")} == {
                "shell_open",
                "shell_exec",
                "shell_read",
                "shell_write",
                "shell_signal",
                "shell_list",
                "shell_close",
            }
            opened = await client.call_tool("shell_open", {})
            assert opened.isError is False
            assert opened.structuredContent is not None
            assert opened.structuredContent["cwd"] == str(project_root)
            shell_id = opened.structuredContent["shell_id"]
            executed = await client.call_tool(
                "shell_exec",
                {"shell_id": shell_id, "command": 'printf \'%s:%s\' "$PWD" "$IDE4AI_STARTUP"'},
            )
            assert executed.isError is False
            assert executed.structuredContent is not None
            assert executed.structuredContent["output"].rstrip("\r\n") == f"{project_root}:ready"
            shell_list = await client.call_tool("shell_list", {})
            assert shell_list.isError is False
            assert shell_list.structuredContent is not None
            assert shell_list.structuredContent["host"]["workspace_root"] == str(project_root)

            invalid = await client.call_tool("Glob", {})
            assert invalid.isError is True
            assert invalid.structuredContent is not None
            assert invalid.structuredContent["error"]["code"] == "TOOL_INPUT_VALIDATION_FAILED"
            assert invalid.structuredContent["error"]["project_name"] == "stdio-project"
            assert "project_id" not in invalid.structuredContent["error"]
            unloaded_after_invalid = await client.call_tool("project_unload", {})
            assert unloaded_after_invalid.structuredContent is not None
            assert unloaded_after_invalid.structuredContent["unloaded"] is False
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()
            stale_shell = await client.call_tool("shell_list", {})
            assert stale_shell.isError is True
            assert stale_shell.structuredContent is not None
            assert stale_shell.structuredContent["error"]["code"] == "TOOL_NOT_AVAILABLE_FOR_CURRENT_PROJECT"
            resources = await client.list_resources()
            assert len(resources.resources) == 1
            assert str(resources.resources[0].uri).startswith("window://")
            rendered = await client.read_resource(resources.resources[0].uri)
            assert rendered.contents

            second = await client.call_tool(
                "project_create",
                {"name": "second-project", "root_dir": str(second_root)},
            )
            assert second.structuredContent is not None
            assert "id" not in second.structuredContent["project"]
            listed = await client.call_tool("project_list", {})
            assert listed.structuredContent is not None
            assert all("id" not in project for project in listed.structuredContent["projects"])
            assert all("current" not in project for project in listed.structuredContent["projects"])
            assert listed.structuredContent["current_project"] == "stdio-project"
            assert notifications == []

            switched = await client.call_tool("project_switch", {"name": "second-project"})
            assert switched.isError is False
            assert switched.structuredContent is not None
            assert "id" not in switched.structuredContent["project"]
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()

            deleted_second = await client.call_tool("project_delete", {"name": "second-project"})
            assert deleted_second.isError is False
            assert deleted_second.structuredContent is not None
            assert "id" not in deleted_second.structuredContent["project"]
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            notifications.clear()

            deleted_first = await client.call_tool("project_delete", {"name": "stdio-project"})
            assert deleted_first.isError is False
            assert deleted_first.structuredContent is not None
            assert "id" not in deleted_first.structuredContent["project"]
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


@pytest.mark.asyncio
@pytest.mark.timeout(40)
async def test_stdio_tfbash_runtimes_are_isolated_per_project(tmp_path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
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
        async with ClientSession(read_stream, write_stream) as client:
            await client.initialize()
            await client.call_tool("project_create", {"name": "first", "root_dir": str(first_root)})
            await client.call_tool("terminal_start", {})
            first_open = await client.call_tool("shell_open", {})
            assert first_open.structuredContent is not None
            first_shell_id = first_open.structuredContent["shell_id"]
            first_extra = await client.call_tool("shell_open", {})
            assert not first_extra.isError and first_extra.structuredContent is not None
            first_shell_ids = {first_shell_id, first_extra.structuredContent["shell_id"]}
            assert len(first_shell_ids) == 2
            first_output = await client.call_tool(
                "shell_exec", {"shell_id": first_shell_id, "command": "echo FIRST_ONLY"}
            )
            assert not first_output.isError and first_output.structuredContent is not None
            assert first_output.structuredContent["output"].strip() == "FIRST_ONLY"

            await client.call_tool("project_create", {"name": "second", "root_dir": str(second_root)})
            await client.call_tool("project_switch", {"name": "second"})
            second_initial_names = {tool.name for tool in (await client.list_tools()).tools}
            assert not any(name.startswith("shell_") for name in second_initial_names)
            await client.call_tool("terminal_start", {})
            second_open = await client.call_tool("shell_open", {})
            assert second_open.structuredContent is not None
            assert second_open.structuredContent["cwd"] == str(second_root)
            second_extra = await client.call_tool("shell_open", {})
            assert not second_extra.isError and second_extra.structuredContent is not None
            second_shell_ids = {second_open.structuredContent["shell_id"], second_extra.structuredContent["shell_id"]}
            assert len(second_shell_ids) == 2 and first_shell_ids.isdisjoint(second_shell_ids)
            second_output = await client.call_tool(
                "shell_exec", {"shell_id": second_open.structuredContent["shell_id"], "command": "echo SECOND_ONLY"}
            )
            assert not second_output.isError and second_output.structuredContent is not None
            assert second_output.structuredContent["output"].strip() == "SECOND_ONLY"
            foreign_shell = await client.call_tool("shell_read", {"shell_id": first_shell_id})
            assert foreign_shell.isError

            await client.call_tool("project_switch", {"name": "first"})
            first_list = await client.call_tool("shell_list", {})
            assert first_list.structuredContent is not None
            assert first_list.structuredContent["host"]["workspace_root"] == str(first_root)
            assert {shell["shell_id"] for shell in first_list.structuredContent["shells"]} == first_shell_ids

            await client.call_tool("terminal_close", {})
            await client.call_tool("project_switch", {"name": "second"})
            second_list = await client.call_tool("shell_list", {})
            assert not second_list.isError and second_list.structuredContent is not None
            assert {shell["shell_id"] for shell in second_list.structuredContent["shells"]} == second_shell_ids
            await client.call_tool("terminal_close", {})


@pytest.mark.asyncio
@pytest.mark.timeout(40)
async def test_stdio_terminal_close_force_kills_running_shell_after_grace_period(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    pid_file = project_root / "shell.pid"
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
            await client.initialize()
            await client.call_tool("project_create", {"name": "close-running", "root_dir": str(project_root)})
            started = await client.call_tool(
                "terminal_start",
                {"shutdown_grace_ms": 100, "close_timeout_ms": 1_500},
            )
            assert started.isError is False
            opened = await client.call_tool("shell_open", {})
            assert opened.structuredContent is not None

            running = await client.call_tool(
                "shell_exec",
                {
                    "shell_id": opened.structuredContent["shell_id"],
                    "command": "trap '' TERM; echo $$ > shell.pid; while :; do sleep 1; done",
                    "yield_ms": 250,
                    "timeout_ms": 30_000,
                },
            )
            assert running.isError is False
            assert running.structuredContent is not None
            assert running.structuredContent["status"] == "running"
            shell_pid = int(pid_file.read_text().strip())
            os.kill(shell_pid, 0)

            notifications.clear()
            close_started = time.monotonic()
            closed = await client.call_tool("terminal_close", {})
            close_elapsed = time.monotonic() - close_started

            assert closed.isError is False
            assert close_elapsed < 3
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            tool_names = {tool.name for tool in (await client.list_tools()).tools}
            assert "terminal_start" in tool_names
            assert "terminal_close" not in tool_names
            assert not any(name.startswith("shell_") for name in tool_names)

            for _ in range(20):
                try:
                    os.kill(shell_pid, 0)
                except ProcessLookupError:
                    break
                await anyio.sleep(0.05)
            else:
                pytest.fail(f"terminal_close left shell process {shell_pid} running")


@pytest.mark.asyncio
@pytest.mark.timeout(40)
async def test_stdio_shell_overview_resource_follows_terminal_and_streams_updates(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    notifications: list[str] = []
    updated_uris: list[str] = []
    resource_updated = anyio.Event()

    async def handle_message(message: Any) -> None:
        if not isinstance(message, types.ServerNotification):
            return
        notifications.append(message.root.method)
        if isinstance(message.root, types.ResourceUpdatedNotification):
            updated_uris.append(str(message.root.params.uri))
            resource_updated.set()

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
            assert initialized.capabilities.resources is not None
            assert initialized.capabilities.resources.subscribe is True
            await client.call_tool("project_create", {"name": "overview", "root_dir": str(project_root)})
            initial_resources = await client.list_resources()
            assert all(str(resource.uri) != SHELL_OVERVIEW_URI for resource in initial_resources.resources)

            notifications.clear()
            started = await client.call_tool("terminal_start", {})
            assert started.isError is False
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            resources = await client.list_resources()
            overview = next(resource for resource in resources.resources if str(resource.uri) == SHELL_OVERVIEW_URI)
            assert overview.name == "Shell Overview"
            assert overview.description == "Current Shell states and recent execution output."
            assert overview.mimeType == "text/markdown"
            assert overview.annotations is not None
            assert overview.annotations.priority == 0.8
            assert overview.annotations.audience == ["assistant"]
            assert overview.meta == {"fullscreen": False}

            await client.subscribe_resource(overview.uri)
            notifications.clear()
            opened = await client.call_tool("shell_open", {})
            assert opened.isError is False
            assert opened.structuredContent is not None
            with anyio.fail_after(3):
                await resource_updated.wait()
            assert updated_uris == [SHELL_OVERVIEW_URI]

            rendered = await client.read_resource(overview.uri)
            assert len(rendered.contents) == 1
            assert isinstance(rendered.contents[0], types.TextResourceContents)
            assert rendered.contents[0].mimeType == "text/markdown"
            assert opened.structuredContent["shell_id"] in rendered.contents[0].text
            assert str(project_root) in rendered.contents[0].text
            with pytest.raises(McpError, match="Unknown Resource URI"):
                await client.read_resource(AnyUrl(f"{SHELL_OVERVIEW_URI}?unexpected=true"))

            await client.unsubscribe_resource(overview.uri)
            notifications.clear()
            updated_uris.clear()
            resource_updated = anyio.Event()
            executed = await client.call_tool(
                "shell_exec",
                {"shell_id": opened.structuredContent["shell_id"], "command": "printf updated"},
            )
            assert executed.isError is False
            with anyio.move_on_after(0.4) as no_update:
                await resource_updated.wait()
            assert no_update.cancel_called is True
            assert updated_uris == []

            await client.subscribe_resource(overview.uri)
            notifications.clear()
            resource_updated = anyio.Event()
            closed = await client.call_tool("terminal_close", {})
            assert closed.isError is False
            assert notifications == [
                "notifications/tools/list_changed",
                "notifications/resources/list_changed",
            ]
            remaining = await client.list_resources()
            assert all(str(resource.uri) != SHELL_OVERVIEW_URI for resource in remaining.resources)
            with anyio.move_on_after(0.4) as no_late_update:
                await resource_updated.wait()
            assert no_late_update.cancel_called is True
            with pytest.raises(McpError):
                await client.read_resource(overview.uri)
            await client.unsubscribe_resource(overview.uri)
