"""Integration tests for Control Tower resource tracking.

Tests the full resource tracking flow:
- Control Tower → Orchestrator Service integration
- LLMGateway resource callback
- Quota enforcement across the stack

These tests verify the fixes documented in POST_INTEGRATION_ARCHITECTURE_AUDIT.md.

Layer Extraction Compliant (Avionics R4):
    TestLLMGatewayResourceCallback and TestResourceTrackingEndToEnd test
    platform infrastructure and do NOT require capability imports.

    TestCodeAnalysisServiceResourceTracking tests capability-specific integration
    and is SKIPPED - these tests belong in the capability layer.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass

from control_tower.resources.tracker import ResourceTracker
from control_tower.types import ResourceQuota, ResourceUsage
from jeeves_infra.protocols import Envelope


pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.bind.return_value = logger
    return logger


@pytest.fixture
def resource_tracker(mock_logger):
    """Create a ResourceTracker instance."""
    return ResourceTracker(
        logger=mock_logger,
        default_quota=ResourceQuota(
            max_llm_calls=10,
            max_tool_calls=50,
            max_agent_hops=21,
            max_iterations=3,
            timeout_seconds=300,
        ),
    )


@pytest.fixture
def mock_control_tower(resource_tracker):
    """Create a mock Control Tower with real resource tracker."""
    control_tower = MagicMock()
    control_tower.resources = resource_tracker
    return control_tower


class TestLLMGatewayResourceCallback:
    """Test LLMGateway resource callback integration."""

    def test_callback_invoked_on_completion(self, resource_tracker):
        """Test that resource callback is invoked after LLM completion."""
        from jeeves_infra.llm.gateway import LLMGateway, LLMResponse
        from datetime import datetime, timezone

        # Track callback invocations
        callback_calls = []

        def track_callback(tokens_in: int, tokens_out: int):
            resource_tracker.record_usage(
                "test-pid",
                llm_calls=1,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            callback_calls.append((tokens_in, tokens_out))
            return resource_tracker.check_quota("test-pid")

        # Allocate resources for the test PID
        resource_tracker.allocate("test-pid", ResourceQuota(max_llm_calls=5))

        # Create gateway with callback
        mock_settings = MagicMock()
        mock_settings.llm_provider = "llamaserver"
        mock_settings.default_model = "test-model"

        gateway = LLMGateway(
            settings=mock_settings,
            logger=MagicMock(),
            resource_callback=track_callback,
        )

        # Create a mock response
        response = LLMResponse(
            text="Test response",
            tool_calls=[],
            tokens_used=150,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=100.0,
            provider="llamaserver",
            model="test-model",
            cost_usd=0.001,
            timestamp=datetime.now(timezone.utc),
            metadata={},
        )

        # Simulate _update_stats being called (normally happens after _call_provider)
        gateway._update_stats(response)

        # Verify callback was invoked
        assert len(callback_calls) == 1
        assert callback_calls[0] == (100, 50)

        # Verify usage was recorded
        usage = resource_tracker.get_usage("test-pid")
        assert usage.llm_calls == 1
        assert usage.tokens_in == 100
        assert usage.tokens_out == 50

    def test_callback_returns_quota_exceeded(self, resource_tracker):
        """Test that callback returns quota exceeded reason."""
        from jeeves_infra.llm.gateway import LLMGateway, LLMResponse
        from datetime import datetime, timezone

        # Allocate very low quota
        resource_tracker.allocate("test-pid", ResourceQuota(max_llm_calls=1))
        # Use up the quota
        resource_tracker.record_usage("test-pid", llm_calls=2)

        def track_callback(tokens_in: int, tokens_out: int):
            resource_tracker.record_usage(
                "test-pid",
                llm_calls=1,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            return resource_tracker.check_quota("test-pid")

        mock_settings = MagicMock()
        gateway = LLMGateway(
            settings=mock_settings,
            logger=MagicMock(),
            resource_callback=track_callback,
        )

        response = LLMResponse(
            text="Test",
            tool_calls=[],
            tokens_used=100,
            prompt_tokens=50,
            completion_tokens=50,
            latency_ms=100.0,
            provider="llamaserver",
            model="test-model",
            cost_usd=0.001,
            timestamp=datetime.now(timezone.utc),
            metadata={},
        )

        result = gateway._update_stats(response)

        # Should return quota exceeded reason
        assert result == "max_llm_calls_exceeded"

    def test_set_resource_callback_dynamic(self, resource_tracker):
        """Test dynamic callback configuration."""
        from jeeves_infra.llm.gateway import LLMGateway

        mock_settings = MagicMock()
        gateway = LLMGateway(settings=mock_settings, logger=MagicMock())

        # Initially no callback
        assert gateway._resource_callback is None

        # Set callback dynamically
        callback = MagicMock()
        gateway.set_resource_callback(callback)

        assert gateway._resource_callback is callback

        # Clear callback
        gateway.set_resource_callback(None)
        assert gateway._resource_callback is None


@pytest.mark.skip(reason="Layer extraction: Tests capability-specific code - moved to jeeves-capability-code-analyser/tests/")
class TestCodeAnalysisServiceResourceTracking:
    """Test CodeAnalysisService resource tracking integration.

    SKIPPED: These tests import from the capability layer (orchestration.service)
    and violate layer boundaries. Capability-specific integration tests should
    live in the capability's test suite.

    See: jeeves-capability-code-analyser/tests/integration/
    """

    pass  # Tests removed - capability-specific code belongs in capability layer


class TestResourceTrackingEndToEnd:
    """End-to-end tests for resource tracking flow."""

    def test_full_tracking_lifecycle(self, resource_tracker):
        """Test full lifecycle: allocate → record → check → release."""
        pid = "e2e-test-pid"

        # 1. Allocate
        resource_tracker.allocate(
            pid,
            ResourceQuota(
                max_llm_calls=5,
                max_tool_calls=20,
                max_agent_hops=10,
            ),
        )

        # 2. Record usage over multiple calls
        resource_tracker.record_usage(pid, llm_calls=1, agent_hops=1)
        resource_tracker.record_usage(pid, llm_calls=2, tool_calls=5)
        resource_tracker.record_usage(pid, agent_hops=3, tokens_in=200)

        # 3. Check quota - should be within
        assert resource_tracker.check_quota(pid) is None

        # 4. Record more usage to exceed
        resource_tracker.record_usage(pid, llm_calls=3)

        # 5. Check quota - should be exceeded
        result = resource_tracker.check_quota(pid)
        assert result == "max_llm_calls_exceeded"

        # 6. Verify final usage
        usage = resource_tracker.get_usage(pid)
        assert usage.llm_calls == 6
        assert usage.tool_calls == 5
        assert usage.agent_hops == 4
        assert usage.tokens_in == 200

        # 7. Release
        resource_tracker.release(pid)
        assert not resource_tracker.is_tracked(pid)

    def test_system_metrics_accumulate(self, resource_tracker):
        """Test that system metrics accumulate across processes."""
        # Process 1
        resource_tracker.allocate("pid-1", ResourceQuota())
        resource_tracker.record_usage(
            "pid-1",
            llm_calls=3,
            tool_calls=10,
            tokens_in=100,
            tokens_out=50,
        )

        # Process 2
        resource_tracker.allocate("pid-2", ResourceQuota())
        resource_tracker.record_usage(
            "pid-2",
            llm_calls=2,
            tool_calls=5,
            tokens_in=200,
            tokens_out=100,
        )

        # Check system metrics
        system = resource_tracker.get_system_usage()

        assert system["total_processes"] == 2
        assert system["active_processes"] == 2
        assert system["system_llm_calls"] == 5
        assert system["system_tool_calls"] == 15
        assert system["system_tokens_in"] == 300
        assert system["system_tokens_out"] == 150

        # Release one process
        resource_tracker.release("pid-1")

        system = resource_tracker.get_system_usage()
        assert system["active_processes"] == 1
        # Total stays the same
        assert system["system_llm_calls"] == 5

    def test_budget_tracking(self, resource_tracker):
        """Test remaining budget calculation."""
        pid = "budget-test"

        resource_tracker.allocate(
            pid,
            ResourceQuota(
                max_llm_calls=10,
                max_tool_calls=50,
                max_agent_hops=21,
            ),
        )

        # Initial budget
        budget = resource_tracker.get_remaining_budget(pid)
        assert budget["llm_calls"] == 10
        assert budget["tool_calls"] == 50
        assert budget["agent_hops"] == 21

        # Use some resources
        resource_tracker.record_usage(pid, llm_calls=3, tool_calls=20, agent_hops=7)

        # Check remaining
        budget = resource_tracker.get_remaining_budget(pid)
        assert budget["llm_calls"] == 7
        assert budget["tool_calls"] == 30
        assert budget["agent_hops"] == 14
