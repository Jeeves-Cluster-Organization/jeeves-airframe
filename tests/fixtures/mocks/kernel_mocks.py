"""Mock implementations for KernelClient gRPC testing.

These mocks allow Python tests to run without a real Go kernel server.

Usage:
    from tests.fixtures.mocks.kernel_mocks import (
        mock_grpc_channel,
        mock_kernel_stub,
        mock_kernel_client,
        make_pcb,
    )
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from jeeves_infra.kernel_client import KernelClient
from jeeves_infra.protocols import engine_pb2 as pb2


def make_pcb(
    pid: str = "test-pid",
    request_id: str = "test-request",
    user_id: str = "test-user",
    session_id: str = "test-session",
    state: int = pb2.PROCESS_STATE_NEW,
    priority: int = pb2.SCHEDULING_PRIORITY_NORMAL,
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    current_stage: str = "",
) -> pb2.ProcessControlBlock:
    """Factory for creating ProcessControlBlock proto responses.

    Args:
        pid: Process ID
        request_id: Request ID
        user_id: User ID
        session_id: Session ID
        state: Process state (use pb2.PROCESS_STATE_* constants)
        priority: Scheduling priority (use pb2.SCHEDULING_PRIORITY_* constants)
        llm_calls: LLM call count
        tool_calls: Tool call count
        agent_hops: Agent hop count
        tokens_in: Input tokens
        tokens_out: Output tokens
        current_stage: Current pipeline stage

    Returns:
        ProcessControlBlock proto message
    """
    pcb = pb2.ProcessControlBlock()
    pcb.pid = pid
    pcb.request_id = request_id
    pcb.user_id = user_id
    pcb.session_id = session_id
    pcb.state = state
    pcb.priority = priority
    pcb.current_stage = current_stage

    # Set usage
    pcb.usage.llm_calls = llm_calls
    pcb.usage.tool_calls = tool_calls
    pcb.usage.agent_hops = agent_hops
    pcb.usage.tokens_in = tokens_in
    pcb.usage.tokens_out = tokens_out

    return pcb


def make_quota_result(
    within_bounds: bool = True,
    exceeded_reason: str = "",
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> pb2.QuotaResult:
    """Factory for creating QuotaResult proto responses.

    Args:
        within_bounds: Whether usage is within quota
        exceeded_reason: Reason for quota exceeded (if applicable)
        llm_calls: Current LLM call count
        tool_calls: Current tool call count
        agent_hops: Current agent hop count
        tokens_in: Current input tokens
        tokens_out: Current output tokens

    Returns:
        QuotaResult proto message
    """
    result = pb2.QuotaResult()
    result.within_bounds = within_bounds
    result.exceeded_reason = exceeded_reason

    result.usage.llm_calls = llm_calls
    result.usage.tool_calls = tool_calls
    result.usage.agent_hops = agent_hops
    result.usage.tokens_in = tokens_in
    result.usage.tokens_out = tokens_out

    return result


def make_resource_usage(
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> pb2.ResourceUsage:
    """Factory for creating ResourceUsage proto responses."""
    usage = pb2.ResourceUsage()
    usage.llm_calls = llm_calls
    usage.tool_calls = tool_calls
    usage.agent_hops = agent_hops
    usage.tokens_in = tokens_in
    usage.tokens_out = tokens_out
    return usage


def make_rate_limit_result(
    allowed: bool = True,
    exceeded: bool = False,
    reason: str = "",
    limit_type: str = "",
    current_count: int = 0,
    limit: int = 100,
    retry_after_seconds: int = 0,
    remaining: int = 100,
) -> pb2.RateLimitResult:
    """Factory for creating RateLimitResult proto responses."""
    result = pb2.RateLimitResult()
    result.allowed = allowed
    result.exceeded = exceeded
    result.reason = reason
    result.limit_type = limit_type
    result.current_count = current_count
    result.limit = limit
    result.retry_after_seconds = retry_after_seconds
    result.remaining = remaining
    return result


def make_list_processes_response(
    processes: list = None,
) -> pb2.ListProcessesResponse:
    """Factory for creating ListProcessesResponse proto responses."""
    response = pb2.ListProcessesResponse()
    if processes:
        for pcb in processes:
            response.processes.append(pcb)
    return response


def make_process_counts_response(
    total: int = 0,
    queue_depth: int = 0,
    counts_by_state: dict = None,
) -> pb2.ProcessCountsResponse:
    """Factory for creating ProcessCountsResponse proto responses."""
    response = pb2.ProcessCountsResponse()
    response.total = total
    response.queue_depth = queue_depth
    if counts_by_state:
        for state, count in counts_by_state.items():
            response.counts_by_state[state] = count
    return response


@pytest.fixture
def mock_grpc_channel():
    """Mock async gRPC channel.

    The channel is mocked to avoid actual network connections.
    """
    channel = MagicMock()
    channel.close = AsyncMock()
    return channel


@pytest.fixture
def mock_kernel_stub():
    """Mock KernelServiceStub with AsyncMock methods.

    All KernelService RPC methods are mocked to return appropriate
    default responses.
    """
    stub = MagicMock()

    # Process lifecycle methods
    stub.CreateProcess = AsyncMock(return_value=make_pcb())
    stub.GetProcess = AsyncMock(return_value=make_pcb())
    stub.ScheduleProcess = AsyncMock(return_value=make_pcb(state=pb2.PROCESS_STATE_READY))
    stub.GetNextRunnable = AsyncMock(return_value=make_pcb(state=pb2.PROCESS_STATE_RUNNING))
    stub.TransitionState = AsyncMock(return_value=make_pcb())
    stub.TerminateProcess = AsyncMock(return_value=make_pcb(state=pb2.PROCESS_STATE_TERMINATED))

    # Resource management methods
    stub.RecordUsage = AsyncMock(return_value=make_resource_usage())
    stub.CheckQuota = AsyncMock(return_value=make_quota_result())
    stub.CheckRateLimit = AsyncMock(return_value=make_rate_limit_result())

    # Query methods
    stub.ListProcesses = AsyncMock(return_value=make_list_processes_response())
    stub.GetProcessCounts = AsyncMock(return_value=make_process_counts_response())

    return stub


@pytest.fixture
def mock_engine_stub():
    """Mock EngineServiceStub with AsyncMock methods."""
    stub = MagicMock()
    stub.CreateEnvelope = AsyncMock(return_value=pb2.Envelope())
    stub.CheckBounds = AsyncMock()
    return stub


@pytest.fixture
def mock_kernel_client(mock_grpc_channel, mock_kernel_stub, mock_engine_stub):
    """Configured KernelClient with mocked gRPC.

    This fixture provides a fully mocked KernelClient that can be used
    in unit tests without requiring a real Go kernel server.

    Usage:
        async def test_something(mock_kernel_client):
            proc = await mock_kernel_client.create_process(pid="test-1")
            assert proc.pid == "test-pid"  # Default from mock
    """
    return KernelClient(
        channel=mock_grpc_channel,
        kernel_stub=mock_kernel_stub,
        engine_stub=mock_engine_stub,
    )


__all__ = [
    # Factory functions
    "make_pcb",
    "make_quota_result",
    "make_resource_usage",
    "make_rate_limit_result",
    "make_list_processes_response",
    "make_process_counts_response",
    # Fixtures
    "mock_grpc_channel",
    "mock_kernel_stub",
    "mock_engine_stub",
    "mock_kernel_client",
]
