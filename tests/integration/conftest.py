"""Integration test fixtures — require a running Rust kernel.

These tests are gated behind the 'integration' marker.
Run with: pytest -m integration tests/integration/
"""

import os
import pytest


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless explicitly requested."""
    if not config.getoption("-m", default="") or "integration" not in config.getoption("-m", default=""):
        skip_marker = pytest.mark.skip(reason="integration tests require -m integration")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_marker)


@pytest.fixture
def kernel_host():
    """Kernel IPC host from env or default."""
    return os.getenv("KERNEL_HOST", "127.0.0.1")


@pytest.fixture
def kernel_port():
    """Kernel IPC port from env or default."""
    return int(os.getenv("KERNEL_PORT", "50051"))


@pytest.fixture
async def kernel_client(kernel_host, kernel_port):
    """Live KernelClient connected to a running kernel."""
    from jeeves_infra.kernel.client import KernelClient
    from jeeves_infra.kernel.transport import IpcTransport

    transport = IpcTransport(host=kernel_host, port=kernel_port)
    await transport.connect()
    client = KernelClient(transport=transport)
    yield client
    await transport.disconnect()
