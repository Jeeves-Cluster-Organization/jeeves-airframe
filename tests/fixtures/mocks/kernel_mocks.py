"""Mock implementations for KernelClient IPC testing.

These mocks allow Python tests to run without a real Rust kernel server.
Mock factories return dicts matching the IPC wire format.

Usage:
    from tests.fixtures.mocks.kernel_mocks import (
        mock_transport,
        mock_kernel_client,
        make_process_dict,
    )
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from jeeves_infra.kernel_client import KernelClient
from jeeves_infra.ipc import IpcTransport


def make_process_dict(
    pid: str = "test-pid",
    request_id: str = "test-request",
    user_id: str = "test-user",
    session_id: str = "test-session",
    state: str = "NEW",
    priority: str = "NORMAL",
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    current_stage: str = "",
) -> dict:
    """Factory for creating process response dicts (IPC wire format)."""
    return {
        "pid": pid,
        "request_id": request_id,
        "user_id": user_id,
        "session_id": session_id,
        "state": state,
        "priority": priority,
        "current_stage": current_stage,
        "usage": {
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
            "agent_hops": agent_hops,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        },
    }


def make_quota_dict(
    within_bounds: bool = True,
    exceeded_reason: str = "",
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> dict:
    """Factory for creating quota result dicts."""
    return {
        "within_bounds": within_bounds,
        "exceeded_reason": exceeded_reason,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "agent_hops": agent_hops,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


def make_usage_dict(
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> dict:
    """Factory for creating resource usage dicts."""
    return {
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "agent_hops": agent_hops,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


def make_rate_limit_dict(
    allowed: bool = True,
    exceeded: bool = False,
    reason: str = "",
    limit_type: str = "",
    current_count: int = 0,
    limit: int = 100,
    retry_after_seconds: int = 0,
    remaining: int = 100,
) -> dict:
    """Factory for creating rate limit result dicts."""
    return {
        "allowed": allowed,
        "exceeded": exceeded,
        "reason": reason,
        "limit_type": limit_type,
        "current_count": current_count,
        "limit": limit,
        "retry_after_seconds": retry_after_seconds,
        "remaining": remaining,
    }


def make_list_processes_dict(processes: list = None) -> dict:
    """Factory for creating list processes response dicts."""
    return {"processes": processes or []}


def make_process_counts_dict(
    total: int = 0,
    queue_depth: int = 0,
    counts_by_state: dict = None,
) -> dict:
    """Factory for creating process counts response dicts."""
    result = {
        "total": total,
        "queue_depth": queue_depth,
    }
    if counts_by_state:
        result.update(counts_by_state)
    return result


@pytest.fixture
def mock_transport():
    """Mock IpcTransport with AsyncMock methods."""
    transport = MagicMock(spec=IpcTransport)
    transport.connect = AsyncMock()
    transport.close = AsyncMock()
    transport.request = AsyncMock(return_value=make_process_dict())
    transport.request_stream = AsyncMock()
    transport.connected = True
    return transport


@pytest.fixture
def mock_kernel_client(mock_transport):
    """Configured KernelClient with mocked IPC transport.

    Usage:
        async def test_something(mock_kernel_client):
            proc = await mock_kernel_client.create_process(pid="test-1")
            assert proc.pid == "test-pid"
    """
    return KernelClient(transport=mock_transport)


__all__ = [
    "make_process_dict",
    "make_quota_dict",
    "make_usage_dict",
    "make_rate_limit_dict",
    "make_list_processes_dict",
    "make_process_counts_dict",
    "mock_transport",
    "mock_kernel_client",
]
