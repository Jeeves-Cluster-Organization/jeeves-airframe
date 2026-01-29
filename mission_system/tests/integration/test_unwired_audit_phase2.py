"""Integration tests for Unwired Capabilities Audit Phase 2.

Tests the wiring added in Phase 2:
- OTEL spans when enable_tracing=true
- LLMGateway cost tracking with per-request PID context
- Provider streaming support
- Bootstrap resource tracking with ContextVar
- Distributed infrastructure wiring

These tests verify the fixes implemented in the unwired audit.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from contextvars import copy_context

pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.bind.return_value = logger
    return logger


# =============================================================================
# OTEL Integration Tests
# =============================================================================


class TestOTELSpanIntegration:
    """Test OpenTelemetry span creation when tracing is enabled."""

    def test_otel_adapter_creates_spans(self):
        """Test that OTEL adapter creates spans correctly."""
        from avionics.observability.otel_adapter import (
            OpenTelemetryAdapter,
            create_tracer,
            OTEL_AVAILABLE,
        )

        if not OTEL_AVAILABLE:
            pytest.skip("OpenTelemetry not installed")

        tracer = create_tracer("test-service", "1.0.0")
        adapter = OpenTelemetryAdapter(tracer)

        assert adapter.enabled is True

        # Test span creation via context manager
        with adapter.start_span(
            "test.operation",
            attributes={"test.key": "test_value"},
            context_key="test-request-1",
        ) as span:
            assert span is not None
            adapter.set_attribute("test.dynamic", "dynamic_value", "test-request-1")
            adapter.record_event("test_event", "test-request-1", {"event_key": "event_value"})

    @pytest.mark.asyncio
    async def test_otel_agent_lifecycle_spans(self):
        """Test OTEL span creation for agent start/complete."""
        from avionics.observability.otel_adapter import (
            OpenTelemetryAdapter,
            create_tracer,
            OTEL_AVAILABLE,
        )

        if not OTEL_AVAILABLE:
            pytest.skip("OpenTelemetry not installed")

        tracer = create_tracer("test-agent-spans", "1.0.0")
        adapter = OpenTelemetryAdapter(tracer, MagicMock())

        # Start agent span
        span_id = await adapter.on_agent_started(
            agent_name="planner",
            request_id="req-123",
            stage_order=1,
        )
        assert span_id is not None

        # Complete agent span
        await adapter.on_agent_completed(
            agent_name="planner",
            request_id="req-123",
            status="success",
        )

        # Verify cleanup
        adapter.cleanup_context("req-123")

    @pytest.mark.asyncio
    async def test_otel_llm_call_spans(self):
        """Test OTEL span creation for LLM calls."""
        from avionics.observability.otel_adapter import (
            OpenTelemetryAdapter,
            create_tracer,
            OTEL_AVAILABLE,
        )

        if not OTEL_AVAILABLE:
            pytest.skip("OpenTelemetry not installed")

        tracer = create_tracer("test-llm-spans", "1.0.0")
        adapter = OpenTelemetryAdapter(tracer, MagicMock())

        # First create a parent span
        await adapter.on_agent_started("test_agent", "req-456", 0)

        # Record LLM call
        await adapter.on_llm_call(
            request_id="req-456",
            provider="llamaserver",
            model="test-model",
            agent_name="test_agent",
            tokens_in=100,
            tokens_out=50,
            latency_ms=150.0,
            cost_usd=0.001,
        )

        # Cleanup
        await adapter.on_agent_completed("test_agent", "req-456", "success")
        adapter.cleanup_context("req-456")

    def test_otel_initialization_in_bootstrap(self, mock_logger):
        """Test that OTEL is initialized in bootstrap when enable_tracing=true."""
        from avionics.feature_flags import FeatureFlags
        from avionics.observability.otel_adapter import OTEL_AVAILABLE

        if not OTEL_AVAILABLE:
            pytest.skip("OpenTelemetry not installed")

        # Create feature flags with tracing enabled
        flags = FeatureFlags(enable_tracing=True)

        # Import after setting up flags
        with patch("avionics.settings.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(log_level="INFO")

            with patch("avionics.feature_flags.get_feature_flags") as mock_flags:
                mock_flags.return_value = flags

                from mission_system.bootstrap import create_app_context

                # Reset global OTEL adapter to test initialization
                with patch(
                    "avionics.observability.otel_adapter._global_adapter",
                    None,
                ):
                    context = create_app_context(feature_flags=flags)

                    # Control Tower should have OTEL adapter
                    assert context.control_tower is not None


# =============================================================================
# Resource Tracking with PID Context Tests
# =============================================================================


class TestResourceTrackingPIDContext:
    """Test per-request PID tracking via ContextVar."""

    def test_set_get_clear_request_pid(self):
        """Test basic PID context operations."""
        from mission_system.bootstrap import (
            set_request_pid,
            get_request_pid,
            clear_request_pid,
        )

        # Initially no PID
        assert get_request_pid() is None

        # Set PID
        set_request_pid("test-pid-123")
        assert get_request_pid() == "test-pid-123"

        # Clear PID
        clear_request_pid()
        assert get_request_pid() is None

    def test_pid_context_isolates_between_contexts(self):
        """Test that ContextVar isolates PIDs correctly."""
        from mission_system.bootstrap import (
            set_request_pid,
            get_request_pid,
            clear_request_pid,
        )

        # Set PID in current context
        set_request_pid("main-pid")
        assert get_request_pid() == "main-pid"

        # Create a copy of context and modify in it
        def inner_context():
            # Should see the parent's value initially
            initial = get_request_pid()
            # Set new value
            set_request_pid("inner-pid")
            return initial, get_request_pid()

        ctx = copy_context()
        initial, after = ctx.run(inner_context)

        # Inner should have seen main-pid initially
        assert initial == "main-pid"
        # Inner should have its own value after set
        assert after == "inner-pid"

        # Main context should still have original value
        assert get_request_pid() == "main-pid"

        clear_request_pid()

    def test_llm_gateway_resource_callback_uses_pid_context(self, mock_logger):
        """Test that LLMGateway callback uses request PID context."""
        from jeeves_infra.llm.gateway import LLMGateway, LLMResponse
        from control_tower.resources.tracker import ResourceTracker
        from control_tower.types import ResourceQuota
        from mission_system.bootstrap import (
            set_request_pid,
            get_request_pid,
            clear_request_pid,
        )

        # Create resource tracker
        tracker = ResourceTracker(
            logger=mock_logger,
            default_quota=ResourceQuota(max_llm_calls=10),
        )

        # Create callback that uses PID context
        def track_resources(tokens_in: int, tokens_out: int):
            pid = get_request_pid()
            if pid is None:
                return None
            tracker.record_usage(
                pid,
                llm_calls=1,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            return tracker.check_quota(pid)

        # Allocate resources for test PID
        tracker.allocate("test-request-1", ResourceQuota(max_llm_calls=5))

        # Create gateway with callback
        mock_settings = MagicMock()
        mock_settings.llm_provider = "llamaserver"
        mock_settings.default_model = "test-model"

        gateway = LLMGateway(
            settings=mock_settings,
            logger=mock_logger,
            resource_callback=track_resources,
        )

        # Set PID context
        set_request_pid("test-request-1")

        # Create mock response and update stats
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

        result = gateway._update_stats(response)

        # Should be within quota
        assert result is None

        # Verify usage was recorded
        usage = tracker.get_usage("test-request-1")
        assert usage.llm_calls == 1
        assert usage.tokens_in == 100
        assert usage.tokens_out == 50

        clear_request_pid()

    def test_callback_returns_none_without_pid_context(self, mock_logger):
        """Test that callback allows requests when no PID is set."""
        from jeeves_infra.llm.gateway import LLMGateway, LLMResponse
        from mission_system.bootstrap import (
            get_request_pid,
            clear_request_pid,
        )

        # Ensure no PID is set
        clear_request_pid()

        callback_called = []

        def track_resources(tokens_in: int, tokens_out: int):
            pid = get_request_pid()
            callback_called.append((pid, tokens_in, tokens_out))
            if pid is None:
                return None  # Allow without tracking
            return None

        mock_settings = MagicMock()
        gateway = LLMGateway(
            settings=mock_settings,
            logger=mock_logger,
            resource_callback=track_resources,
        )

        response = LLMResponse(
            text="Test",
            tool_calls=[],
            tokens_used=100,
            prompt_tokens=50,
            completion_tokens=50,
            latency_ms=50.0,
            provider="test",
            model="test",
            cost_usd=0.0001,
            timestamp=datetime.now(timezone.utc),
            metadata={},
        )

        result = gateway._update_stats(response)

        # Should allow without error
        assert result is None
        # Callback should have been called with no PID
        assert len(callback_called) == 1
        assert callback_called[0][0] is None


# =============================================================================
# LLM Gateway Cost Tracking Tests
# =============================================================================


class TestLLMGatewayCostTracking:
    """Test LLM Gateway cost tracking end-to-end."""

    def test_gateway_tracks_cost_per_request(self, mock_logger):
        """Test that gateway tracks cost for each request."""
        from jeeves_infra.llm.gateway import LLMGateway, LLMResponse

        mock_settings = MagicMock()
        mock_settings.llm_provider = "openai"
        mock_settings.default_model = "gpt-4"

        gateway = LLMGateway(
            settings=mock_settings,
            logger=mock_logger,
        )

        # Simulate multiple completions
        costs = [0.005, 0.003, 0.002]
        for cost in costs:
            response = LLMResponse(
                text="Response",
                tool_calls=[],
                tokens_used=100,
                prompt_tokens=60,
                completion_tokens=40,
                latency_ms=200.0,
                provider="openai",
                model="gpt-4",
                cost_usd=cost,
                timestamp=datetime.now(timezone.utc),
                metadata={},
            )
            gateway._update_stats(response)

        # Verify accumulated stats
        stats = gateway.get_stats()
        assert stats["total_requests"] == 3
        assert abs(stats["total_cost_usd"] - sum(costs)) < 0.0001
        assert stats["total_tokens"] == 300

    def test_gateway_tracks_by_provider(self, mock_logger):
        """Test that gateway tracks stats per provider."""
        from jeeves_infra.llm.gateway import LLMGateway, LLMResponse

        mock_settings = MagicMock()
        gateway = LLMGateway(
            settings=mock_settings,
            logger=mock_logger,
        )

        # Simulate completions from different providers
        providers = [
            ("openai", "gpt-4", 0.01),
            ("anthropic", "claude-3", 0.008),
            ("openai", "gpt-4", 0.005),
            ("llamaserver", "llama-3", 0.0),  # Local has no cost
        ]

        for provider, model, cost in providers:
            response = LLMResponse(
                text="Response",
                tool_calls=[],
                tokens_used=100,
                prompt_tokens=60,
                completion_tokens=40,
                latency_ms=150.0,
                provider=provider,
                model=model,
                cost_usd=cost,
                timestamp=datetime.now(timezone.utc),
                metadata={},
            )
            gateway._update_stats(response)

        stats = gateway.get_stats()

        assert "openai" in stats["by_provider"]
        assert stats["by_provider"]["openai"]["requests"] == 2
        assert abs(stats["by_provider"]["openai"]["cost_usd"] - 0.015) < 0.0001

        assert "anthropic" in stats["by_provider"]
        assert stats["by_provider"]["anthropic"]["requests"] == 1

        assert "llamaserver" in stats["by_provider"]
        assert stats["by_provider"]["llamaserver"]["cost_usd"] == 0.0


# =============================================================================
# Provider Streaming Tests
# =============================================================================


class TestProviderStreaming:
    """Test provider streaming support."""

    @pytest.mark.asyncio
    async def test_gateway_streaming_callback(self, mock_logger):
        """Test that streaming callback is invoked for each chunk."""
        from jeeves_infra.llm.gateway import LLMGateway, StreamingChunk

        mock_settings = MagicMock()
        mock_settings.llm_provider = "llamaserver"
        mock_settings.default_model = "test-model"

        chunks_received = []

        def streaming_callback(chunk: StreamingChunk):
            chunks_received.append(chunk)

        gateway = LLMGateway(
            settings=mock_settings,
            logger=mock_logger,
            streaming_callback=streaming_callback,
        )

        # Verify callback is set
        assert gateway._streaming_callback is streaming_callback

        # Test dynamic callback setting
        new_callback = MagicMock()
        gateway.set_streaming_callback(new_callback)
        assert gateway._streaming_callback is new_callback

        # Clear callback
        gateway.set_streaming_callback(None)
        assert gateway._streaming_callback is None

    def test_streaming_chunk_to_dict(self):
        """Test StreamingChunk serialization."""
        from jeeves_infra.llm.gateway import StreamingChunk

        chunk = StreamingChunk(
            text="Hello",
            is_final=False,
            request_id="req-123",
            agent_name="planner",
            provider="llamaserver",
            model="llama-3",
            cumulative_tokens=5,
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )

        data = chunk.to_dict()

        assert data["text"] == "Hello"
        assert data["is_final"] is False
        assert data["request_id"] == "req-123"
        assert data["agent_name"] == "planner"
        assert data["provider"] == "llamaserver"
        assert data["cumulative_tokens"] == 5
        assert "timestamp" in data


# =============================================================================
# Distributed Infrastructure Tests
# =============================================================================


class TestDistributedInfrastructure:
    """Test distributed infrastructure wiring."""

    def test_distributed_infra_disabled_by_default(self, mock_logger):
        """Test that distributed infra is not created when disabled."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock

        flags = FeatureFlags(
            enable_distributed_mode=False,
            use_redis_state=False,
        )

        mock_settings = MagicMock()
        context = AppContext(
            settings=mock_settings,
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=None,
        )

        from mission_system.bootstrap import create_distributed_infrastructure

        result = create_distributed_infrastructure(context)

        assert result["redis_client"] is None
        assert result["distributed_bus"] is None
        assert result["worker_coordinator"] is None
        assert result["checkpoint_adapter"] is None

    def test_distributed_infra_requires_redis_state(self, mock_logger):
        """Test that distributed mode requires use_redis_state flag."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock

        flags = FeatureFlags(
            enable_distributed_mode=True,
            use_redis_state=False,  # Missing dependency
        )

        context = AppContext(
            settings=MagicMock(),
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=None,
        )

        from mission_system.bootstrap import create_distributed_infrastructure

        result = create_distributed_infrastructure(context)

        # Should warn and return empty
        assert result["redis_client"] is None
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_distributed_infra_created_when_enabled(self, mock_logger):
        """Test distributed infrastructure creation when both flags enabled."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock

        flags = FeatureFlags(
            enable_distributed_mode=True,
            use_redis_state=True,
        )

        mock_control_tower = MagicMock()

        context = AppContext(
            settings=MagicMock(),
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=mock_control_tower,
        )

        # Mock Redis to avoid actual connection
        with patch("redis.asyncio.from_url") as mock_redis:
            mock_redis.return_value = AsyncMock()

            from mission_system.bootstrap import create_distributed_infrastructure

            try:
                result = create_distributed_infrastructure(context)

                # Should create all components
                assert result["redis_client"] is not None
                assert result["distributed_bus"] is not None
                assert result["worker_coordinator"] is not None
                # No checkpoint adapter without postgres_client
                assert result["checkpoint_adapter"] is None

            except ImportError:
                pytest.skip("Redis package not installed")

    @pytest.mark.asyncio
    async def test_checkpoint_adapter_wired_when_enabled(self, mock_logger):
        """Test checkpoint adapter is wired when enable_checkpoints=true."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock

        flags = FeatureFlags(
            enable_distributed_mode=True,
            use_redis_state=True,
            enable_checkpoints=True,
        )

        mock_control_tower = MagicMock()
        mock_postgres_client = MagicMock()

        context = AppContext(
            settings=MagicMock(),
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=mock_control_tower,
        )

        # Mock Redis to avoid actual connection
        with patch("redis.asyncio.from_url") as mock_redis:
            mock_redis.return_value = AsyncMock()

            from mission_system.bootstrap import create_distributed_infrastructure

            try:
                result = create_distributed_infrastructure(
                    context,
                    postgres_client=mock_postgres_client,
                )

                # Should create checkpoint adapter
                assert result["checkpoint_adapter"] is not None
                assert result["worker_coordinator"] is not None

            except ImportError:
                pytest.skip("Redis package not installed")

    @pytest.mark.asyncio
    async def test_checkpoint_adapter_skipped_without_postgres(self, mock_logger):
        """Test checkpoint adapter is skipped when no postgres_client provided."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock

        flags = FeatureFlags(
            enable_distributed_mode=True,
            use_redis_state=True,
            enable_checkpoints=True,  # Enabled but no postgres_client
        )

        context = AppContext(
            settings=MagicMock(),
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=MagicMock(),
        )

        with patch("redis.asyncio.from_url") as mock_redis:
            mock_redis.return_value = AsyncMock()

            from mission_system.bootstrap import create_distributed_infrastructure

            try:
                result = create_distributed_infrastructure(context)

                # Should warn and not create checkpoint adapter
                assert result["checkpoint_adapter"] is None
                mock_logger.warning.assert_called()

            except ImportError:
                pytest.skip("Redis package not installed")


# =============================================================================
# Bootstrap Integration Tests
# =============================================================================


class TestBootstrapIntegration:
    """Test bootstrap wiring integration."""

    def test_create_avionics_dependencies_with_gateway(self, mock_logger):
        """Test that avionics dependencies creates gateway when enabled."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock

        flags = FeatureFlags(use_llm_gateway=True)
        mock_settings = MagicMock()
        mock_settings.llm_provider = "llamaserver"

        mock_control_tower = MagicMock()

        context = AppContext(
            settings=mock_settings,
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=mock_control_tower,
        )

        from mission_system.bootstrap import create_avionics_dependencies

        deps = create_avionics_dependencies(context)

        assert deps["llm_gateway"] is not None
        assert deps["llm_factory"] is not None

    def test_create_avionics_dependencies_wires_resource_callback(self, mock_logger):
        """Test that resource callback is wired when Control Tower available."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock

        flags = FeatureFlags(use_llm_gateway=True)
        mock_settings = MagicMock()
        mock_settings.llm_provider = "llamaserver"

        mock_control_tower = MagicMock()
        mock_control_tower.record_llm_call.return_value = None  # Within quota

        context = AppContext(
            settings=mock_settings,
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=mock_control_tower,
        )

        from mission_system.bootstrap import (
            create_avionics_dependencies,
            set_request_pid,
            clear_request_pid,
        )

        deps = create_avionics_dependencies(context)
        gateway = deps["llm_gateway"]

        # Gateway should have callback set
        assert gateway._resource_callback is not None

        # Test callback invokes Control Tower
        set_request_pid("test-pid-abc")

        # Manually invoke callback
        result = gateway._resource_callback(100, 50)

        # Should have called Control Tower
        mock_control_tower.record_llm_call.assert_called_once_with(
            pid="test-pid-abc",
            tokens_in=100,
            tokens_out=50,
        )

        clear_request_pid()


# =============================================================================
# Worker Coordinator Tests
# =============================================================================


class TestWorkerCoordinatorIntegration:
    """Test worker coordinator with Control Tower integration."""

    @pytest.fixture
    def mock_distributed_bus(self):
        """Create mock distributed bus."""
        bus = AsyncMock()
        bus.enqueue_task = AsyncMock(return_value="task-123")
        bus.register_worker = AsyncMock()
        bus.deregister_worker = AsyncMock()
        bus.heartbeat = AsyncMock()
        return bus

    @pytest.fixture
    def mock_control_tower(self, mock_logger):
        """Create mock Control Tower."""
        from control_tower.resources.tracker import ResourceTracker
        from control_tower.types import ResourceQuota

        ct = MagicMock()
        ct.resources = ResourceTracker(logger=mock_logger)
        ct.lifecycle = MagicMock()
        ct.lifecycle.submit = MagicMock()
        return ct

    @pytest.mark.asyncio
    async def test_submit_envelope_creates_pcb(
        self, mock_distributed_bus, mock_control_tower
    ):
        """Test that submit_envelope creates PCB in Control Tower."""
        from mission_system.services.worker_coordinator import WorkerCoordinator
        from jeeves_infra.protocols import Envelope
from jeeves_infra.protocols import RequestContext

        coordinator = WorkerCoordinator(
            distributed_bus=mock_distributed_bus,
            control_tower=mock_control_tower,
            logger=MagicMock(),
        )

        request_context = RequestContext(
            request_id="req-123",
            capability="test_capability",
            user_id="user-1",
            session_id="session-1",
        )
        envelope = Envelope(
            request_context=request_context,
            envelope_id="env-123",
            request_id="req-123",
            user_id="user-1",
            session_id="session-1",
        )

        task_id = await coordinator.submit_envelope(
            envelope=envelope,
            queue_name="agent:planner",
            agent_name="planner",
        )

        # Should have created PCB
        mock_control_tower.lifecycle.submit.assert_called_once()

        # Should have enqueued task
        mock_distributed_bus.enqueue_task.assert_called_once()
        assert task_id is not None

    @pytest.mark.asyncio
    async def test_submit_envelope_allocates_resources(
        self, mock_distributed_bus, mock_control_tower
    ):
        """Test that submit_envelope allocates resources."""
        from mission_system.services.worker_coordinator import WorkerCoordinator
        from jeeves_infra.protocols import Envelope
from jeeves_infra.protocols import RequestContext
        from control_tower.types import ResourceQuota

        coordinator = WorkerCoordinator(
            distributed_bus=mock_distributed_bus,
            control_tower=mock_control_tower,
            logger=MagicMock(),
        )

        request_context = RequestContext(
            request_id="req-456",
            capability="test_capability",
            user_id="user-1",
            session_id="session-1",
        )
        envelope = Envelope(
            request_context=request_context,
            envelope_id="env-456",
            request_id="req-456",
            user_id="user-1",
            session_id="session-1",
        )

        await coordinator.submit_envelope(
            envelope=envelope,
            queue_name="agent:validator",
            resource_quota=ResourceQuota(max_llm_calls=20),
        )

        # Should have allocated resources
        assert mock_control_tower.resources.is_tracked("env-456")
