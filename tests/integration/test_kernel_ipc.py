"""Integration tests for kernel IPC round-trips.

Requires a running jeeves-core kernel at KERNEL_HOST:KERNEL_PORT.
Run with: pytest -m integration tests/integration/test_kernel_ipc.py
"""

import pytest


pytestmark = pytest.mark.integration


class TestKernelHealthCheck:
    """Verify basic kernel connectivity."""

    async def test_get_system_status(self, kernel_client):
        """GetSystemStatus should return a dict with process counts."""
        result = await kernel_client.get_system_status()
        assert isinstance(result, dict)
        assert "processes_total" in result

    async def test_get_quota_defaults(self, kernel_client):
        """GetQuotaDefaults should return current quota configuration."""
        result = await kernel_client.get_quota_defaults()
        assert isinstance(result, dict)
        assert "max_llm_calls" in result


class TestKernelProcessLifecycle:
    """Verify process creation and lifecycle."""

    async def test_create_and_get_process(self, kernel_client):
        """Create a process, then retrieve it by PID."""
        import uuid

        pid = f"integ-{uuid.uuid4().hex[:8]}"
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        user_id = "integ-user"
        session_id = f"sess-{uuid.uuid4().hex[:8]}"

        created = await kernel_client.create_process(
            pid=pid,
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
        )
        assert created["pid"] == pid

        fetched = await kernel_client.get_process(pid)
        assert fetched["pid"] == pid
        assert fetched["user_id"] == user_id


class TestKernelRateLimiting:
    """Verify rate limiting IPC."""

    async def test_check_rate_limit(self, kernel_client):
        """CheckRateLimit should return allowed/exceeded status."""
        result = await kernel_client.check_rate_limit(
            user_id="integ-user",
            endpoint="/test",
        )
        assert isinstance(result, dict)
        assert "exceeded" in result or "allowed" in result
