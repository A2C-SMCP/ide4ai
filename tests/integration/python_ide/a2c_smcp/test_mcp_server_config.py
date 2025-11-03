# filename: test_mcp_server_config.py
# @Time    : 2025/10/30 11:19
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
测试 MCP Server 配置 | Test MCP Server Configuration

使用 confz 进行配置管理，支持环境变量和命令行参数
Using confz for configuration management, supporting environment variables and command-line arguments
"""

import os
import sys
from unittest.mock import patch

from confz import CLArgSource, DataSource, EnvSource

from ide4ai.a2c_smcp.config import MCPServerConfig


class TestMCPServerConfig:
    """测试 MCP Server 配置 | Test MCP Server Configuration"""

    def test_default_config(self) -> None:
        """
        测试默认配置 | Test default configuration
        """
        # 使用 DataSource 提供空数据，测试默认值
        # Use DataSource with empty data to test default values
        with MCPServerConfig.change_config_sources(DataSource(data={})):
            config = MCPServerConfig()

            assert config.root_dir == "."
            assert config.project_name == "mcp-project"
            assert config.cmd_time_out == 10
            # 默认白名单不为空 | Default whitelist is not empty
            assert config.cmd_white_list == ["ls", "pwd", "echo", "cat", "grep", "find", "head", "tail", "wc"]
            assert config.render_with_symbols is True
            assert config.max_active_models == 3
            assert config.enable_simple_view_mode is True

    def test_to_ide_kwargs(self) -> None:
        """
        测试转换为 IDE 初始化参数 | Test conversion to IDE initialization parameters
        """
        with MCPServerConfig.change_config_sources(DataSource(data={})):
            config = MCPServerConfig()

            kwargs = config.to_ide_kwargs()

            assert kwargs["root_dir"] == "."
            assert kwargs["project_name"] == "mcp-project"
            assert "cmd_filter" in kwargs
            assert "cmd_time_out" in kwargs
            assert "render_with_symbols" in kwargs


class TestEnvironmentVariables:
    """测试环境变量配置 | Test Environment Variable Configuration"""

    def test_env_project_root(self) -> None:
        """
        测试 PROJECT_ROOT 环境变量 | Test PROJECT_ROOT environment variable
        """
        with patch.dict(os.environ, {"PROJECT_ROOT": "/custom/root"}, clear=True):
            with patch.object(sys, "argv", ["test"]):
                # 重新创建配置源以使用新的环境变量
                # Recreate config sources to use new environment variables
                env_source = EnvSource(
                    allow_all=True,
                    prefix="",
                    remap={
                        "PROJECT_ROOT": "root_dir",
                        "PROJECT_NAME": "project_name",
                        "CMD_WHITE_LIST": "cmd_white_list",
                        "CMD_TIMEOUT": "cmd_time_out",
                    },
                )
                with MCPServerConfig.change_config_sources(env_source):
                    config = MCPServerConfig()
                    assert config.root_dir == "/custom/root"

    def test_env_project_name(self) -> None:
        """
        测试 PROJECT_NAME 环境变量 | Test PROJECT_NAME environment variable
        """
        with patch.dict(os.environ, {"PROJECT_NAME": "custom-name"}, clear=True):
            with patch.object(sys, "argv", ["test"]):
                env_source = EnvSource(
                    allow_all=True,
                    prefix="",
                    remap={"PROJECT_NAME": "project_name"},
                )
                with MCPServerConfig.change_config_sources(env_source):
                    config = MCPServerConfig()
                    assert config.project_name == "custom-name"

    def test_env_cmd_timeout(self) -> None:
        """
        测试 CMD_TIMEOUT 环境变量 | Test CMD_TIMEOUT environment variable
        """
        with patch.dict(os.environ, {"CMD_TIMEOUT": "60"}, clear=True):
            with patch.object(sys, "argv", ["test"]):
                env_source = EnvSource(
                    allow_all=True,
                    prefix="",
                    remap={"CMD_TIMEOUT": "cmd_time_out"},
                )
                with MCPServerConfig.change_config_sources(env_source):
                    config = MCPServerConfig()
                    assert config.cmd_time_out == 60

    def test_env_cmd_white_list(self) -> None:
        """
        测试 CMD_WHITE_LIST 环境变量 | Test CMD_WHITE_LIST environment variable
        """
        with patch.dict(os.environ, {"CMD_WHITE_LIST": "ls,pwd,echo,cat"}, clear=True):
            with patch.object(sys, "argv", ["test"]):
                env_source = EnvSource(
                    allow_all=True,
                    prefix="",
                    remap={"CMD_WHITE_LIST": "cmd_white_list"},
                )
                with MCPServerConfig.change_config_sources(env_source):
                    config = MCPServerConfig()
                    assert config.cmd_white_list == ["ls", "pwd", "echo", "cat"]

    def test_env_cmd_white_list_with_spaces(self) -> None:
        """
        测试带空格的 CMD_WHITE_LIST 环境变量 | Test CMD_WHITE_LIST with spaces
        """
        with patch.dict(os.environ, {"CMD_WHITE_LIST": "ls, pwd , echo,  cat  "}, clear=True):
            with patch.object(sys, "argv", ["test"]):
                env_source = EnvSource(
                    allow_all=True,
                    prefix="",
                    remap={"CMD_WHITE_LIST": "cmd_white_list"},
                )
                with MCPServerConfig.change_config_sources(env_source):
                    config = MCPServerConfig()
                    assert config.cmd_white_list == ["ls", "pwd", "echo", "cat"]

    def test_env_all_options(self) -> None:
        """
        测试所有环境变量选项 | Test all environment variable options
        """
        env_vars = {
            "PROJECT_ROOT": "/test/root",
            "PROJECT_NAME": "test-project",
            "CMD_WHITE_LIST": "ls,pwd",
            "CMD_TIMEOUT": "30",
            "RENDER_WITH_SYMBOLS": "false",
            "MAX_ACTIVE_MODELS": "5",
            "ENABLE_SIMPLE_VIEW_MODE": "false",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            with patch.object(sys, "argv", ["test"]):
                env_source = EnvSource(
                    allow_all=True,
                    prefix="",
                    remap={
                        "PROJECT_ROOT": "root_dir",
                        "PROJECT_NAME": "project_name",
                        "CMD_WHITE_LIST": "cmd_white_list",
                        "CMD_TIMEOUT": "cmd_time_out",
                        "RENDER_WITH_SYMBOLS": "render_with_symbols",
                        "MAX_ACTIVE_MODELS": "max_active_models",
                        "ENABLE_SIMPLE_VIEW_MODE": "enable_simple_view_mode",
                    },
                )
                with MCPServerConfig.change_config_sources(env_source):
                    config = MCPServerConfig()
                    assert config.root_dir == "/test/root"
                    assert config.project_name == "test-project"
                    assert config.cmd_white_list == ["ls", "pwd"]
                    assert config.cmd_time_out == 30
                    assert config.render_with_symbols is False
                    assert config.max_active_models == 5
                    assert config.enable_simple_view_mode is False


class TestCommandLineArguments:
    """测试命令行参数配置 | Test Command-line Argument Configuration"""

    def test_cli_project_root(self) -> None:
        """
        测试 --root-dir 命令行参数 | Test --root-dir command-line argument
        """
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["test", "--root-dir", "/cli/root"]):
                cli_source = CLArgSource(
                    prefix="",
                    remap={"root-dir": "root_dir"},
                )
                with MCPServerConfig.change_config_sources(cli_source):
                    config = MCPServerConfig()
                    assert config.root_dir == "/cli/root"

    def test_cli_project_name(self) -> None:
        """
        测试 --project-name 命令行参数 | Test --project-name command-line argument
        """
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["test", "--project-name", "cli-project"]):
                cli_source = CLArgSource(
                    prefix="",
                    remap={"project-name": "project_name"},
                )
                with MCPServerConfig.change_config_sources(cli_source):
                    config = MCPServerConfig()
                    assert config.project_name == "cli-project"

    def test_cli_cmd_timeout(self) -> None:
        """
        测试 --cmd-timeout 命令行参数 | Test --cmd-timeout command-line argument
        """
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["test", "--cmd-timeout", "45"]):
                cli_source = CLArgSource(
                    prefix="",
                    remap={"cmd-timeout": "cmd_time_out"},
                )
                with MCPServerConfig.change_config_sources(cli_source):
                    config = MCPServerConfig()
                    assert config.cmd_time_out == 45

    def test_cli_cmd_white_list(self) -> None:
        """
        测试 --cmd-white-list 命令行参数 | Test --cmd-white-list command-line argument
        """
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["test", "--cmd-white-list", "ls,pwd,echo"]):
                cli_source = CLArgSource(
                    prefix="",
                    remap={"cmd-white-list": "cmd_white_list"},
                )
                with MCPServerConfig.change_config_sources(cli_source):
                    config = MCPServerConfig()
                    assert config.cmd_white_list == ["ls", "pwd", "echo"]

    def test_cli_priority_over_env(self) -> None:
        """
        测试命令行参数优先级高于环境变量 | Test command-line arguments have higher priority than environment variables
        """
        env_vars = {
            "PROJECT_ROOT": "/env/root",
            "PROJECT_NAME": "env-project",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            with patch.object(sys, "argv", ["test", "--root-dir", "/cli/root", "--project-name", "cli-project"]):
                # 配置源优先级：命令行参数 > 环境变量
                # Config source priority: Command-line arguments > Environment variables
                # 使用列表传递多个配置源 | Use list to pass multiple config sources
                sources = [
                    EnvSource(
                        allow_all=True,
                        prefix="",
                        remap={
                            "PROJECT_ROOT": "root_dir",
                            "PROJECT_NAME": "project_name",
                        },
                    ),
                    CLArgSource(
                        prefix="",
                        remap={
                            "root-dir": "root_dir",
                            "project-name": "project_name",
                        },
                    ),
                ]
                with MCPServerConfig.change_config_sources(sources):
                    config = MCPServerConfig()
                    # 命令行参数应该覆盖环境变量 | Command-line arguments should override environment variables
                    assert config.root_dir == "/cli/root"
                    assert config.project_name == "cli-project"

    def test_cli_all_options(self) -> None:
        """
        测试所有命令行参数选项 | Test all command-line argument options
        """
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(
                sys,
                "argv",
                [
                    "test",
                    "--root-dir",
                    "/cli/root",
                    "--project-name",
                    "cli-project",
                    "--cmd-white-list",
                    "ls,pwd",
                    "--cmd-timeout",
                    "25",
                    "--render-with-symbols",
                    "false",
                    "--max-active-models",
                    "7",
                    "--enable-simple-view-mode",
                    "false",
                ],
            ):
                cli_source = CLArgSource(
                    prefix="",
                    remap={
                        "root-dir": "root_dir",
                        "project-name": "project_name",
                        "cmd-white-list": "cmd_white_list",
                        "cmd-timeout": "cmd_time_out",
                        "render-with-symbols": "render_with_symbols",
                        "max-active-models": "max_active_models",
                        "enable-simple-view-mode": "enable_simple_view_mode",
                    },
                )
                with MCPServerConfig.change_config_sources(cli_source):
                    config = MCPServerConfig()
                    assert config.root_dir == "/cli/root"
                    assert config.project_name == "cli-project"
                    assert config.cmd_white_list == ["ls", "pwd"]
                    assert config.cmd_time_out == 25
                    assert config.render_with_symbols is False
                    assert config.max_active_models == 7
                    assert config.enable_simple_view_mode is False

    def test_transport_mode_config(self) -> None:
        """
        测试传输模式配置 | Test transport mode configuration
        """
        # 测试默认传输模式 | Test default transport mode
        with MCPServerConfig.change_config_sources(DataSource(data={})):
            config = MCPServerConfig()
            assert config.transport == "stdio"
            assert config.host == "127.0.0.1"
            assert config.port == 8000

        # 测试 SSE 模式 | Test SSE mode
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "sse",
                    "host": "0.0.0.0",
                    "port": 9000,
                },
            ),
        ):
            config = MCPServerConfig()
            assert config.transport == "sse"
            assert config.host == "0.0.0.0"
            assert config.port == 9000

        # 测试 Streamable HTTP 模式 | Test Streamable HTTP mode
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "streamable-http",
                    "host": "localhost",
                    "port": 8080,
                },
            ),
        ):
            config = MCPServerConfig()
            assert config.transport == "streamable-http"
            assert config.host == "localhost"
            assert config.port == 8080

    def test_transport_mode_from_env(self) -> None:
        """
        测试从环境变量加载传输模式配置 | Test loading transport mode config from environment variables
        """
        env_vars = {
            "TRANSPORT": "sse",
            "HOST": "192.168.1.100",
            "PORT": "7000",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            env_source = EnvSource(
                allow_all=True,
                prefix="",
                remap={
                    "TRANSPORT": "transport",
                    "HOST": "host",
                    "PORT": "port",
                },
            )
            with MCPServerConfig.change_config_sources(env_source):
                config = MCPServerConfig()
                assert config.transport == "sse"
                assert config.host == "192.168.1.100"
                assert config.port == 7000

    def test_transport_mode_from_cli(self) -> None:
        """
        测试从命令行参数加载传输模式配置 | Test loading transport mode config from CLI arguments
        """
        with patch.object(
            sys,
            "argv",
            [
                "test",
                "--transport",
                "streamable-http",
                "--host",
                "10.0.0.1",
                "--port",
                "8888",
            ],
        ):
            cli_source = CLArgSource(
                prefix="",
                remap={
                    "transport": "transport",
                    "host": "host",
                    "port": "port",
                },
            )
            with MCPServerConfig.change_config_sources(cli_source):
                config = MCPServerConfig()
                assert config.transport == "streamable-http"
                assert config.host == "10.0.0.1"
                assert config.port == 8888

    def test_mixed_config_with_transport(self) -> None:
        """
        测试混合配置（传输模式 + IDE 配置）| Test mixed configuration (transport + IDE config)
        """
        with MCPServerConfig.change_config_sources(
            DataSource(
                data={
                    "transport": "sse",
                    "host": "0.0.0.0",
                    "port": 8000,
                    "root_dir": "/test/project",
                    "project_name": "mixed-test",
                    "cmd_white_list": ["ls", "pwd", "echo"],
                    "cmd_time_out": 20,
                },
            ),
        ):
            config = MCPServerConfig()

            # 验证传输配置 | Verify transport config
            assert config.transport == "sse"
            assert config.host == "0.0.0.0"
            assert config.port == 8000

            # 验证 IDE 配置 | Verify IDE config
            assert config.root_dir == "/test/project"
            assert config.project_name == "mixed-test"
            assert config.cmd_white_list == ["ls", "pwd", "echo"]
            assert config.cmd_time_out == 20
