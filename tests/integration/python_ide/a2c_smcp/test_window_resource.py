# filename: test_window_resource.py
# @Time    : 2025/11/04 16:48
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
Window Resource 集成测试 | Window Resource Integration Tests

测试 WindowResource 的功能和 MCP Server 集成
Test WindowResource functionality and MCP Server integration
"""

import pytest

from ide4ai.a2c_smcp.resources import WindowResource
from ide4ai.python_ide.ide import PythonIDE


@pytest.fixture
def python_ide(tmp_path):
    """
    创建 PythonIDE 实例 | Create PythonIDE instance
    """
    ide = PythonIDE(
        root_dir=str(tmp_path),
        project_name="test-project",
        cmd_time_out=5,
    )
    yield ide
    ide.close()


class TestWindowResource:
    """
    WindowResource 集成测试 | WindowResource Integration Tests
    """

    def test_window_resource_uri_format(self, python_ide):
        """
        测试 Window Resource URI 格式 | Test Window Resource URI format
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 验证 URI 格式符合 window:// 协议规范 | Verify URI format follows window:// protocol
        uri = resource.uri
        assert uri.startswith("window://test-project?")
        assert "priority=0" in uri
        assert "fullscreen=true" in uri

    def test_window_resource_basic(self, python_ide):
        """
        测试基本的 Window Resource 功能 | Test basic Window Resource functionality
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=False)

        # 验证资源属性 | Verify resource properties
        assert resource.name == "IDE Window - test-project"
        assert "IDE 窗口内容" in resource.description
        assert resource.mime_type == "text/plain"

        # 验证 URI | Verify URI
        uri = resource.uri
        assert "window://test-project" in uri
        assert "priority=50" in uri
        assert "fullscreen=false" in uri

    def test_window_resource_invalid_priority(self, python_ide):
        """
        测试无效的 priority 参数 | Test invalid priority parameter
        """
        # priority 超出范围 | priority out of range
        with pytest.raises(ValueError, match="priority must be int in"):
            WindowResource(python_ide, priority=150, fullscreen=True)

        # priority 为负数 | priority is negative
        with pytest.raises(ValueError, match="priority must be int in"):
            WindowResource(python_ide, priority=-1, fullscreen=True)

    @pytest.mark.asyncio
    async def test_window_resource_read(self, python_ide):
        """
        测试 Window Resource 读取功能 | Test Window Resource read functionality
        """
        resource = WindowResource(python_ide)

        # 读取资源内容 | Read resource content
        content = await resource.read()

        # 验证内容包含 IDE 渲染信息 | Verify content contains IDE render information
        assert isinstance(content, str)
        assert "IDE Content:" in content

    @pytest.mark.asyncio
    async def test_window_resource_to_dict(self, python_ide):
        """
        测试 Window Resource 字典转换 | Test Window Resource dictionary conversion
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=False)

        # 转换为字典 | Convert to dictionary
        resource_dict = resource.to_dict()

        # 验证字典内容 | Verify dictionary content
        assert "uri" in resource_dict
        assert "name" in resource_dict
        assert "description" in resource_dict
        assert "mimeType" in resource_dict
        assert resource_dict["mimeType"] == "text/plain"
        assert "window://test-project" in resource_dict["uri"]

    def test_window_resource_base_uri(self, python_ide):
        """
        测试 base_uri 不包含查询参数 | Test base_uri without query parameters
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=True)

        # 验证 base_uri 不包含查询参数 | Verify base_uri has no query parameters
        base_uri = resource.base_uri
        assert base_uri == "window://test-project"
        assert "?" not in base_uri
        assert "priority" not in base_uri
        assert "fullscreen" not in base_uri

        # 验证完整 URI 包含查询参数 | Verify full URI has query parameters
        full_uri = resource.uri
        assert "priority=50" in full_uri
        assert "fullscreen=true" in full_uri

    def test_window_resource_update_from_uri(self, python_ide):
        """
        测试从 URI 更新资源参数 | Test updating resource parameters from URI
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 初始状态 | Initial state
        assert "priority=0" in resource.uri
        assert "fullscreen=true" in resource.uri

        # 使用新参数更新 | Update with new parameters
        new_uri = "window://test-project?priority=80&fullscreen=false"
        resource.update_from_uri(new_uri)

        # 验证参数已更新 | Verify parameters updated
        assert "priority=80" in resource.uri
        assert "fullscreen=false" in resource.uri

    def test_window_resource_update_partial_params(self, python_ide):
        """
        测试部分参数更新 | Test partial parameter update
        """
        resource = WindowResource(python_ide, priority=10, fullscreen=True)

        # 只更新 priority | Update only priority
        resource.update_from_uri("window://test-project?priority=50")
        assert "priority=50" in resource.uri
        assert "fullscreen=true" in resource.uri  # fullscreen 保持不变

        # 只更新 fullscreen | Update only fullscreen
        resource.update_from_uri("window://test-project?fullscreen=false")
        assert "priority=50" in resource.uri  # priority 保持不变
        assert "fullscreen=false" in resource.uri
