# filename: test_read_resource_anyurl_regression.py
# @Time    : 2026/06/22
# @Software: PyCharm
"""
read_resource AnyUrl 回归测试 | read_resource AnyUrl regression tests

复现并守护 Issue #13：mcp lowlevel 分发器恒以 ``AnyUrl`` 调用 read_resource handler，
而 handler 内部把 uri 当作 str 直接交给 urlparse，触发
``'AnyUrl' object has no attribute 'decode'``，导致任意 ``window://`` 资源读取必失败。

Reproduce and guard Issue #13: the mcp lowlevel dispatcher always invokes the
read_resource handler with an ``AnyUrl``; the handler treated uri as ``str`` and fed it to
urlparse, raising ``'AnyUrl' object has no attribute 'decode'`` and breaking every
``window://`` resource read.

这些测试直接驱动 server 注册到 ``request_handlers`` 的真实 handler（而非旁路直接调
WindowResource），因此精确复刻 a2c-computer 桌面刷新走过的崩溃路径。
These tests drive the real handler registered in ``request_handlers`` (instead of bypassing
to WindowResource directly), faithfully reproducing the crash path the a2c-computer desktop
refresh goes through.
"""

import mcp.types as mcp_types
import pytest
from confz import DataSource
from pydantic import AnyUrl

from ide4ai.a2c_smcp.cli import IDEMCPServer
from ide4ai.a2c_smcp.config import MCPServerConfig


@pytest.fixture
def server(tmp_path, request):
    """
    构造真实的 IDEMCPServer | Build a real IDEMCPServer

    IDEInstance 仅以 project_name 作 key（见 CLAUDE.md），同名会跨用例复用同一实例，
    而 fixture teardown 会 close 掉 IDE，导致后续用例拿到已关闭实例。故每个用例用唯一 project_name 隔离。
    IDEInstance is keyed only on project_name; reusing a name shares one (closed-after-teardown)
    instance across tests, so each test uses a unique project_name for isolation.
    """
    project_name = f"anyurl-regression-{request.node.name}"
    with MCPServerConfig.change_config_sources(
        DataSource(
            data={
                "transport": "stdio",
                "root_dir": str(tmp_path),
                "project_name": project_name,
            },
        ),
    ):
        config = MCPServerConfig()
        srv = IDEMCPServer(config)
        try:
            yield srv, config
        finally:
            srv.close()


async def _dispatch_read(server: IDEMCPServer, uri: AnyUrl) -> mcp_types.ReadResourceResult:
    """
    走 mcp lowlevel 注册的 handler 读取资源 | Read via the mcp lowlevel registered handler

    复刻 ``mcp/server/lowlevel/server.py`` 的分发：以 ``AnyUrl`` 注入 ``params.uri``。
    Mirrors the dispatch in ``mcp/server/lowlevel/server.py``: inject ``AnyUrl`` as ``params.uri``.
    """
    handler = server.server.request_handlers[mcp_types.ReadResourceRequest]
    req = mcp_types.ReadResourceRequest(
        method="resources/read",
        params=mcp_types.ReadResourceRequestParams(uri=uri),
    )
    result = await handler(req)
    # handler 返回 ServerResult，包装着 ReadResourceResult | handler returns ServerResult wrapping ReadResourceResult
    return result.root


class TestReadResourceAcceptsAnyUrl:
    """
    read_resource 必须接受 lowlevel 传入的 AnyUrl | read_resource must accept the AnyUrl from lowlevel
    """

    async def test_read_window_resource_with_query_params(self, server):
        """
        带查询参数的 window:// AnyUrl 应正常读取，而非触发 .decode 崩溃
        A window:// AnyUrl with query params must read normally, not crash on .decode
        """
        srv, config = server
        uri = AnyUrl(f"window://{config.project_name}?priority=0&fullscreen=true")

        result = await _dispatch_read(srv, uri)

        assert result.contents, "应返回非空内容 | should return non-empty contents"
        text = result.contents[0].text
        assert "IDE Content:" in text

    async def test_read_window_resource_bare_uri(self, server):
        """
        无查询参数的裸 AnyUrl 同样应正常读取 | A bare AnyUrl without query params must also read normally
        """
        srv, config = server
        uri = AnyUrl(f"window://{config.project_name}")

        result = await _dispatch_read(srv, uri)

        assert result.contents
        assert "IDE Content:" in result.contents[0].text

    async def test_read_window_resource_updates_params_from_anyurl(self, server):
        """
        通过 AnyUrl 传入不同参数时，update_from_uri 应被正确驱动并完成读取
        When different params arrive via AnyUrl, update_from_uri must be driven correctly and read succeeds
        """
        srv, config = server
        base_uri = f"window://{config.project_name}"
        resource = srv.resources[base_uri]

        # 用与当前不同的参数请求 | Request with params differing from current state
        uri = AnyUrl(f"{base_uri}?priority=80&fullscreen=false")
        result = await _dispatch_read(srv, uri)

        assert "IDE Content:" in result.contents[0].text
        # 参数应已下沉到资源实例 | Params should have been applied to the resource instance
        assert "priority=80" in resource.uri
        assert "fullscreen=false" in resource.uri
