"""Tests for jeeves_infra.resource_tracker module."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from jeeves_infra.resource_tracker import (
    ResourceTracker,
    ResourceUsage,
    LocalQuotaResult,
)
from jeeves_infra.config import ResourceConfig


class TestResourceUsage:
    """Tests for ResourceUsage dataclass."""

    def test_default_values(self):
        """Test default usage values are zero."""
        usage = ResourceUsage()
        assert usage.llm_calls == 0
        assert usage.tool_calls == 0
        assert usage.agent_hops == 0
        assert usage.tokens_in == 0
        assert usage.tokens_out == 0
        assert usage.iterations == 0


class TestLocalQuotaResult:
    """Tests for LocalQuotaResult dataclass."""

    def test_within_bounds(self):
        """Test result when within bounds."""
        result = LocalQuotaResult(
            within_bounds=True,
            llm_calls_remaining=50,
            tool_calls_remaining=100,
            agent_hops_remaining=10,
        )
        assert result.within_bounds is True
        assert result.exceeded_reason is None

    def test_exceeded(self):
        """Test result when quota exceeded."""
        result = LocalQuotaResult(
            within_bounds=False,
            exceeded_reason="max_llm_calls exceeded",
            llm_calls_remaining=0,
            tool_calls_remaining=50,
            agent_hops_remaining=5,
        )
        assert result.within_bounds is False
        assert result.exceeded_reason == "max_llm_calls exceeded"


class TestResourceTrackerLocalMode:
    """Tests for ResourceTracker without kernel (local tracking)."""

    def test_has_kernel_false(self):
        """Test has_kernel returns False without kernel."""
        tracker = ResourceTracker()
        assert tracker.has_kernel is False

    def test_config_default(self):
        """Test default config is used when not provided."""
        tracker = ResourceTracker()
        assert tracker.config.max_llm_calls == 100

    def test_config_custom(self):
        """Test custom config is used."""
        config = ResourceConfig(max_llm_calls=50)
        tracker = ResourceTracker(config=config)
        assert tracker.config.max_llm_calls == 50

    @pytest.mark.asyncio
    async def test_record_llm_call(self):
        """Test recording LLM calls locally."""
        tracker = ResourceTracker()
        result = await tracker.record_llm_call("pid-1", tokens_in=100, tokens_out=50)
        assert result is None  # No quota exceeded

        usage = tracker.get_usage("pid-1")
        assert usage.llm_calls == 1
        assert usage.tokens_in == 100
        assert usage.tokens_out == 50

    @pytest.mark.asyncio
    async def test_record_tool_call(self):
        """Test recording tool calls locally."""
        tracker = ResourceTracker()
        result = await tracker.record_tool_call("pid-1")
        assert result is None

        usage = tracker.get_usage("pid-1")
        assert usage.tool_calls == 1

    @pytest.mark.asyncio
    async def test_record_agent_hop(self):
        """Test recording agent hops locally."""
        tracker = ResourceTracker()
        result = await tracker.record_agent_hop("pid-1")
        assert result is None

        usage = tracker.get_usage("pid-1")
        assert usage.agent_hops == 1

    @pytest.mark.asyncio
    async def test_record_iteration(self):
        """Test recording iterations locally."""
        tracker = ResourceTracker()
        result = await tracker.record_iteration("pid-1")
        assert result is None

        usage = tracker.get_usage("pid-1")
        assert usage.iterations == 1

    @pytest.mark.asyncio
    async def test_llm_quota_exceeded(self):
        """Test quota exceeded detection for LLM calls."""
        config = ResourceConfig(max_llm_calls=2)
        tracker = ResourceTracker(config=config)

        await tracker.record_llm_call("pid-1")
        await tracker.record_llm_call("pid-1")
        result = await tracker.record_llm_call("pid-1")  # Exceeds

        assert result is not None
        assert "max_llm_calls exceeded" in result
        assert "3/2" in result

    @pytest.mark.asyncio
    async def test_tool_quota_exceeded(self):
        """Test quota exceeded detection for tool calls."""
        config = ResourceConfig(max_tool_calls=1)
        tracker = ResourceTracker(config=config)

        await tracker.record_tool_call("pid-1")
        result = await tracker.record_tool_call("pid-1")  # Exceeds

        assert result is not None
        assert "max_tool_calls exceeded" in result

    @pytest.mark.asyncio
    async def test_agent_hops_quota_exceeded(self):
        """Test quota exceeded detection for agent hops."""
        config = ResourceConfig(max_agent_hops=1)
        tracker = ResourceTracker(config=config)

        await tracker.record_agent_hop("pid-1")
        result = await tracker.record_agent_hop("pid-1")  # Exceeds

        assert result is not None
        assert "max_agent_hops exceeded" in result

    @pytest.mark.asyncio
    async def test_iterations_quota_exceeded(self):
        """Test quota exceeded detection for iterations."""
        config = ResourceConfig(max_iterations=1)
        tracker = ResourceTracker(config=config)

        await tracker.record_iteration("pid-1")
        result = await tracker.record_iteration("pid-1")  # Exceeds

        assert result is not None
        assert "max_iterations exceeded" in result

    @pytest.mark.asyncio
    async def test_check_quota_within_bounds(self):
        """Test quota check when within bounds."""
        tracker = ResourceTracker()
        await tracker.record_llm_call("pid-1")

        result = await tracker.check_quota("pid-1")
        assert result.within_bounds is True
        assert result.exceeded_reason is None
        assert result.llm_calls_remaining == 99

    @pytest.mark.asyncio
    async def test_check_quota_exceeded(self):
        """Test quota check when exceeded."""
        config = ResourceConfig(max_llm_calls=1)
        tracker = ResourceTracker(config=config)
        await tracker.record_llm_call("pid-1")

        result = await tracker.check_quota("pid-1")
        assert result.within_bounds is False
        assert result.exceeded_reason == "max_llm_calls exceeded"

    def test_get_usage_unknown_pid(self):
        """Test get_usage returns empty for unknown PID."""
        tracker = ResourceTracker()
        usage = tracker.get_usage("unknown-pid")
        assert usage.llm_calls == 0

    def test_reset(self):
        """Test reset clears usage for a PID."""
        tracker = ResourceTracker()
        tracker._local_usage["pid-1"] = ResourceUsage(llm_calls=5)

        tracker.reset("pid-1")
        usage = tracker.get_usage("pid-1")
        assert usage.llm_calls == 0

    def test_reset_all(self):
        """Test reset_all clears all usage."""
        tracker = ResourceTracker()
        tracker._local_usage["pid-1"] = ResourceUsage(llm_calls=5)
        tracker._local_usage["pid-2"] = ResourceUsage(llm_calls=3)

        tracker.reset_all()
        assert len(tracker._local_usage) == 0

    @pytest.mark.asyncio
    async def test_multiple_pids_isolated(self):
        """Test that different PIDs have isolated tracking."""
        tracker = ResourceTracker()

        await tracker.record_llm_call("pid-1")
        await tracker.record_llm_call("pid-1")
        await tracker.record_llm_call("pid-2")

        assert tracker.get_usage("pid-1").llm_calls == 2
        assert tracker.get_usage("pid-2").llm_calls == 1


class TestResourceTrackerKernelMode:
    """Tests for ResourceTracker with kernel client."""

    @pytest.fixture
    def mock_kernel(self):
        """Create a mock kernel client."""
        kernel = MagicMock()
        kernel.record_llm_call = AsyncMock(return_value=None)
        kernel.record_tool_call = AsyncMock(return_value=None)
        kernel.record_agent_hop = AsyncMock(return_value=None)
        kernel.check_quota = AsyncMock(return_value=MagicMock(
            within_bounds=True,
            exceeded_reason=None,
            llm_calls_remaining=50,
            tool_calls_remaining=100,
            agent_hops_remaining=10,
        ))
        return kernel

    def test_has_kernel_true(self, mock_kernel):
        """Test has_kernel returns True with kernel."""
        tracker = ResourceTracker(kernel_client=mock_kernel)
        assert tracker.has_kernel is True

    @pytest.mark.asyncio
    async def test_record_llm_call_delegates_to_kernel(self, mock_kernel):
        """Test LLM call recording delegates to kernel."""
        tracker = ResourceTracker(kernel_client=mock_kernel)

        result = await tracker.record_llm_call("pid-1", tokens_in=100, tokens_out=50)

        mock_kernel.record_llm_call.assert_called_once_with("pid-1", 100, 50)
        assert result is None

    @pytest.mark.asyncio
    async def test_record_tool_call_delegates_to_kernel(self, mock_kernel):
        """Test tool call recording delegates to kernel."""
        tracker = ResourceTracker(kernel_client=mock_kernel)

        await tracker.record_tool_call("pid-1")

        mock_kernel.record_tool_call.assert_called_once_with("pid-1")

    @pytest.mark.asyncio
    async def test_record_agent_hop_delegates_to_kernel(self, mock_kernel):
        """Test agent hop recording delegates to kernel."""
        tracker = ResourceTracker(kernel_client=mock_kernel)

        await tracker.record_agent_hop("pid-1")

        mock_kernel.record_agent_hop.assert_called_once_with("pid-1")

    @pytest.mark.asyncio
    async def test_check_quota_delegates_to_kernel(self, mock_kernel):
        """Test quota check delegates to kernel."""
        tracker = ResourceTracker(kernel_client=mock_kernel)

        result = await tracker.check_quota("pid-1")

        mock_kernel.check_quota.assert_called_once_with("pid-1")
        assert result.within_bounds is True

    @pytest.mark.asyncio
    async def test_kernel_failure_falls_back_to_local(self, mock_kernel):
        """Test fallback to local tracking on kernel failure."""
        mock_kernel.record_llm_call.side_effect = Exception("Connection failed")
        tracker = ResourceTracker(kernel_client=mock_kernel)

        # Should not raise, falls back to local
        result = await tracker.record_llm_call("pid-1", tokens_in=100, tokens_out=50)

        assert result is None
        usage = tracker.get_usage("pid-1")
        assert usage.llm_calls == 1

    @pytest.mark.asyncio
    async def test_iteration_always_local(self, mock_kernel):
        """Test iteration recording is always local (kernel doesn't track)."""
        tracker = ResourceTracker(kernel_client=mock_kernel)

        await tracker.record_iteration("pid-1")

        # Kernel methods should not be called for iterations
        mock_kernel.record_llm_call.assert_not_called()
        usage = tracker.get_usage("pid-1")
        assert usage.iterations == 1
