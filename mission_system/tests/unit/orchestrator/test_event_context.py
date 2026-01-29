"""
Tests for the centralized EventContext.

Verifies:
- Event context creation
- Agent event emission via context
- Domain event emission via context
- Integration with EventEmitter
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mission_system.orchestrator.event_context import (
    EventContext,
    create_event_context,
)
from jeeves_infra.protocols import RequestContext


def _ctx(
    request_id: str = "req_456",
    session_id: str = "sess_123",
    user_id: str = "user_789",
) -> RequestContext:
    return RequestContext(
        request_id=request_id,
        capability="test_capability",
        session_id=session_id,
        user_id=user_id,
    )


class TestEventContextCreation:
    """Tests for EventContext creation."""

    def test_create_event_context_with_minimal_args(self):
        """Test creating context with only required args."""
        context = create_event_context(
            request_context=_ctx(),
        )

        assert context.request_context.session_id == "sess_123"
        assert context.request_context.request_id == "req_456"
        assert context.request_context.user_id == "user_789"
        assert context.agent_event_emitter is None
        assert context.domain_event_emitter is None
        # correlation_id defaults to request_id
        assert context.correlation_id == "req_456"

    def test_create_event_context_with_custom_correlation_id(self):
        """Test creating context with custom correlation ID."""
        context = create_event_context(
            request_context=_ctx(),
            correlation_id="corr_custom",
        )

        assert context.correlation_id == "corr_custom"

    def test_create_event_context_with_emitters(self):
        """Test creating context with emitters."""
        mock_agent_emitter = MagicMock()
        mock_domain_emitter = MagicMock()

        context = create_event_context(
            request_context=_ctx(),
            agent_event_emitter=mock_agent_emitter,
            domain_event_emitter=mock_domain_emitter,
        )

        assert context.agent_event_emitter == mock_agent_emitter
        assert context.domain_event_emitter == mock_domain_emitter


class TestEventContextAgentEvents:
    """Tests for agent lifecycle event emission."""

    @pytest.mark.asyncio
    async def test_emit_agent_started_with_emitter(self):
        """Test emitting agent started event when emitter is present."""
        mock_emitter = AsyncMock()
        ctx = _ctx()

        context = EventContext(
            request_context=ctx,
            agent_event_emitter=mock_emitter,
        )

        await context.emit_agent_started("planner", foo="bar")

        mock_emitter.emit_agent_started.assert_called_once_with(
            agent_name="planner",
            request_context=ctx,
            foo="bar",
        )

    @pytest.mark.asyncio
    async def test_emit_agent_started_without_emitter(self):
        """Test emitting agent started event when no emitter (no error)."""
        context = EventContext(
            request_context=_ctx(),
        )

        # Should not raise
        await context.emit_agent_started("planner")

    @pytest.mark.asyncio
    async def test_emit_agent_completed_with_emitter(self):
        """Test emitting agent completed event when emitter is present."""
        mock_emitter = AsyncMock()
        ctx = _ctx()

        context = EventContext(
            request_context=ctx,
            agent_event_emitter=mock_emitter,
        )

        await context.emit_agent_completed(
            "planner",
            status="success",
            step_count=3,
        )

        mock_emitter.emit_agent_completed.assert_called_once_with(
            agent_name="planner",
            request_context=ctx,
            status="success",
            error=None,
            step_count=3,
        )

    @pytest.mark.asyncio
    async def test_emit_agent_completed_with_error(self):
        """Test emitting agent completed event with error."""
        mock_emitter = AsyncMock()
        ctx = _ctx()

        context = EventContext(
            request_context=ctx,
            agent_event_emitter=mock_emitter,
        )

        await context.emit_agent_completed(
            "planner",
            status="error",
            error="Something went wrong",
        )

        mock_emitter.emit_agent_completed.assert_called_once_with(
            agent_name="planner",
            request_context=ctx,
            status="error",
            error="Something went wrong",
        )


class TestEventContextDomainEvents:
    """Tests for domain event emission."""

    @pytest.mark.asyncio
    async def test_emit_plan_created_with_domain_emitter(self):
        """Test emitting plan_created domain event."""
        mock_domain_emitter = AsyncMock()
        mock_domain_emitter.emit_plan_created.return_value = "event_123"

        context = EventContext(
            request_context=_ctx(),
            domain_event_emitter=mock_domain_emitter,
        )

        event_id = await context.emit_plan_created(
            plan_id="plan_abc",
            intent="understand_architecture",
            confidence=0.85,
            tools=["tree_structure", "read_file"],
            step_count=2,
            clarification_needed=False,
        )

        assert event_id == "event_123"
        mock_domain_emitter.emit_plan_created.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_plan_created_without_domain_emitter(self):
        """Test emitting plan_created when no domain emitter (returns None)."""
        context = EventContext(
            request_context=_ctx(),
        )

        event_id = await context.emit_plan_created(
            plan_id="plan_abc",
            intent="understand_architecture",
            confidence=0.85,
            tools=["tree_structure"],
            step_count=1,
        )

        assert event_id is None

    @pytest.mark.asyncio
    async def test_emit_critic_decision(self):
        """Test emitting critic_decision domain event."""
        mock_domain_emitter = AsyncMock()
        mock_domain_emitter.emit_critic_decision.return_value = "event_456"

        context = EventContext(
            request_context=_ctx(),
            domain_event_emitter=mock_domain_emitter,
        )

        event_id = await context.emit_critic_decision(
            action="approved",
            confidence=0.9,
            issue=None,
            feedback=None,
        )

        assert event_id == "event_456"
        mock_domain_emitter.emit_critic_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_tool_completed_with_both_emitters(self):
        """Test emit_tool_completed emits to both agent and domain emitters."""
        mock_agent_emitter = AsyncMock()
        mock_domain_emitter = AsyncMock()
        mock_domain_emitter.emit_tool_executed.return_value = "event_789"

        context = EventContext(
            request_context=_ctx(),
            agent_event_emitter=mock_agent_emitter,
            domain_event_emitter=mock_domain_emitter,
        )

        event_id = await context.emit_tool_completed(
            tool_name="read_file",
            status="success",
            execution_time_ms=150,
        )

        # Should emit to agent emitter
        mock_agent_emitter.emit_tool_completed.assert_called_once()

        # Should emit to domain emitter
        mock_domain_emitter.emit_tool_executed.assert_called_once()
        assert event_id == "event_789"


class TestEventContextFlowEvents:
    """Tests for flow lifecycle events."""

    @pytest.mark.asyncio
    async def test_emit_flow_started(self):
        """Test emitting flow started event."""
        mock_emitter = AsyncMock()

        context = EventContext(
            request_context=_ctx(),
            agent_event_emitter=mock_emitter,
        )

        await context.emit_flow_started()

        mock_emitter.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_flow_completed(self):
        """Test emitting flow completed event."""
        mock_emitter = AsyncMock()

        context = EventContext(
            request_context=_ctx(),
            agent_event_emitter=mock_emitter,
        )

        await context.emit_flow_completed(status="success")

        mock_emitter.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_stage_transition(self):
        """Test emitting stage transition event."""
        mock_emitter = AsyncMock()
        ctx = _ctx()

        context = EventContext(
            request_context=ctx,
            agent_event_emitter=mock_emitter,
        )

        await context.emit_stage_transition(
            from_stage=1,
            to_stage=2,
            satisfied_goals=["goal1"],
            remaining_goals=["goal2"],
        )

        mock_emitter.emit_stage_transition.assert_called_once_with(
            request_context=ctx,
            from_stage=1,
            to_stage=2,
            satisfied_goals=["goal1"],
            remaining_goals=["goal2"],
        )


class TestEventContextUtilities:
    """Tests for utility methods."""

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the event context."""
        mock_emitter = AsyncMock()

        context = EventContext(
            request_context=_ctx(),
            agent_event_emitter=mock_emitter,
        )

        await context.close()

        mock_emitter.close.assert_called_once()

    def test_get_event_nowait_with_emitter(self):
        """Test getting events from emitter."""
        mock_emitter = MagicMock()
        mock_event = MagicMock()
        mock_emitter.get_nowait.return_value = mock_event

        context = EventContext(
            request_context=_ctx(),
            agent_event_emitter=mock_emitter,
        )

        event = context.get_event_nowait()

        assert event == mock_event
        mock_emitter.get_nowait.assert_called_once()

    def test_get_event_nowait_without_emitter(self):
        """Test getting events when no emitter (returns None)."""
        context = EventContext(
            request_context=_ctx(),
        )

        event = context.get_event_nowait()

        assert event is None
