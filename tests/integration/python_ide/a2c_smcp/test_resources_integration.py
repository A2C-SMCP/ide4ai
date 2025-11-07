# filename: test_resources_integration.py
# @Time    : 2025/11/04 17:12
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Resources 集成测试 | MCP Resources Integration Tests

测试真实的 PythonIDEMCPServer 中的资源注册和 list_resources 功能
Test resource registration and list_resources functionality in real PythonIDEMCPServer
"""

import pytest
from confz import DataSource

from ide4ai.a2c_smcp.config import MCPServerConfig
from ide4ai.python_ide.a2c_smcp.server import PythonIDEMCPServer


class TestResourcesIntegration:
    """
    资源集成测试 | Resources Integration Tests

    使用真实的 PythonIDEMCPServer 测试资源功能
    Test resource functionality using real PythonIDEMCPServer
    """

    def test_resources_registered(self, tmp_path):
        """
        测试资源已注册 | Test resources are registered
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": str(tmp_path),
                    "project_name": "test-resources",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 验证资源已注册 | Verify resources are registered
                assert len(server.resources) > 0

                # 验证窗口资源已注册 | Verify window resource is registered
                window_uri = f"window://{config.project_name}"
                assert window_uri in server.resources

                # 验证资源属性 | Verify resource properties
                window_resource = server.resources[window_uri]
                assert window_resource.name == f"IDE Window - {config.project_name}"
                assert "IDE 窗口内容" in window_resource.description
                assert window_resource.mime_type == "text/plain"

            finally:
                server.close()

    def test_resource_base_uri_format(self, tmp_path):
        """
        测试资源 base_uri 格式 | Test resource base_uri format
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": str(tmp_path),
                    "project_name": "test-base-uri",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 获取窗口资源 | Get window resource
                window_uri = f"window://{config.project_name}"
                window_resource = server.resources[window_uri]

                # 验证 base_uri 不包含查询参数 | Verify base_uri has no query params
                assert window_resource.base_uri == window_uri
                assert "?" not in window_resource.base_uri
                assert "priority" not in window_resource.base_uri
                assert "fullscreen" not in window_resource.base_uri

                # 验证完整 URI 包含查询参数 | Verify full URI has query params
                full_uri = window_resource.uri
                assert "priority=" in full_uri
                assert "fullscreen=" in full_uri

            finally:
                server.close()

    def test_resource_to_dict_format(self, tmp_path):
        """
        测试资源转换为字典格式（模拟 list_resources 返回）
        Test resource conversion to dict format (simulating list_resources return)
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": str(tmp_path),
                    "project_name": "test-to-dict",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 模拟 list_resources 的处理逻辑 | Simulate list_resources handler logic
                resources_list = []
                for resource in server.resources.values():
                    resource_dict = resource.to_dict()
                    resources_list.append(resource_dict)

                # 验证资源列表不为空 | Verify resource list is not empty
                assert len(resources_list) > 0

                # 验证第一个资源（窗口资源）| Verify first resource (window resource)
                window_resource_dict = resources_list[0]

                # 验证必需字段 | Verify required fields
                assert "uri" in window_resource_dict
                assert "name" in window_resource_dict
                assert "description" in window_resource_dict
                assert "mimeType" in window_resource_dict

                # 验证 URI 格式 | Verify URI format
                assert window_resource_dict["uri"].startswith("window://")
                assert config.project_name in window_resource_dict["uri"]
                assert "priority=" in window_resource_dict["uri"]
                assert "fullscreen=" in window_resource_dict["uri"]

                # 验证其他字段 | Verify other fields
                assert window_resource_dict["name"] == f"IDE Window - {config.project_name}"
                assert "IDE 窗口内容" in window_resource_dict["description"]
                assert window_resource_dict["mimeType"] == "text/plain"

            finally:
                server.close()

    @pytest.mark.asyncio
    async def test_resource_read_content(self, tmp_path):
        """
        测试资源内容读取 | Test resource content reading
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": str(tmp_path),
                    "project_name": "test-read-content",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 获取窗口资源 | Get window resource
                window_uri = f"window://{config.project_name}"
                window_resource = server.resources[window_uri]

                # 读取资源内容 | Read resource content
                content = await window_resource.read()

                # 验证内容格式 | Verify content format
                assert isinstance(content, str)
                assert "IDE Content:" in content

            finally:
                server.close()

    @pytest.mark.asyncio
    async def test_resource_dynamic_params_update(self, tmp_path):
        """
        测试资源动态参数更新 | Test resource dynamic parameter update
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": str(tmp_path),
                    "project_name": "test-dynamic-params",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 获取窗口资源 | Get window resource
                window_uri = f"window://{config.project_name}"
                window_resource = server.resources[window_uri]

                # 记录初始 URI | Record initial URI
                initial_uri = window_resource.uri
                assert "priority=0" in initial_uri
                assert "fullscreen=true" in initial_uri

                # 使用新参数更新 | Update with new parameters
                new_uri = f"{window_uri}?priority=80&fullscreen=false"
                window_resource.update_from_uri(new_uri)

                # 验证参数已更新 | Verify parameters updated
                updated_uri = window_resource.uri
                assert "priority=80" in updated_uri
                assert "fullscreen=false" in updated_uri

                # 验证 base_uri 保持不变 | Verify base_uri remains unchanged
                assert window_resource.base_uri == window_uri

                # 读取内容应该仍然正常工作 | Reading content should still work
                content = await window_resource.read()
                assert isinstance(content, str)
                assert "IDE Content:" in content

            finally:
                server.close()

    def test_multiple_resources_same_base_uri(self, tmp_path):
        """
        测试相同 base_uri 的资源共享实例 | Test resources with same base_uri share instance
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": str(tmp_path),
                    "project_name": "test-same-base",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 获取窗口资源 | Get window resource
                window_uri = f"window://{config.project_name}"
                window_resource = server.resources[window_uri]

                # 验证资源字典使用 base_uri 作为 key | Verify resource dict uses base_uri as key
                assert window_uri in server.resources
                assert window_resource.base_uri == window_uri

                # 即使完整 URI 包含查询参数，也应该使用 base_uri 查找
                # Even if full URI contains query params, should use base_uri for lookup
                full_uri_with_params = f"{window_uri}?priority=50&fullscreen=false"
                # 这个 URI 不应该在字典中 | This URI should not be in dict
                assert full_uri_with_params not in server.resources

            finally:
                server.close()

    def test_resource_list_format_matches_mcp_spec(self, tmp_path):
        """
        测试资源列表格式符合 MCP 规范 | Test resource list format matches MCP specification
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "stdio",
                    "root_dir": str(tmp_path),
                    "project_name": "test-mcp-spec",
                },
            ),
        ):
            config = MCPServerConfig()
            server = PythonIDEMCPServer(config)

            try:
                # 模拟 MCP list_resources 处理器 | Simulate MCP list_resources handler
                from mcp.types import Resource
                from pydantic import AnyUrl

                mcp_resources = []
                for resource in server.resources.values():
                    # 这是 BaseMCPServer._setup_handlers 中 list_resources 的实际逻辑
                    # This is the actual logic from list_resources in BaseMCPServer._setup_handlers
                    mcp_resource = Resource(
                        uri=AnyUrl(resource.uri),
                        name=resource.name,
                        description=resource.description,
                        mimeType=resource.mime_type,
                    )
                    mcp_resources.append(mcp_resource)

                # 验证可以成功创建 MCP Resource 对象 | Verify MCP Resource objects can be created
                assert len(mcp_resources) > 0

                # 验证第一个资源 | Verify first resource
                window_mcp_resource = mcp_resources[0]
                assert str(window_mcp_resource.uri).startswith("window://")
                assert window_mcp_resource.name == f"IDE Window - {config.project_name}"
                assert "IDE 窗口内容" in window_mcp_resource.description
                assert window_mcp_resource.mimeType == "text/plain"

            finally:
                server.close()
