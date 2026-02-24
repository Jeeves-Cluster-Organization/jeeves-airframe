"""Unit tests for the orchestrator events module.

Tests:
- AgentEvent creation, validation, serialization (to_dict, to_json)
- AgentEventType enum coverage
- EventEmitter queue mechanics (emit, events iterator, close, get_nowait)
- EventContext delegation (agent started/completed, tool, flow, retry, reasoning)
- EventOrchestrator facade (lazy init, delegation, streaming, lifecycle)
- create_event_orchestrator factory
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jeeves_infra.orchestrator.agent_events import (
    AgentEventType,
    AgentEvent,
    EventEmitter,
    create_agent_event_emitter,
)
from jeeves_infra.orchestrator.event_context import (
    EventContext,
    create_event_context,
)
from jeeves_infra.orchestrator.events import (
    EventOrchestrator,
    create_event_orchestrator,
)
from jeeves_infra.protocols import RequestContext


# =============================================================================
# Helpers
# =============================================================================

def _make_request_context(
    request_id: str = "req-123",
    capability: str = "test_cap",
    session_id: str = "sess-456",
    user_id: str = "user-789",
) -> RequestContext:
    return RequestContext(
        request_id=request_id,
        capability=capability,
        session_id=session_id,
        user_id=user_id,
    )


def _make_mock_logger():
    logger = MagicMock()
    logger.bind = MagicMock(return_value=logger)
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


# =============================================================================
# AgentEventType
# =============================================================================


class TestAgentEventType:
    def test_all_event_types_have_string_values(self):
        for member in AgentEventType:
            assert isinstance(member.value, str)
            assert "." in member.value

    def test_agent_lifecycle_types(self):
        assert AgentEventType.AGENT_STARTED.value == "agent.started"
        assert AgentEventType.AGENT_COMPLETED.value == "agent.completed"
        assert AgentEventType.AGENT_DECISION.value == "agent.decision"

    def test_tool_types(self):
        assert AgentEventType.TOOL_STARTED.value == "tool.started"
        assert AgentEventType.TOOL_COMPLETED.value == "tool.completed"

    def test_orchestrator_types(self):
        assert AgentEventType.STAGE_TRANSITION.value == "orchestrator.stage_transition"
        assert AgentEventType.FLOW_STARTED.value == "orchestrator.started"
        assert AgentEventType.FLOW_COMPLETED.value == "orchestrator.completed"
        assert AgentEventType.FLOW_ERROR.value == "orchestrator.error"


# =============================================================================
# AgentEvent
# =============================================================================


class TestAgentEvent:
    def test_create_basic_event(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.AGENT_STARTED,
            agent_name="planner",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
        )
        assert event.event_type == AgentEventType.AGENT_STARTED
        assert event.agent_name == "planner"
        assert event.session_id == "sess-456"
        assert event.request_id == "req-123"
        assert event.payload == {}
        assert event.timestamp_ms > 0

    def test_create_event_with_payload(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.AGENT_COMPLETED,
            agent_name="critic",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
            payload={"status": "success", "step_count": 3},
        )
        assert event.payload["status"] == "success"
        assert event.payload["step_count"] == 3

    def test_validation_requires_request_context(self):
        with pytest.raises(ValueError, match="request_context is required"):
            AgentEvent(
                event_type=AgentEventType.AGENT_STARTED,
                agent_name="planner",
                request_context=None,
                session_id="sess-456",
                request_id="req-123",
            )

    def test_validation_request_id_mismatch(self):
        ctx = _make_request_context(request_id="req-123")
        with pytest.raises(ValueError, match="request_id does not match"):
            AgentEvent(
                event_type=AgentEventType.AGENT_STARTED,
                agent_name="planner",
                request_context=ctx,
                session_id="sess-456",
                request_id="req-WRONG",
            )

    def test_validation_session_id_mismatch(self):
        ctx = _make_request_context(session_id="sess-456")
        with pytest.raises(ValueError, match="session_id does not match"):
            AgentEvent(
                event_type=AgentEventType.AGENT_STARTED,
                agent_name="planner",
                request_context=ctx,
                session_id="sess-WRONG",
                request_id="req-123",
            )

    def test_to_dict_agent_event_qualifies_type(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.AGENT_STARTED,
            agent_name="planner",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
        )
        d = event.to_dict()
        # agent.started with agent_name="planner" -> "agent.planner.started"
        assert d["event_type"] == "agent.planner.started"
        assert d["agent_name"] == "planner"
        assert d["session_id"] == "sess-456"
        assert d["request_id"] == "req-123"
        assert "request_context" in d

    def test_to_dict_agent_completed_qualifies_type(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.AGENT_COMPLETED,
            agent_name="critic",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
        )
        d = event.to_dict()
        assert d["event_type"] == "agent.critic.completed"

    def test_to_dict_non_agent_event_keeps_base_type(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.FLOW_STARTED,
            agent_name="orchestrator",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
        )
        d = event.to_dict()
        # orchestrator.started has parts[0]="orchestrator", not "agent"
        assert d["event_type"] == "orchestrator.started"

    def test_to_dict_tool_event_keeps_base_type(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.TOOL_STARTED,
            agent_name="executor",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
            payload={"tool_name": "grep_search"},
        )
        d = event.to_dict()
        assert d["event_type"] == "tool.started"
        assert d["tool_name"] == "grep_search"

    def test_to_dict_payload_merged_into_dict(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.AGENT_DECISION,
            agent_name="critic",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
            payload={"action": "approved", "confidence": 0.95},
        )
        d = event.to_dict()
        assert d["action"] == "approved"
        assert d["confidence"] == 0.95

    def test_to_json_is_valid_json(self):
        ctx = _make_request_context()
        event = AgentEvent(
            event_type=AgentEventType.AGENT_STARTED,
            agent_name="planner",
            request_context=ctx,
            session_id="sess-456",
            request_id="req-123",
        )
        j = event.to_json()
        parsed = json.loads(j)
        assert parsed["event_type"] == "agent.planner.started"
        assert parsed["agent_name"] == "planner"


# =============================================================================
# EventEmitter
# =============================================================================


class TestEventEmitter:
    def test_factory_creates_emitter(self):
        emitter = create_agent_event_emitter()
        assert isinstance(emitter, EventEmitter)

    @pytest.mark.asyncio
    async def test_emit_and_consume_event(self):
        emitter = EventEmitter()
        ctx = _make_request_context()

        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_agent_started("planner", ctx)

        event = emitter.get_nowait()
        assert event is not None
        assert event.event_type == AgentEventType.AGENT_STARTED
        assert event.agent_name == "planner"

    @pytest.mark.asyncio
    async def test_emit_agent_completed(self):
        emitter = EventEmitter()
        ctx = _make_request_context()

        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_agent_completed("critic", ctx, status="success")

        event = emitter.get_nowait()
        assert event is not None
        assert event.event_type == AgentEventType.AGENT_COMPLETED
        assert event.agent_name == "critic"
        assert event.payload["status"] == "success"

    @pytest.mark.asyncio
    async def test_emit_agent_decision(self):
        emitter = EventEmitter()
        ctx = _make_request_context()

        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_agent_decision(
                "critic", ctx, action="loop_back", confidence=0.8
            )

        event = emitter.get_nowait()
        assert event is not None
        assert event.event_type == AgentEventType.AGENT_DECISION
        assert event.payload["action"] == "loop_back"
        assert event.payload["confidence"] == 0.8

    @pytest.mark.asyncio
    async def test_emit_tool_started(self):
        emitter = EventEmitter()
        ctx = _make_request_context()

        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_tool_started(
                "grep_search", ctx, agent_name="executor"
            )

        event = emitter.get_nowait()
        assert event is not None
        assert event.event_type == AgentEventType.TOOL_STARTED
        assert event.payload["tool_name"] == "grep_search"

    @pytest.mark.asyncio
    async def test_emit_tool_completed(self):
        emitter = EventEmitter()
        ctx = _make_request_context()

        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_tool_completed(
                "grep_search", ctx, agent_name="executor", status="error"
            )

        event = emitter.get_nowait()
        assert event is not None
        assert event.event_type == AgentEventType.TOOL_COMPLETED
        assert event.payload["status"] == "error"

    @pytest.mark.asyncio
    async def test_emit_stage_transition(self):
        emitter = EventEmitter()
        ctx = _make_request_context()

        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_stage_transition(
                ctx, from_stage=1, to_stage=2,
                satisfied_goals=["goal_a"],
                remaining_goals=["goal_b", "goal_c"],
            )

        event = emitter.get_nowait()
        assert event is not None
        assert event.event_type == AgentEventType.STAGE_TRANSITION
        assert event.payload["from_stage"] == 1
        assert event.payload["to_stage"] == 2
        assert event.payload["satisfied_goals"] == ["goal_a"]

    @pytest.mark.asyncio
    async def test_close_signals_end_of_stream(self):
        emitter = EventEmitter()
        await emitter.close()
        assert emitter._closed is True

    @pytest.mark.asyncio
    async def test_emit_after_close_is_ignored(self):
        emitter = EventEmitter()
        ctx = _make_request_context()
        await emitter.close()

        # Should not raise, just silently ignore
        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_agent_started("planner", ctx)

        # The None sentinel is in the queue from close(), but not the new event
        sentinel = emitter.get_nowait()
        assert sentinel is None

    @pytest.mark.asyncio
    async def test_events_iterator_yields_all_then_stops(self):
        emitter = EventEmitter()
        ctx = _make_request_context()

        with patch("jeeves_infra.logging.get_current_logger", return_value=_make_mock_logger()):
            await emitter.emit_agent_started("planner", ctx)
            await emitter.emit_agent_completed("planner", ctx)
            await emitter.close()

        collected = []
        async for event in emitter.events():
            collected.append(event)

        assert len(collected) == 2
        assert collected[0].event_type == AgentEventType.AGENT_STARTED
        assert collected[1].event_type == AgentEventType.AGENT_COMPLETED

    def test_get_nowait_empty_returns_none(self):
        emitter = EventEmitter()
        result = emitter.get_nowait()
        assert result is None

    def test_custom_maxsize(self):
        emitter = EventEmitter(maxsize=5)
        assert emitter._queue.maxsize == 5


# =============================================================================
# EventContext
# =============================================================================


class TestEventContext:
    def _make_context(
        self,
        agent_emitter=None,
        domain_emitter=None,
        correlation_id=None,
    ) -> EventContext:
        ctx = _make_request_context()
        logger = _make_mock_logger()
        return EventContext(
            request_context=ctx,
            agent_event_emitter=agent_emitter,
            domain_event_emitter=domain_emitter,
            correlation_id=correlation_id,
            _logger=logger,
        )

    def test_factory_function(self):
        ctx = _make_request_context()
        event_ctx = create_event_context(request_context=ctx)
        assert event_ctx.request_context is ctx
        assert event_ctx.agent_event_emitter is None
        assert event_ctx.domain_event_emitter is None

    def test_correlation_id_defaults_to_request_id(self):
        event_ctx = self._make_context()
        assert event_ctx.correlation_id == "req-123"

    def test_custom_correlation_id(self):
        event_ctx = self._make_context(correlation_id="corr-custom")
        assert event_ctx.correlation_id == "corr-custom"

    @pytest.mark.asyncio
    async def test_emit_agent_started_delegates_to_emitter(self):
        emitter = MagicMock()
        emitter.emit_agent_started = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        await event_ctx.emit_agent_started("planner", extra_key="extra_val")

        emitter.emit_agent_started.assert_called_once_with(
            agent_name="planner",
            request_context=event_ctx.request_context,
            extra_key="extra_val",
        )

    @pytest.mark.asyncio
    async def test_emit_agent_started_no_emitter_no_error(self):
        event_ctx = self._make_context(agent_emitter=None)
        # Should not raise
        await event_ctx.emit_agent_started("planner")

    @pytest.mark.asyncio
    async def test_emit_agent_completed_delegates_to_emitter(self):
        emitter = MagicMock()
        emitter.emit_agent_completed = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        await event_ctx.emit_agent_completed("critic", status="error", error="boom")

        emitter.emit_agent_completed.assert_called_once_with(
            agent_name="critic",
            request_context=event_ctx.request_context,
            status="error",
            error="boom",
        )

    @pytest.mark.asyncio
    async def test_emit_tool_started_creates_params_preview(self):
        emitter = MagicMock()
        emitter.emit_tool_started = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        params = {"query": "test search", "limit": 10}
        await event_ctx.emit_tool_started(
            tool_name="grep_search",
            agent_name="executor",
            params=params,
            step_number=1,
            total_steps=3,
        )

        emitter.emit_tool_started.assert_called_once()
        call_kwargs = emitter.emit_tool_started.call_args[1]
        assert call_kwargs["tool_name"] == "grep_search"
        assert call_kwargs["agent_name"] == "executor"
        assert call_kwargs["params_preview"]["query"] == "test search"
        assert call_kwargs["params_preview"]["limit"] == "10"

    @pytest.mark.asyncio
    async def test_emit_tool_completed_delegates_to_both_emitters(self):
        agent_emitter = MagicMock()
        agent_emitter.emit_tool_completed = AsyncMock()
        domain_emitter = MagicMock()
        domain_emitter.emit_tool_executed = AsyncMock(return_value="evt-001")

        event_ctx = self._make_context(
            agent_emitter=agent_emitter,
            domain_emitter=domain_emitter,
        )

        result = await event_ctx.emit_tool_completed(
            tool_name="read_file",
            agent_name="executor",
            status="success",
            execution_time_ms=150,
        )

        agent_emitter.emit_tool_completed.assert_called_once()
        domain_emitter.emit_tool_executed.assert_called_once()
        assert result == "evt-001"

    @pytest.mark.asyncio
    async def test_emit_tool_completed_error_logs_warning(self):
        event_ctx = self._make_context()
        await event_ctx.emit_tool_completed(
            tool_name="broken_tool",
            agent_name="executor",
            status="error",
            error="Something went wrong",
            error_type="tool_error",
        )
        event_ctx._logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_retry_attempt_with_domain_emitter(self):
        domain_emitter = MagicMock()
        domain_emitter.emit_retry_attempt = AsyncMock(return_value="evt-002")

        event_ctx = self._make_context(domain_emitter=domain_emitter)
        result = await event_ctx.emit_retry_attempt(
            retry_type="validator",
            attempt_number=1,
            reason="Schema mismatch",
            feedback="Fix the output format",
        )

        domain_emitter.emit_retry_attempt.assert_called_once()
        assert result == "evt-002"

    @pytest.mark.asyncio
    async def test_emit_retry_attempt_no_domain_emitter(self):
        event_ctx = self._make_context()
        result = await event_ctx.emit_retry_attempt(
            retry_type="planner",
            attempt_number=2,
            reason="Bad plan",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_emit_stage_transition_delegates(self):
        emitter = MagicMock()
        emitter.emit_stage_transition = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        await event_ctx.emit_stage_transition(
            from_stage=1,
            to_stage=2,
            satisfied_goals=["analyze"],
            remaining_goals=["synthesize"],
        )

        emitter.emit_stage_transition.assert_called_once_with(
            request_context=event_ctx.request_context,
            from_stage=1,
            to_stage=2,
            satisfied_goals=["analyze"],
            remaining_goals=["synthesize"],
        )

    @pytest.mark.asyncio
    async def test_emit_flow_started(self):
        emitter = MagicMock()
        emitter.emit = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        await event_ctx.emit_flow_started()

        emitter.emit.assert_called_once()
        emitted_event = emitter.emit.call_args[0][0]
        assert emitted_event.event_type == AgentEventType.FLOW_STARTED
        assert emitted_event.agent_name == "orchestrator"

    @pytest.mark.asyncio
    async def test_emit_flow_completed(self):
        emitter = MagicMock()
        emitter.emit = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        await event_ctx.emit_flow_completed(status="success")

        emitter.emit.assert_called_once()
        emitted_event = emitter.emit.call_args[0][0]
        assert emitted_event.event_type == AgentEventType.FLOW_COMPLETED
        assert emitted_event.payload["status"] == "success"

    @pytest.mark.asyncio
    async def test_emit_flow_error(self):
        emitter = MagicMock()
        emitter.emit = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        await event_ctx.emit_flow_error(error="Pipeline crashed")

        emitter.emit.assert_called_once()
        emitted_event = emitter.emit.call_args[0][0]
        assert emitted_event.event_type == AgentEventType.FLOW_ERROR
        assert emitted_event.payload["error"] == "Pipeline crashed"

    @pytest.mark.asyncio
    async def test_emit_flow_started_no_emitter(self):
        event_ctx = self._make_context(agent_emitter=None)
        # Should not raise
        await event_ctx.emit_flow_started()

    @pytest.mark.asyncio
    async def test_close_closes_emitter(self):
        emitter = MagicMock()
        emitter.close = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        await event_ctx.close()

        emitter.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_no_emitter(self):
        event_ctx = self._make_context(agent_emitter=None)
        # Should not raise
        await event_ctx.close()

    def test_get_event_nowait_delegates(self):
        emitter = MagicMock()
        emitter.get_nowait = MagicMock(return_value="fake_event")
        event_ctx = self._make_context(agent_emitter=emitter)

        result = event_ctx.get_event_nowait()
        assert result == "fake_event"

    def test_get_event_nowait_no_emitter(self):
        event_ctx = self._make_context(agent_emitter=None)
        result = event_ctx.get_event_nowait()
        assert result is None


class TestEventContextParamsPreview:
    """Test _create_params_preview truncation logic."""

    def _make_context(self) -> EventContext:
        ctx = _make_request_context()
        logger = _make_mock_logger()
        return EventContext(
            request_context=ctx,
            _logger=logger,
        )

    def test_string_value_truncation(self):
        event_ctx = self._make_context()
        params = {"text": "A" * 200}
        preview = event_ctx._create_params_preview(params, max_value_length=100)
        assert len(preview["text"]) == 103  # 100 + "..."
        assert preview["text"].endswith("...")

    def test_short_string_not_truncated(self):
        event_ctx = self._make_context()
        params = {"text": "short"}
        preview = event_ctx._create_params_preview(params, max_value_length=100)
        assert preview["text"] == "short"

    def test_none_value(self):
        event_ctx = self._make_context()
        params = {"key": None}
        preview = event_ctx._create_params_preview(params)
        assert preview["key"] == "null"

    def test_numeric_values(self):
        event_ctx = self._make_context()
        params = {"count": 42, "rate": 3.14, "flag": True}
        preview = event_ctx._create_params_preview(params)
        assert preview["count"] == "42"
        assert preview["rate"] == "3.14"
        assert preview["flag"] == "True"

    def test_complex_value_truncation(self):
        event_ctx = self._make_context()
        params = {"data": list(range(200))}
        preview = event_ctx._create_params_preview(params, max_value_length=50)
        assert len(preview["data"]) <= 53  # 50 + "..."

    def test_unknown_type(self):
        event_ctx = self._make_context()

        class Custom:
            pass

        params = {"obj": Custom()}
        preview = event_ctx._create_params_preview(params)
        assert preview["obj"] == "<Custom>"


class TestEventContextReasoning:
    """Test emit_agent_reasoning with feature flag gating."""

    def _make_context(self, agent_emitter=None) -> EventContext:
        ctx = _make_request_context()
        logger = _make_mock_logger()
        return EventContext(
            request_context=ctx,
            agent_event_emitter=agent_emitter,
            _logger=logger,
        )

    @pytest.mark.asyncio
    async def test_reasoning_emitted_when_flag_enabled(self):
        emitter = MagicMock()
        emitter.emit = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        mock_flags = MagicMock()
        mock_flags.emit_agent_reasoning = True

        with patch(
            "jeeves_infra.feature_flags.get_feature_flags",
            return_value=mock_flags,
        ):
            await event_ctx.emit_agent_reasoning(
                agent_name="planner",
                reasoning_type="planning",
                reasoning_text="I should search for the file first.",
                confidence=0.9,
            )

        emitter.emit.assert_called_once()
        emitted = emitter.emit.call_args[0][0]
        assert emitted.payload["type"] == "reasoning"
        assert emitted.payload["reasoning_type"] == "planning"
        assert emitted.payload["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_reasoning_skipped_when_flag_disabled(self):
        emitter = MagicMock()
        emitter.emit = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        mock_flags = MagicMock()
        mock_flags.emit_agent_reasoning = False

        with patch(
            "jeeves_infra.feature_flags.get_feature_flags",
            return_value=mock_flags,
        ):
            await event_ctx.emit_agent_reasoning(
                agent_name="planner",
                reasoning_type="planning",
                reasoning_text="I should search for the file first.",
            )

        emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_reasoning_skipped_when_import_fails(self):
        emitter = MagicMock()
        emitter.emit = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        with patch(
            "jeeves_infra.feature_flags.get_feature_flags",
            side_effect=ImportError("no feature_flags"),
        ):
            await event_ctx.emit_agent_reasoning(
                agent_name="planner",
                reasoning_type="planning",
                reasoning_text="test",
            )

        emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_reasoning_text_truncated(self):
        emitter = MagicMock()
        emitter.emit = AsyncMock()
        event_ctx = self._make_context(agent_emitter=emitter)

        mock_flags = MagicMock()
        mock_flags.emit_agent_reasoning = True

        long_text = "A" * 1000

        with patch(
            "jeeves_infra.feature_flags.get_feature_flags",
            return_value=mock_flags,
        ):
            await event_ctx.emit_agent_reasoning(
                agent_name="planner",
                reasoning_type="planning",
                reasoning_text=long_text,
            )

        emitted = emitter.emit.call_args[0][0]
        reasoning = emitted.payload["reasoning"]
        assert len(reasoning) == 503  # 500 + "..."
        assert reasoning.endswith("...")


# =============================================================================
# EventOrchestrator (Unified Facade)
# =============================================================================


class TestEventOrchestrator:
    def _make_orchestrator(self, **kwargs) -> EventOrchestrator:
        defaults = dict(
            request_context=_make_request_context(),
            enable_streaming=False,
            enable_persistence=False,
        )
        defaults.update(kwargs)

        logger = _make_mock_logger()
        with patch("jeeves_infra.orchestrator.events.get_logger", return_value=logger):
            return EventOrchestrator(**defaults)

    def test_factory_function(self):
        ctx = _make_request_context()
        with patch("jeeves_infra.orchestrator.events.get_logger", return_value=_make_mock_logger()):
            orch = create_event_orchestrator(
                request_context=ctx,
                enable_streaming=False,
                enable_persistence=False,
            )
        assert isinstance(orch, EventOrchestrator)
        assert orch.request_context is ctx

    def test_correlation_id_defaults_to_request_id(self):
        orch = self._make_orchestrator()
        assert orch.correlation_id == "req-123"

    def test_custom_correlation_id(self):
        orch = self._make_orchestrator(correlation_id="corr-custom")
        assert orch.correlation_id == "corr-custom"

    def test_lazy_initialization(self):
        orch = self._make_orchestrator()
        assert orch._initialized is False
        assert orch._agent_emitter is None
        assert orch._context is None

    def test_ensure_initialized_creates_context(self):
        orch = self._make_orchestrator(enable_streaming=False, enable_persistence=False)
        orch._ensure_initialized()
        assert orch._initialized is True
        assert orch._context is not None
        assert orch._agent_emitter is None  # streaming disabled

    def test_ensure_initialized_creates_emitter_when_streaming(self):
        orch = self._make_orchestrator(enable_streaming=True)
        orch._ensure_initialized()
        assert orch._agent_emitter is not None
        assert isinstance(orch._agent_emitter, EventEmitter)

    def test_ensure_initialized_idempotent(self):
        orch = self._make_orchestrator()
        orch._ensure_initialized()
        first_context = orch._context
        orch._ensure_initialized()
        assert orch._context is first_context

    @pytest.mark.asyncio
    async def test_emit_agent_started_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_agent_started = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_agent_started("planner", key="val")

        mock_context.emit_agent_started.assert_called_once_with(
            "planner", key="val"
        )

    @pytest.mark.asyncio
    async def test_emit_agent_completed_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_agent_completed = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_agent_completed("critic", status="error", error="boom")

        mock_context.emit_agent_completed.assert_called_once_with(
            "critic", status="error", error="boom"
        )

    @pytest.mark.asyncio
    async def test_emit_tool_started_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_tool_started = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_tool_started(
            tool_name="read_file",
            agent_name="executor",
            params={"path": "/test"},
            step_number=1,
            total_steps=3,
        )

        mock_context.emit_tool_started.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_tool_completed_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_tool_completed = AsyncMock(return_value="evt-001")
        orch._context = mock_context
        orch._initialized = True

        result = await orch.emit_tool_completed(
            tool_name="read_file",
            agent_name="executor",
            status="success",
            execution_time_ms=100,
        )

        assert result == "evt-001"

    @pytest.mark.asyncio
    async def test_emit_flow_started_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_flow_started = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_flow_started()
        mock_context.emit_flow_started.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_flow_completed_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_flow_completed = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_flow_completed(status="success")
        mock_context.emit_flow_completed.assert_called_once_with(status="success")

    @pytest.mark.asyncio
    async def test_emit_flow_error_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_flow_error = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_flow_error(error="Pipeline failed")
        mock_context.emit_flow_error.assert_called_once_with(error="Pipeline failed")

    @pytest.mark.asyncio
    async def test_emit_stage_transition_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_stage_transition = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_stage_transition(
            from_stage=1,
            to_stage=2,
            satisfied_goals=["a"],
            remaining_goals=["b"],
        )

        mock_context.emit_stage_transition.assert_called_once_with(
            from_stage=1,
            to_stage=2,
            satisfied_goals=["a"],
            remaining_goals=["b"],
        )

    @pytest.mark.asyncio
    async def test_emit_retry_attempt_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_retry_attempt = AsyncMock(return_value="evt-002")
        orch._context = mock_context
        orch._initialized = True

        result = await orch.emit_retry_attempt(
            retry_type="validator",
            attempt_number=1,
            reason="bad output",
            feedback="fix format",
        )

        assert result == "evt-002"

    @pytest.mark.asyncio
    async def test_emit_agent_reasoning_delegates(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.emit_agent_reasoning = AsyncMock()
        orch._context = mock_context
        orch._initialized = True

        await orch.emit_agent_reasoning(
            agent_name="planner",
            reasoning_type="planning",
            reasoning_text="Thinking...",
            confidence=0.85,
            metadata={"step": 1},
        )

        mock_context.emit_agent_reasoning.assert_called_once_with(
            agent_name="planner",
            reasoning_type="planning",
            reasoning_text="Thinking...",
            confidence=0.85,
            metadata={"step": 1},
        )

    @pytest.mark.asyncio
    async def test_close_delegates_to_context(self):
        orch = self._make_orchestrator()
        mock_context = MagicMock()
        mock_context.close = AsyncMock()
        orch._context = mock_context

        await orch.close()
        mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_context(self):
        orch = self._make_orchestrator()
        # Should not raise even if context is None
        await orch.close()

    def test_get_event_nowait_no_emitter(self):
        orch = self._make_orchestrator(enable_streaming=False)
        orch._ensure_initialized()
        result = orch.get_event_nowait()
        assert result is None

    def test_context_property_triggers_init(self):
        orch = self._make_orchestrator()
        ctx = orch.context
        assert orch._initialized is True
        assert ctx is not None


class TestEventOrchestratorStreaming:
    """Test the streaming (async iterator) path end-to-end."""

    @pytest.mark.asyncio
    async def test_events_iterator_with_real_emitter(self):
        ctx = _make_request_context()
        logger = _make_mock_logger()

        with patch("jeeves_infra.orchestrator.events.get_logger", return_value=logger):
            orch = EventOrchestrator(
                request_context=ctx,
                enable_streaming=True,
                enable_persistence=False,
            )

        orch._ensure_initialized()
        emitter = orch._agent_emitter

        # Emit events then close
        with patch("jeeves_infra.logging.get_current_logger", return_value=logger):
            await emitter.emit_agent_started("planner", ctx)
            await emitter.emit_agent_completed("planner", ctx, status="success")
            await emitter.close()

        collected = []
        async for event in orch.events():
            collected.append(event)

        assert len(collected) == 2
        assert collected[0].agent_name == "planner"
        assert collected[0].event_type == AgentEventType.AGENT_STARTED
        assert collected[1].event_type == AgentEventType.AGENT_COMPLETED

    @pytest.mark.asyncio
    async def test_events_iterator_no_emitter_yields_nothing(self):
        ctx = _make_request_context()
        logger = _make_mock_logger()

        with patch("jeeves_infra.orchestrator.events.get_logger", return_value=logger):
            orch = EventOrchestrator(
                request_context=ctx,
                enable_streaming=False,
                enable_persistence=False,
            )

        orch._ensure_initialized()

        collected = []
        async for event in orch.events():
            collected.append(event)

        assert len(collected) == 0


class TestEventOrchestratorPersistence:
    """Test domain persistence initialization path."""

    def test_persistence_creates_domain_emitter_via_registry(self):
        ctx = _make_request_context()
        logger = _make_mock_logger()

        mock_factory = MagicMock(return_value="mock_domain_emitter")
        mock_registry = MagicMock()
        mock_registry.get_memory_service_factory = MagicMock(return_value=mock_factory)

        with patch("jeeves_infra.orchestrator.events.get_logger", return_value=logger):
            orch = EventOrchestrator(
                request_context=ctx,
                persistence="mock_db",
                enable_streaming=False,
                enable_persistence=True,
            )

        with patch(
            "jeeves_infra.protocols.get_capability_resource_registry",
            return_value=mock_registry,
        ):
            orch._ensure_initialized()

        mock_registry.get_memory_service_factory.assert_called_once_with("event_emitter")
        mock_factory.assert_called_once_with("mock_db")
        assert orch._domain_emitter == "mock_domain_emitter"

    def test_persistence_no_factory_in_registry(self):
        ctx = _make_request_context()
        logger = _make_mock_logger()

        mock_registry = MagicMock()
        mock_registry.get_memory_service_factory = MagicMock(return_value=None)

        with patch("jeeves_infra.orchestrator.events.get_logger", return_value=logger):
            orch = EventOrchestrator(
                request_context=ctx,
                persistence="mock_db",
                enable_streaming=False,
                enable_persistence=True,
            )

        with patch(
            "jeeves_infra.protocols.get_capability_resource_registry",
            return_value=mock_registry,
        ):
            orch._ensure_initialized()

        assert orch._domain_emitter is None

    def test_persistence_disabled_skips_domain_emitter(self):
        ctx = _make_request_context()
        logger = _make_mock_logger()

        with patch("jeeves_infra.orchestrator.events.get_logger", return_value=logger):
            orch = EventOrchestrator(
                request_context=ctx,
                persistence="mock_db",
                enable_streaming=False,
                enable_persistence=False,
            )

        orch._ensure_initialized()
        assert orch._domain_emitter is None
