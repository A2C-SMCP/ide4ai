"""Optional Docker Pyright acceptance; TCP reachability is not readiness."""

import pytest

from tests.integration.python_ide.docker_pyright_client import PyrightUnavailable, check_pyright_endpoint


@pytest.mark.timeout(15)
async def test_docker_pyright_process_async() -> None:
    try:
        await check_pyright_endpoint("localhost", 3000)
    except PyrightUnavailable as exc:
        pytest.skip(str(exc))
