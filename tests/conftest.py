# filename: conftest.py
# @Time    : 2025/10/31
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
"""
全局 pytest 配置，自动加载 .env 环境变量
Global pytest configuration, automatically loads .env environment variables
"""

from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def load_env():
    """
    在所有测试开始前自动加载 .env 文件
    Automatically load .env file before all tests
    """
    try:
        from dotenv import load_dotenv

        # 查找项目根目录的 .env 文件
        # Find .env file in project root
        project_root = Path(__file__).parent.parent
        env_file = project_root / ".env"

        if env_file.exists():
            load_dotenv(env_file, override=False)
            print(f"✓ Loaded environment variables from {env_file}")
        else:
            print(f"⚠ No .env file found at {env_file}")
    except ImportError:
        print("⚠ python-dotenv not installed, skipping .env loading")
        print("  Install with: uv add --dev python-dotenv")
