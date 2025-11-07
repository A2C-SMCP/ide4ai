# filename: test_resource_dynamic_params.py
# @Time    : 2025/11/04 17:00
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
资源动态参数更新测试 | Resource Dynamic Parameter Update Tests

详细测试资源的动态参数更新机制，包括边界条件和异常情况
Detailed tests for resource dynamic parameter update mechanism, including edge cases and exceptions
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


class TestBaseURIBehavior:
    """
    Base URI 行为测试 | Base URI Behavior Tests
    """

    def test_base_uri_excludes_query_params(self, python_ide):
        """
        测试 base_uri 排除查询参数 | Test base_uri excludes query parameters
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=True)

        # base_uri 应该只包含 scheme://host | base_uri should only contain scheme://host
        assert resource.base_uri == "window://test-project"
        assert "?" not in resource.base_uri
        assert "priority" not in resource.base_uri
        assert "fullscreen" not in resource.base_uri

    def test_base_uri_consistent_across_param_changes(self, python_ide):
        """
        测试 base_uri 在参数变化时保持一致 | Test base_uri remains consistent across parameter changes
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)
        initial_base_uri = resource.base_uri

        # 更新参数 | Update parameters
        resource.update_from_uri("window://test-project?priority=100&fullscreen=false")

        # base_uri 应该保持不变 | base_uri should remain unchanged
        assert resource.base_uri == initial_base_uri
        assert resource.base_uri == "window://test-project"

    def test_different_params_same_base_uri(self, python_ide):
        """
        测试不同参数的资源具有相同的 base_uri | Test resources with different params have same base_uri
        """
        resource1 = WindowResource(python_ide, priority=0, fullscreen=True)
        resource2 = WindowResource(python_ide, priority=100, fullscreen=False)

        # 两个资源应该有相同的 base_uri | Both resources should have same base_uri
        assert resource1.base_uri == resource2.base_uri
        assert resource1.base_uri == "window://test-project"

        # 但完整 URI 应该不同 | But full URIs should be different
        assert resource1.uri != resource2.uri


class TestPriorityUpdate:
    """
    Priority 参数更新测试 | Priority Parameter Update Tests
    """

    def test_update_priority_valid_value(self, python_ide):
        """
        测试更新有效的 priority 值 | Test updating valid priority value
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 更新为有效值 | Update to valid value
        resource.update_from_uri("window://test-project?priority=50")

        # 验证更新成功 | Verify update success
        assert "priority=50" in resource.uri

    def test_update_priority_boundary_values(self, python_ide):
        """
        测试边界值的 priority 更新 | Test priority update with boundary values
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=True)

        # 测试最小值 0 | Test minimum value 0
        resource.update_from_uri("window://test-project?priority=0")
        assert "priority=0" in resource.uri

        # 测试最大值 100 | Test maximum value 100
        resource.update_from_uri("window://test-project?priority=100")
        assert "priority=100" in resource.uri

    def test_update_priority_invalid_value_ignored(self, python_ide):
        """
        测试无效的 priority 值被忽略 | Test invalid priority value is ignored
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=True)
        original_uri = resource.uri

        # 尝试更新为超出范围的值 | Try to update with out-of-range value
        resource.update_from_uri("window://test-project?priority=150")

        # priority 应该保持原值 | priority should remain original value
        assert "priority=50" in resource.uri
        assert resource.uri == original_uri

        # 尝试更新为负值 | Try to update with negative value
        resource.update_from_uri("window://test-project?priority=-10")
        assert "priority=50" in resource.uri

    def test_update_priority_invalid_format_ignored(self, python_ide):
        """
        测试无效格式的 priority 被忽略 | Test invalid format priority is ignored
        """
        resource = WindowResource(python_ide, priority=30, fullscreen=True)
        original_uri = resource.uri

        # 尝试更新为非数字值 | Try to update with non-numeric value
        resource.update_from_uri("window://test-project?priority=abc")

        # priority 应该保持原值 | priority should remain original value
        assert "priority=30" in resource.uri
        assert resource.uri == original_uri


class TestFullscreenUpdate:
    """
    Fullscreen 参数更新测试 | Fullscreen Parameter Update Tests
    """

    def test_update_fullscreen_true(self, python_ide):
        """
        测试更新 fullscreen 为 true | Test updating fullscreen to true
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=False)

        # 测试各种 true 的表示 | Test various representations of true
        for true_value in ["true", "True", "TRUE", "1", "yes", "on"]:
            resource.update_from_uri(f"window://test-project?fullscreen={true_value}")
            assert "fullscreen=true" in resource.uri

    def test_update_fullscreen_false(self, python_ide):
        """
        测试更新 fullscreen 为 false | Test updating fullscreen to false
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 测试各种 false 的表示 | Test various representations of false
        for false_value in ["false", "False", "FALSE", "0", "no", "off"]:
            resource.update_from_uri(f"window://test-project?fullscreen={false_value}")
            assert "fullscreen=false" in resource.uri

    def test_update_fullscreen_invalid_value_ignored(self, python_ide):
        """
        测试无效的 fullscreen 值被忽略 | Test invalid fullscreen value is ignored
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)
        original_uri = resource.uri

        # 尝试更新为无效值 | Try to update with invalid value
        resource.update_from_uri("window://test-project?fullscreen=maybe")

        # fullscreen 应该保持原值 | fullscreen should remain original value
        assert "fullscreen=true" in resource.uri
        assert resource.uri == original_uri


class TestPartialParameterUpdate:
    """
    部分参数更新测试 | Partial Parameter Update Tests
    """

    def test_update_only_priority(self, python_ide):
        """
        测试只更新 priority | Test updating only priority
        """
        resource = WindowResource(python_ide, priority=10, fullscreen=True)

        # 只更新 priority | Update only priority
        resource.update_from_uri("window://test-project?priority=60")

        # priority 应该更新，fullscreen 保持不变 | priority should update, fullscreen remains
        assert "priority=60" in resource.uri
        assert "fullscreen=true" in resource.uri

    def test_update_only_fullscreen(self, python_ide):
        """
        测试只更新 fullscreen | Test updating only fullscreen
        """
        resource = WindowResource(python_ide, priority=25, fullscreen=True)

        # 只更新 fullscreen | Update only fullscreen
        resource.update_from_uri("window://test-project?fullscreen=false")

        # fullscreen 应该更新，priority 保持不变 | fullscreen should update, priority remains
        assert "priority=25" in resource.uri
        assert "fullscreen=false" in resource.uri

    def test_update_both_parameters(self, python_ide):
        """
        测试同时更新两个参数 | Test updating both parameters
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 同时更新两个参数 | Update both parameters
        resource.update_from_uri("window://test-project?priority=75&fullscreen=false")

        # 两个参数都应该更新 | Both parameters should update
        assert "priority=75" in resource.uri
        assert "fullscreen=false" in resource.uri


class TestParameterUpdateWithNoChange:
    """
    参数无变化更新测试 | Parameter Update with No Change Tests
    """

    def test_update_with_same_values(self, python_ide):
        """
        测试使用相同值更新 | Test updating with same values
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=True)
        original_uri = resource.uri

        # 使用相同的值更新 | Update with same values
        resource.update_from_uri("window://test-project?priority=50&fullscreen=true")

        # URI 应该保持不变 | URI should remain unchanged
        assert resource.uri == original_uri

    def test_update_with_empty_query(self, python_ide):
        """
        测试使用空查询参数更新 | Test updating with empty query
        """
        resource = WindowResource(python_ide, priority=30, fullscreen=False)
        original_uri = resource.uri

        # 使用没有查询参数的 URI 更新 | Update with URI without query parameters
        resource.update_from_uri("window://test-project")

        # 参数应该保持不变 | Parameters should remain unchanged
        assert resource.uri == original_uri
        assert "priority=30" in resource.uri
        assert "fullscreen=false" in resource.uri


class TestMultipleUpdates:
    """
    多次更新测试 | Multiple Updates Tests
    """

    def test_sequential_updates(self, python_ide):
        """
        测试连续多次更新 | Test sequential multiple updates
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 第一次更新 | First update
        resource.update_from_uri("window://test-project?priority=25")
        assert "priority=25" in resource.uri
        assert "fullscreen=true" in resource.uri

        # 第二次更新 | Second update
        resource.update_from_uri("window://test-project?fullscreen=false")
        assert "priority=25" in resource.uri
        assert "fullscreen=false" in resource.uri

        # 第三次更新 | Third update
        resource.update_from_uri("window://test-project?priority=80&fullscreen=true")
        assert "priority=80" in resource.uri
        assert "fullscreen=true" in resource.uri

    def test_update_back_and_forth(self, python_ide):
        """
        测试来回更新参数 | Test updating parameters back and forth
        """
        resource = WindowResource(python_ide, priority=50, fullscreen=True)

        # 更新为新值 | Update to new values
        resource.update_from_uri("window://test-project?priority=10&fullscreen=false")
        assert "priority=10" in resource.uri
        assert "fullscreen=false" in resource.uri

        # 更新回原值 | Update back to original values
        resource.update_from_uri("window://test-project?priority=50&fullscreen=true")
        assert "priority=50" in resource.uri
        assert "fullscreen=true" in resource.uri


class TestResourceReadAfterUpdate:
    """
    更新后资源读取测试 | Resource Read After Update Tests
    """

    @pytest.mark.asyncio
    async def test_read_after_parameter_update(self, python_ide):
        """
        测试参数更新后读取资源 | Test reading resource after parameter update
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 更新参数 | Update parameters
        resource.update_from_uri("window://test-project?priority=90&fullscreen=false")

        # 读取资源应该正常工作 | Reading resource should work normally
        content = await resource.read()
        assert isinstance(content, str)
        assert "IDE Content:" in content

    @pytest.mark.asyncio
    async def test_multiple_reads_with_updates(self, python_ide):
        """
        测试多次读取和更新 | Test multiple reads with updates
        """
        resource = WindowResource(python_ide, priority=0, fullscreen=True)

        # 第一次读取 | First read
        content1 = await resource.read()
        assert "IDE Content:" in content1

        # 更新参数 | Update parameters
        resource.update_from_uri("window://test-project?priority=50")

        # 第二次读取 | Second read
        content2 = await resource.read()
        assert "IDE Content:" in content2

        # 再次更新参数 | Update parameters again
        resource.update_from_uri("window://test-project?fullscreen=false")

        # 第三次读取 | Third read
        content3 = await resource.read()
        assert "IDE Content:" in content3
