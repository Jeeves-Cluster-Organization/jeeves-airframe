"""Unit tests for KernelClient.

Tests the Python IPC client for the Rust kernel with mocked transport.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from jeeves_infra.ipc import IpcTransport, IpcError
from jeeves_infra.kernel_client import (
    KernelClient,
    KernelClientError,
    QuotaCheckResult,
    QuotaDefaults,
    SystemStatusResult,
    ProcessInfo,
    DEFAULT_KERNEL_ADDRESS,
)


# =============================================================================
# Dict Factories
# =============================================================================

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


def make_usage_dict(
    llm_calls: int = 0,
    tool_calls: int = 0,
    agent_hops: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> dict:
    return {
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "agent_hops": agent_hops,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
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
    return {
        "within_bounds": within_bounds,
        "exceeded_reason": exceeded_reason,
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


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_transport():
    transport = MagicMock(spec=IpcTransport)
    transport.connect = AsyncMock()
    transport.close = AsyncMock()
    transport.request = AsyncMock(return_value=make_process_dict())
    transport.request_stream = AsyncMock()
    transport.connected = True
    return transport


@pytest.fixture
def mock_kernel_client(mock_transport):
    return KernelClient(transport=mock_transport)


# =============================================================================
# Tests
# =============================================================================


class TestQuotaCheckResult:
    def test_default_values(self):
        result = QuotaCheckResult(within_bounds=True)
        assert result.within_bounds is True
        assert result.exceeded_reason == ""
        assert result.llm_calls == 0

    def test_with_exceeded_reason(self):
        result = QuotaCheckResult(
            within_bounds=False,
            exceeded_reason="max_llm_calls exceeded",
            llm_calls=100,
            tokens_in=5000,
        )
        assert result.within_bounds is False
        assert result.exceeded_reason == "max_llm_calls exceeded"
        assert result.llm_calls == 100


class TestProcessInfo:
    def test_default_values(self):
        info = ProcessInfo(
            pid="test-1", request_id="req-1", user_id="user-1",
            session_id="sess-1", state="NEW", priority="NORMAL",
        )
        assert info.pid == "test-1"
        assert info.state == "NEW"
        assert info.llm_calls == 0

    def test_all_fields(self):
        info = ProcessInfo(
            pid="test-1", request_id="req-1", user_id="user-1",
            session_id="sess-1", state="RUNNING", priority="HIGH",
            llm_calls=5, tool_calls=10, agent_hops=2,
            tokens_in=1000, tokens_out=500, current_stage="executor",
        )
        assert info.state == "RUNNING"
        assert info.priority == "HIGH"
        assert info.llm_calls == 5
        assert info.current_stage == "executor"


class TestKernelClientInit:
    def test_init_with_transport(self, mock_transport):
        client = KernelClient(transport=mock_transport)
        assert client._transport is mock_transport


class TestKernelClientConnect:
    @pytest.mark.asyncio
    async def test_connect_context_manager(self):
        with patch.object(IpcTransport, "connect", new_callable=AsyncMock) as mock_connect, \
             patch.object(IpcTransport, "close", new_callable=AsyncMock) as mock_close:
            async with KernelClient.connect("localhost:50051") as client:
                assert isinstance(client, KernelClient)
                mock_connect.assert_called_once()

            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self, mock_transport):
        client = KernelClient(transport=mock_transport)
        await client.close()
        mock_transport.close.assert_called_once()


class TestProcessLifecycle:
    @pytest.mark.asyncio
    async def test_create_process(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_process_dict(pid="proc-1", state="NEW")

        proc = await mock_kernel_client.create_process(pid="proc-1", user_id="user-1", session_id="sess-1")

        assert proc.pid == "proc-1"
        assert proc.state == "NEW"
        mock_transport.request.assert_called_once()
        call_args = mock_transport.request.call_args
        assert call_args[0][0] == "kernel"
        assert call_args[0][1] == "CreateProcess"

    @pytest.mark.asyncio
    async def test_create_process_with_priority(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_process_dict(pid="proc-1", priority="HIGH")

        proc = await mock_kernel_client.create_process(pid="proc-1", priority="HIGH", max_llm_calls=50)

        assert proc.priority == "HIGH"

    @pytest.mark.asyncio
    async def test_create_process_error_handling(self, mock_kernel_client, mock_transport):
        mock_transport.request.side_effect = IpcError("INTERNAL", "server error")

        with pytest.raises(KernelClientError, match="CreateProcess failed"):
            await mock_kernel_client.create_process(pid="proc-1")

    @pytest.mark.asyncio
    async def test_get_process(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_process_dict(pid="proc-1", state="RUNNING")

        proc = await mock_kernel_client.get_process("proc-1")

        assert proc is not None
        assert proc.pid == "proc-1"
        assert proc.state == "RUNNING"

    @pytest.mark.asyncio
    async def test_get_process_not_found(self, mock_kernel_client, mock_transport):
        mock_transport.request.side_effect = IpcError("NOT_FOUND", "not found")

        proc = await mock_kernel_client.get_process("nonexistent")

        assert proc is None

    @pytest.mark.asyncio
    async def test_schedule_process(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_process_dict(pid="proc-1", state="READY")

        proc = await mock_kernel_client.schedule_process("proc-1")

        assert proc.state == "READY"

    @pytest.mark.asyncio
    async def test_get_next_runnable(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_process_dict(pid="proc-1", state="RUNNING")

        proc = await mock_kernel_client.get_next_runnable()

        assert proc is not None
        assert proc.state == "RUNNING"

    @pytest.mark.asyncio
    async def test_get_next_runnable_empty(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = {"pid": ""}

        proc = await mock_kernel_client.get_next_runnable()

        assert proc is None

    @pytest.mark.asyncio
    async def test_transition_state(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_process_dict(pid="proc-1", state="BLOCKED")

        proc = await mock_kernel_client.transition_state(
            pid="proc-1", new_state="BLOCKED", reason="waiting for user input",
        )

        assert proc.state == "BLOCKED"

    @pytest.mark.asyncio
    async def test_terminate_process(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_process_dict(pid="proc-1", state="TERMINATED")

        proc = await mock_kernel_client.terminate_process(pid="proc-1", reason="completed")

        assert proc.state == "TERMINATED"


class TestResourceManagement:
    @pytest.mark.asyncio
    async def test_record_usage(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_usage_dict(llm_calls=5, tokens_in=1000, tokens_out=500)

        result = await mock_kernel_client.record_usage(
            pid="proc-1", llm_calls=1, tokens_in=100, tokens_out=50,
        )

        assert result.llm_calls == 5
        assert result.tokens_in == 1000

    @pytest.mark.asyncio
    async def test_check_quota_within_bounds(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_quota_dict(within_bounds=True, llm_calls=10)

        result = await mock_kernel_client.check_quota("proc-1")

        assert result.within_bounds is True
        assert result.exceeded_reason == ""
        assert result.llm_calls == 10

    @pytest.mark.asyncio
    async def test_check_quota_exceeded(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_quota_dict(
            within_bounds=False, exceeded_reason="max_llm_calls exceeded", llm_calls=100,
        )

        result = await mock_kernel_client.check_quota("proc-1")

        assert result.within_bounds is False
        assert result.exceeded_reason == "max_llm_calls exceeded"

    @pytest.mark.asyncio
    async def test_check_rate_limit(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = make_rate_limit_dict(allowed=True, remaining=90)

        result = await mock_kernel_client.check_rate_limit(user_id="user-1", endpoint="/api/chat")

        assert result["allowed"] is True
        assert result["remaining"] == 90


class TestConvenienceMethods:
    @pytest.mark.asyncio
    async def test_record_llm_call(self, mock_kernel_client, mock_transport):
        mock_transport.request.side_effect = [
            make_usage_dict(),
            make_quota_dict(within_bounds=True),
        ]

        result = await mock_kernel_client.record_llm_call(pid="proc-1", tokens_in=100, tokens_out=50)

        assert result is None

    @pytest.mark.asyncio
    async def test_record_llm_call_quota_exceeded(self, mock_kernel_client, mock_transport):
        mock_transport.request.side_effect = [
            make_usage_dict(),
            make_quota_dict(within_bounds=False, exceeded_reason="max_llm_calls exceeded"),
        ]

        result = await mock_kernel_client.record_llm_call(pid="proc-1")

        assert result == "max_llm_calls exceeded"

    @pytest.mark.asyncio
    async def test_record_tool_call(self, mock_kernel_client, mock_transport):
        mock_transport.request.side_effect = [
            make_usage_dict(),
            make_quota_dict(within_bounds=True),
        ]

        result = await mock_kernel_client.record_tool_call(pid="proc-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_record_agent_hop(self, mock_kernel_client, mock_transport):
        mock_transport.request.side_effect = [
            make_usage_dict(),
            make_quota_dict(within_bounds=True),
        ]

        result = await mock_kernel_client.record_agent_hop(pid="proc-1")

        assert result is None


class TestQuotaDefaults:
    @pytest.mark.asyncio
    async def test_set_quota_defaults_sends_correct_payload(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = {
            "max_llm_calls": 200,
            "max_tool_calls": 50,
            "max_agent_hops": 10,
            "max_iterations": 20,
            "timeout_seconds": 300,
            "soft_timeout_seconds": 240,
            "max_input_tokens": 100_000,
            "max_output_tokens": 50_000,
            "max_context_tokens": 150_000,
            "rate_limit_rpm": 60,
            "rate_limit_rph": 1000,
            "rate_limit_burst": 10,
            "max_inference_requests": 50,
            "max_inference_input_chars": 500_000,
        }

        result = await mock_kernel_client.set_quota_defaults(max_llm_calls=200)

        mock_transport.request.assert_called_once_with(
            "kernel", "SetQuotaDefaults", {"quota": {"max_llm_calls": 200}},
        )
        assert isinstance(result, QuotaDefaults)
        assert result.max_llm_calls == 200

    @pytest.mark.asyncio
    async def test_set_quota_defaults_filters_none_but_keeps_zero(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = {
            "max_llm_calls": 0,
            "max_agent_hops": 5,
        }

        await mock_kernel_client.set_quota_defaults(max_llm_calls=0, max_tool_calls=None, max_agent_hops=5)

        call_args = mock_transport.request.call_args
        payload = call_args[0][2]
        assert payload == {"quota": {"max_llm_calls": 0, "max_agent_hops": 5}}
        assert "max_tool_calls" not in payload["quota"]

    @pytest.mark.asyncio
    async def test_get_quota_defaults_returns_dataclass(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = {
            "max_llm_calls": 150,
            "max_tool_calls": 75,
            "max_agent_hops": 15,
            "max_iterations": 30,
            "timeout_seconds": 600,
            "soft_timeout_seconds": 480,
            "max_input_tokens": 200_000,
            "max_output_tokens": 100_000,
            "max_context_tokens": 300_000,
            "rate_limit_rpm": 120,
            "rate_limit_rph": 2000,
            "rate_limit_burst": 20,
            "max_inference_requests": 100,
            "max_inference_input_chars": 1_000_000,
        }

        result = await mock_kernel_client.get_quota_defaults()

        mock_transport.request.assert_called_once_with("kernel", "GetQuotaDefaults", {})
        assert isinstance(result, QuotaDefaults)
        assert result.max_llm_calls == 150
        assert result.max_tool_calls == 75
        assert result.max_agent_hops == 15
        assert result.max_iterations == 30
        assert result.timeout_seconds == 600
        assert result.soft_timeout_seconds == 480
        assert result.max_input_tokens == 200_000
        assert result.max_output_tokens == 100_000
        assert result.max_context_tokens == 300_000
        assert result.rate_limit_rpm == 120
        assert result.rate_limit_rph == 2000
        assert result.rate_limit_burst == 20
        assert result.max_inference_requests == 100
        assert result.max_inference_input_chars == 1_000_000

    @pytest.mark.asyncio
    async def test_get_quota_defaults_error_handling(self, mock_kernel_client, mock_transport):
        mock_transport.request.side_effect = IpcError("INTERNAL", "server error")

        with pytest.raises(KernelClientError, match="GetQuotaDefaults failed"):
            await mock_kernel_client.get_quota_defaults()


class TestSystemStatus:
    @pytest.mark.asyncio
    async def test_get_system_status_parses_response(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = {
            "processes": {
                "total": 42,
                "by_state": {"RUNNING": 10, "READY": 5, "BLOCKED": 3},
            },
            "services": {
                "healthy": 8,
                "degraded": 1,
                "unhealthy": 0,
            },
            "orchestration": {
                "active_sessions": 7,
            },
            "commbus": {
                "events_published": 1500,
                "commands_sent": 300,
                "queries_executed": 800,
                "active_subscribers": 12,
            },
        }

        result = await mock_kernel_client.get_system_status()

        mock_transport.request.assert_called_once_with("kernel", "GetSystemStatus", {})
        assert isinstance(result, SystemStatusResult)
        assert result.processes_total == 42
        assert result.processes_by_state == {"RUNNING": 10, "READY": 5, "BLOCKED": 3}
        assert result.services_healthy == 8
        assert result.services_degraded == 1
        assert result.services_unhealthy == 0
        assert result.active_orchestration_sessions == 7
        assert result.commbus_events_published == 1500
        assert result.commbus_commands_sent == 300
        assert result.commbus_queries_executed == 800
        assert result.commbus_active_subscribers == 12

    @pytest.mark.asyncio
    async def test_get_system_status_handles_empty(self, mock_kernel_client, mock_transport):
        mock_transport.request.return_value = {
            "processes": {},
            "services": {},
            "orchestration": {},
            "commbus": {},
        }

        result = await mock_kernel_client.get_system_status()

        assert isinstance(result, SystemStatusResult)
        assert result.processes_total == 0
        assert result.processes_by_state == {}
        assert result.services_healthy == 0
        assert result.services_degraded == 0
        assert result.services_unhealthy == 0
        assert result.active_orchestration_sessions == 0
        assert result.commbus_events_published == 0
        assert result.commbus_commands_sent == 0
        assert result.commbus_queries_executed == 0
        assert result.commbus_active_subscribers == 0
