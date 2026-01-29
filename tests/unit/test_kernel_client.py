"""Unit tests for KernelClient.

Tests the Python gRPC client for the Go kernel with mocked gRPC.
"""

import sys
from pathlib import Path

# Add jeeves-infra root to path for imports
jeeves_infra_root = Path(__file__).parent.parent.parent
if str(jeeves_infra_root) not in sys.path:
    sys.path.insert(0, str(jeeves_infra_root))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import grpc

from jeeves_infra.kernel_client import (
    KernelClient,
    KernelClientError,
    QuotaCheckResult,
    ProcessInfo,
    get_kernel_client,
    close_kernel_client,
    reset_kernel_client,
    DEFAULT_KERNEL_ADDRESS,
)
from jeeves_infra.protocols import engine_pb2 as pb2


# =============================================================================
# Mock Factory Functions (inline to avoid import issues)
# =============================================================================

def make_pcb(
    pid: str = "test-pid",
    request_id: str = "test-request",
    user_id: str = "test-user",
    session_id: str = "test-session",
    state: int = None,
    priority: int = None,
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    current_stage: str = "",
) -> pb2.ProcessControlBlock:
    """Factory for creating ProcessControlBlock proto responses."""
    if state is None:
        state = pb2.PROCESS_STATE_NEW
    if priority is None:
        priority = pb2.SCHEDULING_PRIORITY_NORMAL

    pcb = pb2.ProcessControlBlock()
    pcb.pid = pid
    pcb.request_id = request_id
    pcb.user_id = user_id
    pcb.session_id = session_id
    pcb.state = state
    pcb.priority = priority
    pcb.current_stage = current_stage
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
    """Factory for creating QuotaResult proto responses."""
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


def make_list_processes_response(processes: list = None) -> pb2.ListProcessesResponse:
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


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_grpc_channel():
    """Mock async gRPC channel."""
    channel = MagicMock()
    channel.close = AsyncMock()
    return channel


@pytest.fixture
def mock_kernel_stub():
    """Mock KernelServiceStub with AsyncMock methods."""
    stub = MagicMock()
    stub.CreateProcess = AsyncMock(return_value=make_pcb())
    stub.GetProcess = AsyncMock(return_value=make_pcb())
    stub.ScheduleProcess = AsyncMock(return_value=make_pcb(state=pb2.PROCESS_STATE_READY))
    stub.GetNextRunnable = AsyncMock(return_value=make_pcb(state=pb2.PROCESS_STATE_RUNNING))
    stub.TransitionState = AsyncMock(return_value=make_pcb())
    stub.TerminateProcess = AsyncMock(return_value=make_pcb(state=pb2.PROCESS_STATE_TERMINATED))
    stub.RecordUsage = AsyncMock(return_value=make_resource_usage())
    stub.CheckQuota = AsyncMock(return_value=make_quota_result())
    stub.CheckRateLimit = AsyncMock(return_value=make_rate_limit_result())
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
    """Configured KernelClient with mocked gRPC."""
    return KernelClient(
        channel=mock_grpc_channel,
        kernel_stub=mock_kernel_stub,
        engine_stub=mock_engine_stub,
    )


# =============================================================================
# Tests
# =============================================================================


class TestQuotaCheckResult:
    """Tests for QuotaCheckResult dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        result = QuotaCheckResult(within_bounds=True)
        assert result.within_bounds is True
        assert result.exceeded_reason == ""
        assert result.llm_calls == 0
        assert result.tool_calls == 0
        assert result.agent_hops == 0
        assert result.tokens_in == 0
        assert result.tokens_out == 0

    def test_with_exceeded_reason(self):
        """Test with quota exceeded."""
        result = QuotaCheckResult(
            within_bounds=False,
            exceeded_reason="max_llm_calls exceeded",
            llm_calls=100,
            tokens_in=5000,
        )
        assert result.within_bounds is False
        assert result.exceeded_reason == "max_llm_calls exceeded"
        assert result.llm_calls == 100
        assert result.tokens_in == 5000


class TestProcessInfo:
    """Tests for ProcessInfo dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        info = ProcessInfo(
            pid="test-1",
            request_id="req-1",
            user_id="user-1",
            session_id="sess-1",
            state="NEW",
            priority="NORMAL",
        )
        assert info.pid == "test-1"
        assert info.state == "NEW"
        assert info.priority == "NORMAL"
        assert info.llm_calls == 0
        assert info.current_stage == ""

    def test_all_fields(self):
        """Test with all fields populated."""
        info = ProcessInfo(
            pid="test-1",
            request_id="req-1",
            user_id="user-1",
            session_id="sess-1",
            state="RUNNING",
            priority="HIGH",
            llm_calls=5,
            tool_calls=10,
            agent_hops=2,
            tokens_in=1000,
            tokens_out=500,
            current_stage="executor",
        )
        assert info.state == "RUNNING"
        assert info.priority == "HIGH"
        assert info.llm_calls == 5
        assert info.current_stage == "executor"


class TestKernelClientInit:
    """Tests for KernelClient initialization."""

    def test_init_with_channel(self, mock_grpc_channel):
        """Test initialization with just a channel."""
        client = KernelClient(channel=mock_grpc_channel)
        assert client._channel is mock_grpc_channel
        assert client._closed is False

    def test_init_with_stubs(self, mock_grpc_channel, mock_kernel_stub, mock_engine_stub):
        """Test initialization with pre-created stubs."""
        client = KernelClient(
            channel=mock_grpc_channel,
            kernel_stub=mock_kernel_stub,
            engine_stub=mock_engine_stub,
        )
        assert client._kernel_stub is mock_kernel_stub
        assert client._engine_stub is mock_engine_stub


class TestKernelClientConnect:
    """Tests for KernelClient.connect() context manager."""

    @pytest.mark.asyncio
    async def test_connect_context_manager(self):
        """Test connect as async context manager."""
        with patch("jeeves_infra.kernel_client.grpc_aio") as mock_grpc_aio:
            mock_channel = MagicMock()
            mock_channel.close = AsyncMock()
            mock_grpc_aio.insecure_channel.return_value = mock_channel

            async with KernelClient.connect("localhost:50051") as client:
                assert client._channel is mock_channel
                assert client._closed is False

            # Channel should be closed after context exits
            mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_secure_channel(self):
        """Test connect with secure channel."""
        with patch("jeeves_infra.kernel_client.grpc_aio") as mock_grpc_aio:
            with patch("jeeves_infra.kernel_client.grpc") as mock_grpc:
                mock_channel = MagicMock()
                mock_channel.close = AsyncMock()
                mock_grpc_aio.secure_channel.return_value = mock_channel
                mock_grpc.ssl_channel_credentials.return_value = MagicMock()

                async with KernelClient.connect("localhost:50051", secure=True) as client:
                    assert client._channel is mock_channel

                mock_grpc_aio.secure_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self, mock_grpc_channel):
        """Test close method."""
        client = KernelClient(channel=mock_grpc_channel)
        assert client._closed is False

        await client.close()
        assert client._closed is True
        mock_grpc_channel.close.assert_called_once()

        # Second close should be no-op
        await client.close()
        mock_grpc_channel.close.assert_called_once()  # Still only once


class TestProcessLifecycle:
    """Tests for process lifecycle methods."""

    @pytest.mark.asyncio
    async def test_create_process(self, mock_kernel_client, mock_kernel_stub):
        """Test create_process method."""
        mock_kernel_stub.CreateProcess.return_value = make_pcb(
            pid="proc-1",
            state=pb2.PROCESS_STATE_NEW,
        )

        proc = await mock_kernel_client.create_process(
            pid="proc-1",
            user_id="user-1",
            session_id="sess-1",
        )

        assert proc.pid == "proc-1"
        assert proc.state == "NEW"
        mock_kernel_stub.CreateProcess.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_process_with_priority(self, mock_kernel_client, mock_kernel_stub):
        """Test create_process with custom priority."""
        mock_kernel_stub.CreateProcess.return_value = make_pcb(
            pid="proc-1",
            priority=pb2.SCHEDULING_PRIORITY_HIGH,
        )

        proc = await mock_kernel_client.create_process(
            pid="proc-1",
            priority="HIGH",
            max_llm_calls=50,
        )

        assert proc.priority == "HIGH"

    @pytest.mark.asyncio
    async def test_create_process_error_handling(self, mock_kernel_client, mock_kernel_stub):
        """Test create_process error handling."""
        mock_kernel_stub.CreateProcess.side_effect = grpc.RpcError()

        with pytest.raises(KernelClientError, match="CreateProcess failed"):
            await mock_kernel_client.create_process(pid="proc-1")

    @pytest.mark.asyncio
    async def test_get_process(self, mock_kernel_client, mock_kernel_stub):
        """Test get_process method."""
        mock_kernel_stub.GetProcess.return_value = make_pcb(
            pid="proc-1",
            state=pb2.PROCESS_STATE_RUNNING,
        )

        proc = await mock_kernel_client.get_process("proc-1")

        assert proc is not None
        assert proc.pid == "proc-1"
        assert proc.state == "RUNNING"

    @pytest.mark.asyncio
    async def test_get_process_not_found(self, mock_kernel_client, mock_kernel_stub):
        """Test get_process returns None for not found."""
        error = grpc.RpcError()
        error.code = lambda: grpc.StatusCode.NOT_FOUND
        mock_kernel_stub.GetProcess.side_effect = error

        proc = await mock_kernel_client.get_process("nonexistent")

        assert proc is None

    @pytest.mark.asyncio
    async def test_schedule_process(self, mock_kernel_client, mock_kernel_stub):
        """Test schedule_process method."""
        mock_kernel_stub.ScheduleProcess.return_value = make_pcb(
            pid="proc-1",
            state=pb2.PROCESS_STATE_READY,
        )

        proc = await mock_kernel_client.schedule_process("proc-1")

        assert proc.state == "READY"

    @pytest.mark.asyncio
    async def test_get_next_runnable(self, mock_kernel_client, mock_kernel_stub):
        """Test get_next_runnable method."""
        mock_kernel_stub.GetNextRunnable.return_value = make_pcb(
            pid="proc-1",
            state=pb2.PROCESS_STATE_RUNNING,
        )

        proc = await mock_kernel_client.get_next_runnable()

        assert proc is not None
        assert proc.state == "RUNNING"

    @pytest.mark.asyncio
    async def test_get_next_runnable_empty(self, mock_kernel_client, mock_kernel_stub):
        """Test get_next_runnable returns None when queue empty."""
        mock_kernel_stub.GetNextRunnable.return_value = pb2.ProcessControlBlock()

        proc = await mock_kernel_client.get_next_runnable()

        assert proc is None

    @pytest.mark.asyncio
    async def test_transition_state(self, mock_kernel_client, mock_kernel_stub):
        """Test transition_state method."""
        mock_kernel_stub.TransitionState.return_value = make_pcb(
            pid="proc-1",
            state=pb2.PROCESS_STATE_BLOCKED,
        )

        proc = await mock_kernel_client.transition_state(
            pid="proc-1",
            new_state="BLOCKED",
            reason="waiting for user input",
        )

        assert proc.state == "BLOCKED"

    @pytest.mark.asyncio
    async def test_terminate_process(self, mock_kernel_client, mock_kernel_stub):
        """Test terminate_process method."""
        mock_kernel_stub.TerminateProcess.return_value = make_pcb(
            pid="proc-1",
            state=pb2.PROCESS_STATE_TERMINATED,
        )

        proc = await mock_kernel_client.terminate_process(
            pid="proc-1",
            reason="completed",
        )

        assert proc.state == "TERMINATED"


class TestResourceManagement:
    """Tests for resource management methods."""

    @pytest.mark.asyncio
    async def test_record_usage(self, mock_kernel_client, mock_kernel_stub):
        """Test record_usage method."""
        mock_kernel_stub.RecordUsage.return_value = make_resource_usage(
            llm_calls=5,
            tokens_in=1000,
            tokens_out=500,
        )

        result = await mock_kernel_client.record_usage(
            pid="proc-1",
            llm_calls=1,
            tokens_in=100,
            tokens_out=50,
        )

        assert result.llm_calls == 5
        assert result.tokens_in == 1000

    @pytest.mark.asyncio
    async def test_check_quota_within_bounds(self, mock_kernel_client, mock_kernel_stub):
        """Test check_quota when within bounds."""
        mock_kernel_stub.CheckQuota.return_value = make_quota_result(
            within_bounds=True,
            llm_calls=10,
        )

        result = await mock_kernel_client.check_quota("proc-1")

        assert result.within_bounds is True
        assert result.exceeded_reason == ""
        assert result.llm_calls == 10

    @pytest.mark.asyncio
    async def test_check_quota_exceeded(self, mock_kernel_client, mock_kernel_stub):
        """Test check_quota when quota exceeded."""
        mock_kernel_stub.CheckQuota.return_value = make_quota_result(
            within_bounds=False,
            exceeded_reason="max_llm_calls exceeded",
            llm_calls=100,
        )

        result = await mock_kernel_client.check_quota("proc-1")

        assert result.within_bounds is False
        assert result.exceeded_reason == "max_llm_calls exceeded"

    @pytest.mark.asyncio
    async def test_check_rate_limit(self, mock_kernel_client, mock_kernel_stub):
        """Test check_rate_limit method."""
        mock_kernel_stub.CheckRateLimit.return_value = make_rate_limit_result(
            allowed=True,
            remaining=90,
        )

        result = await mock_kernel_client.check_rate_limit(
            user_id="user-1",
            endpoint="/api/chat",
        )

        assert result["allowed"] is True
        assert result["remaining"] == 90


class TestQueries:
    """Tests for query methods."""

    @pytest.mark.asyncio
    async def test_list_processes(self, mock_kernel_client, mock_kernel_stub):
        """Test list_processes method."""
        mock_kernel_stub.ListProcesses.return_value = make_list_processes_response(
            processes=[
                make_pcb(pid="proc-1"),
                make_pcb(pid="proc-2"),
            ]
        )

        procs = await mock_kernel_client.list_processes()

        assert len(procs) == 2
        assert procs[0].pid == "proc-1"
        assert procs[1].pid == "proc-2"

    @pytest.mark.asyncio
    async def test_list_processes_with_filters(self, mock_kernel_client, mock_kernel_stub):
        """Test list_processes with state filter."""
        mock_kernel_stub.ListProcesses.return_value = make_list_processes_response(
            processes=[make_pcb(pid="proc-1", state=pb2.PROCESS_STATE_RUNNING)]
        )

        procs = await mock_kernel_client.list_processes(
            state="RUNNING",
            user_id="user-1",
        )

        assert len(procs) == 1

    @pytest.mark.asyncio
    async def test_get_process_counts(self, mock_kernel_client, mock_kernel_stub):
        """Test get_process_counts method."""
        mock_kernel_stub.GetProcessCounts.return_value = make_process_counts_response(
            total=10,
            queue_depth=3,
            counts_by_state={"RUNNING": 5, "READY": 3, "BLOCKED": 2},
        )

        counts = await mock_kernel_client.get_process_counts()

        assert counts["total"] == 10
        assert counts["queue_depth"] == 3
        assert counts["RUNNING"] == 5


class TestConvenienceMethods:
    """Tests for high-level convenience methods."""

    @pytest.mark.asyncio
    async def test_record_llm_call(self, mock_kernel_client, mock_kernel_stub):
        """Test record_llm_call convenience method."""
        mock_kernel_stub.RecordUsage.return_value = make_resource_usage()
        mock_kernel_stub.CheckQuota.return_value = make_quota_result(within_bounds=True)

        result = await mock_kernel_client.record_llm_call(
            pid="proc-1",
            tokens_in=100,
            tokens_out=50,
        )

        assert result is None  # No exceeded reason

    @pytest.mark.asyncio
    async def test_record_llm_call_quota_exceeded(self, mock_kernel_client, mock_kernel_stub):
        """Test record_llm_call when quota exceeded."""
        mock_kernel_stub.RecordUsage.return_value = make_resource_usage()
        mock_kernel_stub.CheckQuota.return_value = make_quota_result(
            within_bounds=False,
            exceeded_reason="max_llm_calls exceeded",
        )

        result = await mock_kernel_client.record_llm_call(pid="proc-1")

        assert result == "max_llm_calls exceeded"

    @pytest.mark.asyncio
    async def test_record_tool_call(self, mock_kernel_client, mock_kernel_stub):
        """Test record_tool_call convenience method."""
        mock_kernel_stub.RecordUsage.return_value = make_resource_usage()
        mock_kernel_stub.CheckQuota.return_value = make_quota_result(within_bounds=True)

        result = await mock_kernel_client.record_tool_call(pid="proc-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_record_agent_hop(self, mock_kernel_client, mock_kernel_stub):
        """Test record_agent_hop convenience method."""
        mock_kernel_stub.RecordUsage.return_value = make_resource_usage()
        mock_kernel_stub.CheckQuota.return_value = make_quota_result(within_bounds=True)

        result = await mock_kernel_client.record_agent_hop(pid="proc-1")

        assert result is None


class TestGlobalClientManagement:
    """Tests for global client management functions."""

    @pytest.fixture(autouse=True)
    def reset_global_client(self):
        """Reset global client before and after each test."""
        reset_kernel_client()
        yield
        reset_kernel_client()

    @pytest.mark.asyncio
    async def test_get_kernel_client_creates_singleton(self):
        """Test get_kernel_client creates singleton."""
        with patch("jeeves_infra.kernel_client.grpc_aio") as mock_grpc_aio:
            mock_channel = MagicMock()
            mock_grpc_aio.insecure_channel.return_value = mock_channel

            client1 = await get_kernel_client("localhost:50051")
            client2 = await get_kernel_client("localhost:50051")

            assert client1 is client2
            mock_grpc_aio.insecure_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_kernel_client(self):
        """Test close_kernel_client."""
        with patch("jeeves_infra.kernel_client.grpc_aio") as mock_grpc_aio:
            mock_channel = MagicMock()
            mock_channel.close = AsyncMock()
            mock_grpc_aio.insecure_channel.return_value = mock_channel

            await get_kernel_client("localhost:50051")
            await close_kernel_client()

            mock_channel.close.assert_called_once()

    def test_reset_kernel_client(self):
        """Test reset_kernel_client."""
        # Just verify it doesn't raise
        reset_kernel_client()


class TestPcbToInfo:
    """Tests for _pcb_to_info conversion method."""

    def test_state_mapping(self, mock_kernel_client):
        """Test process state mapping."""
        test_cases = [
            (pb2.PROCESS_STATE_NEW, "NEW"),
            (pb2.PROCESS_STATE_READY, "READY"),
            (pb2.PROCESS_STATE_RUNNING, "RUNNING"),
            (pb2.PROCESS_STATE_WAITING, "WAITING"),
            (pb2.PROCESS_STATE_BLOCKED, "BLOCKED"),
            (pb2.PROCESS_STATE_TERMINATED, "TERMINATED"),
            (pb2.PROCESS_STATE_ZOMBIE, "ZOMBIE"),
        ]

        for proto_state, expected_str in test_cases:
            pcb = make_pcb(state=proto_state)
            info = mock_kernel_client._pcb_to_info(pcb)
            assert info.state == expected_str, f"Expected {expected_str}, got {info.state}"

    def test_priority_mapping(self, mock_kernel_client):
        """Test scheduling priority mapping."""
        test_cases = [
            (pb2.SCHEDULING_PRIORITY_REALTIME, "REALTIME"),
            (pb2.SCHEDULING_PRIORITY_HIGH, "HIGH"),
            (pb2.SCHEDULING_PRIORITY_NORMAL, "NORMAL"),
            (pb2.SCHEDULING_PRIORITY_LOW, "LOW"),
            (pb2.SCHEDULING_PRIORITY_IDLE, "IDLE"),
        ]

        for proto_priority, expected_str in test_cases:
            pcb = make_pcb(priority=proto_priority)
            info = mock_kernel_client._pcb_to_info(pcb)
            assert info.priority == expected_str, f"Expected {expected_str}, got {info.priority}"
