"""Synchronous caller of the shared bounded Docker Pyright acceptance probe."""

import asyncio

import pytest

from tests.integration.python_ide.docker_pyright_client import PyrightUnavailable, check_pyright_endpoint


@pytest.mark.timeout(15)
def test_docker_pyright_process() -> None:
    try:
        asyncio.run(check_pyright_endpoint("localhost", 3000))
    except PyrightUnavailable as exc:
        pytest.skip(str(exc))
