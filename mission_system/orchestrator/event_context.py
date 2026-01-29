"""
Centralized agent event context for unified event emission.

Provides a single interface for emitting both:
- Real-time agent events (EventEmitter) for frontend streaming
- Domain events (EventEmitter) for audit/persistence

This addresses the gap where events were spread across multiple systems
with inconsistent emission patterns.

Usage:
    # Create context for a request
    context = EventContext(
        request_context=RequestContext(
            request_id="req_456",
            capability="example",
            session_id="sess_123",
            user_id="user_789",
        ),
        agent_event_emitter=emitter,
        domain_event_emitter=event_emitter,
    )

    # In agent process():
    await context.emit_agent_started("planner")
    # ... do work ...
    await context.emit_agent_completed("planner", step_count=3, tools=["grep", "read"])
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from jeeves_infra.protocols import LoggerProtocol, RequestContext
from mission_system.adapters import get_logger

if TYPE_CHECKING:
    from mission_system.orchestrator.agent_events import AgentEventEmitter
    from jeeves_infra.memory.services.event_emitter import EventEmitter as DomainEventEmitter


@dataclass
class EventContext:
    """
    Unified context for agent event emission.

    Bridges the real-time EventEmitter (for frontend streaming) with
    the domain EventEmitter (for audit/persistence), ensuring events are
    emitted consistently from a single point.

    Attributes:
        request_context: RequestContext for the request
        agent_event_emitter: Optional emitter for real-time frontend events
        domain_event_emitter: Optional emitter for domain/audit events
        correlation_id: Optional correlation ID for domain events
    """

    request_context: RequestContext
    agent_event_emitter: Optional["AgentEventEmitter"] = None
    domain_event_emitter: Optional["DomainEventEmitter"] = None
    correlation_id: Optional[str] = None
    _logger: Any = field(default=None, repr=False)

    def __post_init__(self):
        if self._logger is None:
            self._logger = get_logger()
        self._logger = self._logger.bind(
            component="agent_event_context",
            session_id=self.request_context.session_id,
            request_id=self.request_context.request_id,
        )
        # Use request_id as correlation_id if not provided
        if self.correlation_id is None:
            self.correlation_id = self.request_context.request_id

    # ========================================================================
    # Agent Lifecycle Events
    # ========================================================================

    async def emit_agent_started(
        self,
        agent_name: str,
        **payload,
    ) -> None:
        """
        Emit agent started event to both systems.

        Args:
            agent_name: Name of the agent (e.g., "planner", "critic")
            **payload: Additional payload data
        """
        # Diagnostic: log whether emitter exists
        has_emitter = self.agent_event_emitter is not None
        self._logger.debug(
            "emit_agent_started_check",
            agent_name=agent_name,
            has_agent_event_emitter=has_emitter,
        )

        if self.agent_event_emitter:
            await self.agent_event_emitter.emit_agent_started(
                agent_name=agent_name,
                request_context=self.request_context,
                **payload,
            )
            self._logger.debug(
                "emit_agent_started_queued",
                agent_name=agent_name,
            )

        self._logger.debug(
            "agent_started",
            agent_name=agent_name,
            **payload,
        )

    async def emit_agent_completed(
        self,
        agent_name: str,
        status: str = "success",
        error: Optional[str] = None,
        **payload,
    ) -> None:
        """
        Emit agent completed event to both systems.

        Args:
            agent_name: Name of the agent
            status: Completion status ("success", "error", "skipped")
            error: Error message if status is "error"
            **payload: Additional payload data (results, stats, etc.)
        """
        if self.agent_event_emitter:
            await self.agent_event_emitter.emit_agent_completed(
                agent_name=agent_name,
                request_context=self.request_context,
                status=status,
                error=error,
                **payload,
            )

        self._logger.debug(
            "agent_completed",
            agent_name=agent_name,
            status=status,
            error=error,
            **payload,
        )

    # ========================================================================
    # Planner Events
    # ========================================================================

    async def emit_plan_created(
        self,
        plan_id: str,
        intent: str,
        confidence: float,
        tools: List[str],
        step_count: int,
        clarification_needed: bool = False,
    ) -> Optional[str]:
        """
        Emit plan created event (domain event for audit).

        This is emitted by the Planner agent after generating a plan.

        Args:
            plan_id: Generated plan identifier
            intent: Intent being planned for
            confidence: Plan confidence/feasibility score (0.0-1.0)
            tools: List of tool names in the plan
            step_count: Number of steps in the plan
            clarification_needed: Whether clarification is needed

        Returns:
            Event ID if domain event emitted, None otherwise
        """
        event_id = None

        if self.domain_event_emitter:
            event_id = await self.domain_event_emitter.emit_plan_created(
                plan_id=plan_id,
                request_id=self.request_context.request_id,
                user_id=self.request_context.user_id or "",
                intent=intent,
                confidence=confidence,
                tool_count=step_count,
                tools=tools,
                clarification_needed=clarification_needed,
                actor="planner",
                correlation_id=self.correlation_id,
                session_id=self.request_context.session_id or "",
            )

        self._logger.info(
            "plan_created",
            plan_id=plan_id,
            intent=intent,
            confidence=confidence,
            step_count=step_count,
            tools=tools[:5],  # Limit for logging
        )

        return event_id

    # ========================================================================
    # Critic Events
    # ========================================================================

    async def emit_critic_decision(
        self,
        action: str,
        confidence: float,
        issue: Optional[str] = None,
        feedback: Optional[str] = None,
    ) -> Optional[str]:
        """
        Emit critic decision event (domain event for audit).

        This is emitted by the Critic agent after evaluating results.

        Args:
            action: Critic verdict ("approved", "loop_back", "next_stage")
            confidence: Decision confidence (0.0-1.0)
            issue: Issue description if not approved
            feedback: Refine intent hint for loop_back verdict

        Returns:
            Event ID if domain event emitted, None otherwise
        """
        event_id = None

        if self.domain_event_emitter:
            event_id = await self.domain_event_emitter.emit_critic_decision(
                request_id=self.request_context.request_id,
                user_id=self.request_context.user_id or "",
                action=action,
                confidence=confidence,
                issue=issue,
                feedback=feedback,
                actor="critic",
                correlation_id=self.correlation_id,
                session_id=self.request_context.session_id or "",
            )

        self._logger.info(
            "critic_decision",
            action=action,
            confidence=confidence,
            issue=issue,
        )

        return event_id

    # ========================================================================
    # Tool Execution Events
    # ========================================================================

    def _create_params_preview(
        self,
        params: Dict[str, Any],
        max_value_length: int = 100,
    ) -> Dict[str, str]:
        """Create truncated, serializable preview of parameters.

        Phase 2.1: Ensures params are safe for streaming without
        exposing full content that might be large or sensitive.

        Args:
            params: Original parameters
            max_value_length: Max chars per value in preview

        Returns:
            Dict with truncated string representations
        """
        preview = {}
        for key, value in params.items():
            if value is None:
                preview[key] = "null"
            elif isinstance(value, str):
                if len(value) > max_value_length:
                    preview[key] = f"{value[:max_value_length]}..."
                else:
                    preview[key] = value
            elif isinstance(value, (int, float, bool)):
                preview[key] = str(value)
            elif isinstance(value, (list, dict)):
                str_repr = str(value)
                if len(str_repr) > max_value_length:
                    preview[key] = f"{str_repr[:max_value_length]}..."
                else:
                    preview[key] = str_repr
            else:
                preview[key] = f"<{type(value).__name__}>"
        return preview

    async def emit_tool_started(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
        step_number: Optional[int] = None,
        total_steps: Optional[int] = None,
        **payload,
    ) -> None:
        """
        Emit tool execution started event with parameter preview.

        Phase 2.1: Includes truncated, serializable parameter preview.

        Args:
            tool_name: Name of the tool being executed
            params: Tool parameters (will be truncated for streaming)
            step_number: Current step number (1-indexed)
            total_steps: Total number of steps in plan
            **payload: Additional payload data

        Constitutional compliance (P2 - Code Context Priority):
            Provides visibility into tool calls without exposing full params.
        """
        # Phase 2.1: Create truncated params preview
        params_preview = self._create_params_preview(params) if params else None

        if self.agent_event_emitter:
            await self.agent_event_emitter.emit_tool_started(
                tool_name=tool_name,
                request_context=self.request_context,
                params_preview=params_preview,
                step_number=step_number,
                total_steps=total_steps,
                **payload,
            )

        self._logger.debug(
            "tool_started",
            tool_name=tool_name,
            params_preview=params_preview,
            step_number=step_number,
        )

    async def emit_tool_completed(
        self,
        tool_name: str,
        status: str = "success",
        execution_time_ms: Optional[int] = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Emit tool execution completed event to both systems.

        Phase 2.2: Includes error_type for better observability.

        Args:
            tool_name: Name of the tool
            status: Execution status ("success", "error")
            execution_time_ms: Duration in milliseconds
            error: Error message if failed
            error_type: Error classification (e.g., "validation_error", "tool_error")

        Returns:
            Event ID if domain event emitted, None otherwise

        Constitutional compliance (P3 - Bounded Efficiency):
            Provides clear error categorization for debugging without exposing internals.
        """
        event_id = None

        # Real-time event with error details
        if self.agent_event_emitter:
            await self.agent_event_emitter.emit_tool_completed(
                tool_name=tool_name,
                request_context=self.request_context,
                status=status,
                error_type=error_type,  # Phase 2.2: Include error type
                execution_time_ms=execution_time_ms,
            )

        # Domain event for audit
        if self.domain_event_emitter:
            event_id = await self.domain_event_emitter.emit_tool_executed(
                request_id=self.request_context.request_id,
                user_id=self.request_context.user_id or "",
                tool_name=tool_name,
                status=status,
                execution_time_ms=execution_time_ms,
                error=error,
                actor="traverser",
                correlation_id=self.correlation_id,
                session_id=self.request_context.session_id or "",
            )

        # Phase 2.2: Log with error details for debugging
        if status == "error":
            self._logger.warning(
                "tool_completed_error",
                tool_name=tool_name,
                error_type=error_type,
                error=error[:200] if error else None,  # Truncate for logging
                execution_time_ms=execution_time_ms,
            )

        return event_id

    # ========================================================================
    # Retry Events
    # ========================================================================

    async def emit_retry_attempt(
        self,
        retry_type: str,
        attempt_number: int,
        reason: str,
        feedback: Optional[str] = None,
    ) -> Optional[str]:
        """
        Emit retry attempt event (domain event for audit).

        Args:
            retry_type: Type of retry ("validator", "planner")
            attempt_number: Which retry attempt (1, 2, ...)
            reason: Why retry was triggered
            feedback: Specific feedback for the retry

        Returns:
            Event ID if domain event emitted, None otherwise
        """
        event_id = None

        if self.domain_event_emitter:
            event_id = await self.domain_event_emitter.emit_retry_attempt(
                request_id=self.request_context.request_id,
                user_id=self.request_context.user_id or "",
                retry_type=retry_type,
                attempt_number=attempt_number,
                reason=reason,
                feedback=feedback,
                actor="orchestrator",
                correlation_id=self.correlation_id,
                session_id=self.request_context.session_id or "",
            )

        self._logger.info(
            "retry_attempt",
            retry_type=retry_type,
            attempt_number=attempt_number,
            reason=reason,
        )

        return event_id

    # ========================================================================
    # Response Events
    # ========================================================================

    async def emit_response_drafted(
        self,
        response_id: str,
        response_preview: str,
        validation_status: str = "pending",
    ) -> Optional[str]:
        """
        Emit response drafted event (domain event for audit).

        Args:
            response_id: Response identifier
            response_preview: Preview of the response (first 200 chars)
            validation_status: Validation status

        Returns:
            Event ID if domain event emitted, None otherwise
        """
        event_id = None

        if self.domain_event_emitter:
            event_id = await self.domain_event_emitter.emit_response_drafted(
                response_id=response_id,
                request_id=self.request_context.request_id,
                user_id=self.request_context.user_id or "",
                response_preview=response_preview,
                validation_status=validation_status,
                actor="integration",
                correlation_id=self.correlation_id,
                session_id=self.request_context.session_id or "",
            )

        return event_id

    # ========================================================================
    # Stage Transition Events
    # ========================================================================

    async def emit_stage_transition(
        self,
        from_stage: int,
        to_stage: int,
        satisfied_goals: Optional[List[str]] = None,
        remaining_goals: Optional[List[str]] = None,
    ) -> None:
        """
        Emit stage transition event (for multi-stage workflows).

        Args:
            from_stage: Previous stage number
            to_stage: New stage number
            satisfied_goals: Goals completed in previous stage
            remaining_goals: Goals remaining for next stage
        """
        if self.agent_event_emitter:
            await self.agent_event_emitter.emit_stage_transition(
                request_context=self.request_context,
                from_stage=from_stage,
                to_stage=to_stage,
                satisfied_goals=satisfied_goals or [],
                remaining_goals=remaining_goals or [],
            )

    # ========================================================================
    # Flow Events
    # ========================================================================

    async def emit_flow_started(self) -> None:
        """Emit flow started event."""
        if self.agent_event_emitter:
            from mission_system.orchestrator.agent_events import AgentEvent, AgentEventType

            event = AgentEvent(
                event_type=AgentEventType.FLOW_STARTED,
                agent_name="orchestrator",
                request_context=self.request_context,
                session_id=self.request_context.session_id or "",
                request_id=self.request_context.request_id,
            )
            await self.agent_event_emitter.emit(event)

    async def emit_flow_completed(self, status: str = "success") -> None:
        """Emit flow completed event."""
        if self.agent_event_emitter:
            from mission_system.orchestrator.agent_events import AgentEvent, AgentEventType

            event = AgentEvent(
                event_type=AgentEventType.FLOW_COMPLETED,
                agent_name="orchestrator",
                request_context=self.request_context,
                session_id=self.request_context.session_id or "",
                request_id=self.request_context.request_id,
                payload={"status": status},
            )
            await self.agent_event_emitter.emit(event)

    async def emit_flow_error(self, error: str) -> None:
        """Emit flow error event."""
        if self.agent_event_emitter:
            from mission_system.orchestrator.agent_events import AgentEvent, AgentEventType

            event = AgentEvent(
                event_type=AgentEventType.FLOW_ERROR,
                agent_name="orchestrator",
                request_context=self.request_context,
                session_id=self.request_context.session_id or "",
                request_id=self.request_context.request_id,
                payload={"error": error},
            )
            await self.agent_event_emitter.emit(event)

    # ========================================================================
    # Agent Reasoning Events (Phase 2.3 - Config-Gated)
    # ========================================================================

    async def emit_agent_reasoning(
        self,
        agent_name: str,
        reasoning_type: str,
        reasoning_text: str,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit agent reasoning/CoT event (config-gated).

        Phase 2.3: Optional emission of intermediate reasoning for observability.
        Only emits when FEATURE_EMIT_AGENT_REASONING=true.

        Args:
            agent_name: Name of the agent (e.g., "planner", "critic")
            reasoning_type: Type of reasoning ("planning", "critique", "synthesis")
            reasoning_text: The reasoning/thinking content (will be truncated)
            confidence: Optional confidence score for this reasoning step
            metadata: Optional additional context

        Constitutional compliance (P2 - Code Context Priority):
            - Provides visibility into agent decision-making
            - Lives entirely in mission/avionics layer (no core changes)
            - Does not affect core data structures
        """
        # Config gate: Check feature flag
        try:
            from mission_system.adapters import get_feature_flags
            flags = get_feature_flags()
            if not flags.emit_agent_reasoning:
                return
        except ImportError:
            # If feature flags not available, skip emission
            return

        # Truncate reasoning for streaming efficiency
        max_reasoning_length = 500
        truncated_reasoning = reasoning_text[:max_reasoning_length]
        if len(reasoning_text) > max_reasoning_length:
            truncated_reasoning += "..."

        if self.agent_event_emitter:
            from mission_system.orchestrator.agent_events import AgentEvent, AgentEventType

            # Use AGENT_COMPLETED with special payload for reasoning
            # (avoids adding new event type to core)
            event = AgentEvent(
                event_type=AgentEventType.AGENT_COMPLETED,
                agent_name=f"{agent_name}_reasoning",
                request_context=self.request_context,
                session_id=self.request_context.session_id or "",
                request_id=self.request_context.request_id,
                payload={
                    "type": "reasoning",
                    "reasoning_type": reasoning_type,
                    "reasoning": truncated_reasoning,
                    "confidence": confidence,
                    "metadata": metadata or {},
                },
            )
            await self.agent_event_emitter.emit(event)

        self._logger.debug(
            "agent_reasoning",
            agent_name=agent_name,
            reasoning_type=reasoning_type,
            reasoning_preview=truncated_reasoning[:100],
            confidence=confidence,
        )

    # ========================================================================
    # Utility Methods
    # ========================================================================

    async def close(self) -> None:
        """Close the event context and signal end of streaming."""
        if self.agent_event_emitter:
            await self.agent_event_emitter.close()

    def get_event_nowait(self) -> Any:
        """Get an event without waiting (for streaming consumers)."""
        if self.agent_event_emitter:
            return self.agent_event_emitter.get_nowait()
        return None


def create_event_context(
    request_context: RequestContext,
    agent_event_emitter: Optional["AgentEventEmitter"] = None,
    domain_event_emitter: Optional["DomainEventEmitter"] = None,
    correlation_id: Optional[str] = None,
) -> EventContext:
    """
    Factory function to create an EventContext.

    Args:
        request_context: RequestContext for the request
        agent_event_emitter: Optional emitter for real-time frontend events
        domain_event_emitter: Optional emitter for domain/audit events
        correlation_id: Optional correlation ID for domain events

    Returns:
        Configured EventContext instance
    """
    return EventContext(
        request_context=request_context,
        agent_event_emitter=agent_event_emitter,
        domain_event_emitter=domain_event_emitter,
        correlation_id=correlation_id,
    )
