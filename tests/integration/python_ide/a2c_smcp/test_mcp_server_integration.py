# filename: test_mcp_server_integration.py
# @Time    : 2025/11/04 17:00
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
MCP Server 集成测试 | MCP Server Integration Tests

测试 PythonIDEMCPServer 的完整功能，包括工具和资源的注册与使用
Test complete functionality of PythonIDEMCPServer, including tool and resource registration and usage
"""

from collections.abc import Generator
from typing import Any

import pytest

from ide4ai.a2c_smcp.resources import WindowResource
from ide4ai.a2c_smcp.tools import BashTool, EditTool, GlobTool, GrepTool, ReadTool, WriteTool
from ide4ai.a2c_smcp.tools.base import BaseTool
from ide4ai.python_ide.ide import PythonIDE


class TestMCPServer:
    """
    测试用 MCP Server | Test MCP Server

    简化的 MCP Server 实现，用于测试工具和资源注册
    Simplified MCP Server implementation for testing tool and resource registration

    不继承 BaseMCPServer 以避免 confz 配置和完整的 MCP 协议处理
    Does not inherit BaseMCPServer to avoid confz configuration and full MCP protocol handling
    """

    def __init__(self, ide: PythonIDE) -> None:
        """
        初始化测试 MCP Server | Initialize test MCP Server

        Args:
            ide: PythonIDE 实例 | PythonIDE instance
        """
        self.ide = ide
        self.tools: dict[str, BaseTool] = {}
        self.resources: dict[str, WindowResource] = {}
        self._register_tools()
        self._register_resources()

    def _register_tools(self) -> None:
        """注册所有工具 | Register all tools"""
        self.tools["Bash"] = BashTool(self.ide)
        self.tools["Glob"] = GlobTool(self.ide)
        self.tools["Grep"] = GrepTool(self.ide)
        self.tools["Read"] = ReadTool(self.ide)
        self.tools["Edit"] = EditTool(self.ide)
        self.tools["Write"] = WriteTool(self.ide)

    def _register_resources(self) -> None:
        """注册所有资源 | Register all resources"""
        window_resource = WindowResource(self.ide, priority=0, fullscreen=True)
        self.resources[window_resource.base_uri] = window_resource


@pytest.fixture
def python_ide(tmp_path) -> Generator[PythonIDE, Any, None]:
    """
    创建 PythonIDE 实例 | Create PythonIDE instance
    """
    ide = PythonIDE(
        root_dir=str(tmp_path),
        project_name="test-mcp-project",
        cmd_time_out=5,
    )
    yield ide
    ide.close()


@pytest.fixture
def mcp_server(python_ide):
    """
    创建 MCP Server 实例 | Create MCP Server instance
    """
    server = TestMCPServer(python_ide)
    yield server
    # IDE 会在 python_ide fixture 中关闭 | IDE will be closed in python_ide fixture


class TestToolsRegistration:
    """
    工具注册测试 | Tools Registration Tests
    """

    def test_all_tools_registered(self, mcp_server):
        """
        测试所有工具都已注册 | Test all tools are registered
        """
        expected_tools = {"Bash", "Glob", "Grep", "Read", "Edit", "Write"}
        registered_tools = set(mcp_server.tools.keys())

        assert expected_tools == registered_tools, f"Expected tools: {expected_tools}, but got: {registered_tools}"

    def test_bash_tool_registered(self, mcp_server):
        """
        测试 Bash 工具已注册 | Test Bash tool is registered
        """
        assert "Bash" in mcp_server.tools
        bash_tool = mcp_server.tools["Bash"]
        assert bash_tool.name == "Bash"
        assert "执行" in bash_tool.description or "execute" in bash_tool.description.lower()

    def test_glob_tool_registered(self, mcp_server):
        """
        测试 Glob 工具已注册 | Test Glob tool is registered
        """
        assert "Glob" in mcp_server.tools
        glob_tool = mcp_server.tools["Glob"]
        assert glob_tool.name == "Glob"
        assert "搜索" in glob_tool.description or "search" in glob_tool.description.lower()

    def test_grep_tool_registered(self, mcp_server):
        """
        测试 Grep 工具已注册 | Test Grep tool is registered
        """
        assert "Grep" in mcp_server.tools
        grep_tool = mcp_server.tools["Grep"]
        assert grep_tool.name == "Grep"
        assert "搜索" in grep_tool.description or "search" in grep_tool.description.lower()

    def test_read_tool_registered(self, mcp_server):
        """
        测试 Read 工具已注册 | Test Read tool is registered
        """
        assert "Read" in mcp_server.tools
        read_tool = mcp_server.tools["Read"]
        assert read_tool.name == "Read"
        assert "读取" in read_tool.description or "read" in read_tool.description.lower()

    def test_edit_tool_registered(self, mcp_server):
        """
        测试 Edit 工具已注册 | Test Edit tool is registered
        """
        assert "Edit" in mcp_server.tools
        edit_tool = mcp_server.tools["Edit"]
        assert edit_tool.name == "Edit"
        assert "编辑" in edit_tool.description or "edit" in edit_tool.description.lower()

    def test_write_tool_registered(self, mcp_server):
        """
        测试 Write 工具已注册 | Test Write tool is registered
        """
        assert "Write" in mcp_server.tools
        write_tool = mcp_server.tools["Write"]
        assert write_tool.name == "Write"
        assert "写入" in write_tool.description or "write" in write_tool.description.lower()


class TestResourcesRegistration:
    """
    资源注册测试 | Resources Registration Tests
    """

    def test_window_resource_registered(self, mcp_server):
        """
        测试窗口资源已注册 | Test window resource is registered
        """
        # 应该有一个窗口资源 | Should have one window resource
        assert len(mcp_server.resources) == 1

        # 检查资源的 base_uri | Check resource's base_uri
        base_uri = f"window://{mcp_server.ide.project_name}"
        assert base_uri in mcp_server.resources

    def test_window_resource_properties(self, mcp_server):
        """
        测试窗口资源属性 | Test window resource properties
        """
        base_uri = f"window://{mcp_server.ide.project_name}"
        window_resource = mcp_server.resources[base_uri]

        # 验证资源属性 | Verify resource properties
        assert window_resource.name == f"IDE Window - {mcp_server.ide.project_name}"
        assert "IDE 窗口内容" in window_resource.description
        assert window_resource.mime_type == "text/plain"

        # 验证 URI 格式 | Verify URI format
        assert "window://" in window_resource.uri
        assert mcp_server.ide.project_name in window_resource.uri

    def test_window_resource_base_uri(self, mcp_server):
        """
        测试窗口资源的 base_uri | Test window resource's base_uri
        """
        base_uri = f"window://{mcp_server.ide.project_name}"
        window_resource = mcp_server.resources[base_uri]

        # base_uri 不应包含查询参数 | base_uri should not contain query parameters
        assert "?" not in window_resource.base_uri
        assert "priority" not in window_resource.base_uri
        assert "fullscreen" not in window_resource.base_uri

        # 完整 URI 应包含查询参数 | Full URI should contain query parameters
        full_uri = window_resource.uri
        assert "priority=" in full_uri
        assert "fullscreen=" in full_uri

    def test_list_resources_format(self, mcp_server):
        """
        测试资源列表格式（模拟 MCP list_resources 返回）| Test resource list format (simulating MCP list_resources return)
        """
        # 获取所有资源并转换为 MCP Resource 格式 | Get all resources and convert to MCP Resource format
        resources_list = []
        for resource in mcp_server.resources.values():
            resource_dict = resource.to_dict()
            resources_list.append(resource_dict)

        # 验证资源列表不为空 | Verify resource list is not empty
        assert len(resources_list) == 1

        # 验证资源格式 | Verify resource format
        resource_dict = resources_list[0]
        assert "uri" in resource_dict
        assert "name" in resource_dict
        assert "description" in resource_dict
        assert "mimeType" in resource_dict

        # 验证 URI 格式 | Verify URI format
        assert resource_dict["uri"].startswith("window://")
        assert "priority=" in resource_dict["uri"]
        assert "fullscreen=" in resource_dict["uri"]

        # 验证其他字段 | Verify other fields
        assert resource_dict["name"] == f"IDE Window - {mcp_server.ide.project_name}"
        assert "IDE 窗口内容" in resource_dict["description"]
        assert resource_dict["mimeType"] == "text/plain"


class TestToolExecution:
    """
    工具执行测试 | Tool Execution Tests
    """

    @pytest.mark.asyncio
    async def test_write_and_read_tool(self, mcp_server, tmp_path):
        """
        测试 Write 和 Read 工具的集成使用 | Test integrated usage of Write and Read tools
        """
        # 准备测试文件路径 | Prepare test file path
        test_file = tmp_path / "test_file.txt"
        test_content = "Hello, MCP Server!\nThis is a test file."

        # 使用 Write 工具写入文件 | Use Write tool to write file
        write_tool = mcp_server.tools["Write"]
        write_result = await write_tool.execute(
            {
                "file_path": str(test_file),
                "content": test_content,
            },
        )

        # 验证写入成功 | Verify write success
        assert write_result["success"] is True
        assert str(test_file) in write_result["message"]

        # 使用 Read 工具读取文件 | Use Read tool to read file
        read_tool = mcp_server.tools["Read"]
        read_result = await read_tool.execute(
            {
                "file_path": str(test_file),
            },
        )

        # 验证读取成功 | Verify read success
        assert read_result["success"] is True
        # ReadTool 返回格式化的内容（带行号），验证原始内容在其中
        # ReadTool returns formatted content (with line numbers), verify original content is in it
        assert "Hello, MCP Server!" in read_result["content"]
        assert "This is a test file." in read_result["content"]
        # 验证包含文件路径信息 | Verify file path info is included
        assert str(test_file) in read_result["content"]

    @pytest.mark.asyncio
    async def test_glob_tool(self, mcp_server, tmp_path):
        """
        测试 Glob 工具 | Test Glob tool
        """
        # 创建测试文件 | Create test files
        (tmp_path / "test1.py").write_text("# Test file 1")
        (tmp_path / "test2.py").write_text("# Test file 2")
        (tmp_path / "test.txt").write_text("Text file")

        # 使用 Glob 工具搜索 .py 文件 | Use Glob tool to search .py files
        glob_tool = mcp_server.tools["Glob"]
        glob_result = await glob_tool.execute(
            {
                "pattern": "*.py",
                "path": str(tmp_path),
            },
        )

        # 验证搜索结果 | Verify search results
        assert glob_result["success"] is True
        assert len(glob_result["files"]) == 2
        # GlobTool 返回的 files 是字典列表，每个字典包含文件信息
        # GlobTool returns files as a list of dicts, each containing file info
        file_paths = [f["path"] for f in glob_result["files"]]
        assert any("test1.py" in path for path in file_paths)
        assert any("test2.py" in path for path in file_paths)

    @pytest.mark.asyncio
    async def test_bash_tool(self, mcp_server):
        """
        测试 Bash 工具 | Test Bash tool
        """
        # 使用 Bash 工具执行简单命令 | Use Bash tool to execute simple command
        bash_tool = mcp_server.tools["Bash"]
        bash_result = await bash_tool.execute(
            {
                "command": "echo 'Hello from Bash'",
            },
        )

        # 验证执行结果 | Verify execution result
        assert bash_result["success"] is True
        assert "Hello from Bash" in bash_result["output"]


class TestResourceAccess:
    """
    资源访问测试 | Resource Access Tests
    """

    @pytest.mark.asyncio
    async def test_window_resource_read(self, mcp_server):
        """
        测试窗口资源读取 | Test window resource read
        """
        base_uri = f"window://{mcp_server.ide.project_name}"
        window_resource = mcp_server.resources[base_uri]

        # 读取窗口资源内容 | Read window resource content
        content = await window_resource.read()

        # 验证内容包含 IDE 信息 | Verify content contains IDE information
        assert isinstance(content, str)
        assert "IDE Content:" in content

    @pytest.mark.asyncio
    async def test_window_resource_dynamic_params(self, mcp_server):
        """
        测试窗口资源动态参数更新 | Test window resource dynamic parameter updates
        """
        base_uri = f"window://{mcp_server.ide.project_name}"
        window_resource = mcp_server.resources[base_uri]

        # 初始参数 | Initial parameters
        initial_uri = window_resource.uri
        assert "priority=0" in initial_uri
        assert "fullscreen=true" in initial_uri

        # 使用新参数更新 | Update with new parameters
        new_uri = f"{base_uri}?priority=80&fullscreen=false"
        window_resource.update_from_uri(new_uri)

        # 验证参数已更新 | Verify parameters updated
        updated_uri = window_resource.uri
        assert "priority=80" in updated_uri
        assert "fullscreen=false" in updated_uri

        # base_uri 保持不变 | base_uri remains unchanged
        assert window_resource.base_uri == base_uri


class TestServerLifecycle:
    """
    服务器生命周期测试 | Server Lifecycle Tests
    """

    def test_server_initialization(self, mcp_server):
        """
        测试服务器初始化 | Test server initialization
        """
        # 验证 IDE 已初始化 | Verify IDE is initialized
        assert mcp_server.ide is not None
        assert mcp_server.ide.project_name == "test-mcp-project"

    def test_server_close(self, tmp_path):
        """
        测试服务器关闭 | Test server close
        """
        ide = PythonIDE(
            root_dir=str(tmp_path),
            project_name="test-close",
            cmd_time_out=5,
        )
        server = TestMCPServer(ide)

        # 验证服务器已初始化 | Verify server is initialized
        assert server.ide is not None

        # 关闭 IDE | Close IDE
        ide.close()

        # 验证资源已清理（IDE 的 close 方法应该被调用）
        # Verify resources are cleaned up (IDE's close method should be called)
        # 注意：这里只是确保 close 方法可以正常调用，不会抛出异常
        # Note: Just ensure close method can be called without exceptions
