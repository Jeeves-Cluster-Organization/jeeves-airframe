"""
Agent event streaming for real-time frontend updates.

Provides an async queue-based mechanism to stream events from the
CodeAnalysisFlowService to the gRPC servicer, enabling real-time
visibility into agent activity.

Each agent (perception, intent, planner, traverser, synthesizer,
critic, integration) emits start and complete events that are
broadcast to the frontend via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, AsyncIterator

from jeeves_infra.protocols import RequestContext


class AgentEventType(Enum):
    """Types of agent events for frontend display."""

    # Agent lifecycle events
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"

    # Specific agent events (for richer details)
    # Standardized naming: agent.<component>.<action>
    PERCEPTION_STARTED = "agent.perception.started"
    PERCEPTION_COMPLETED = "agent.perception.completed"
    INTENT_STARTED = "agent.intent.started"
    INTENT_COMPLETED = "agent.intent.completed"
    PLANNER_STARTED = "agent.planner.started"
    PLANNER_COMPLETED = "agent.planner.completed"
    TRAVERSER_STARTED = "agent.traverser.started"
    TRAVERSER_COMPLETED = "agent.traverser.completed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    SYNTHESIZER_STARTED = "agent.synthesizer.started"
    SYNTHESIZER_COMPLETED = "agent.synthesizer.completed"
    CRITIC_STARTED = "agent.critic.started"
    CRITIC_DECISION = "agent.critic.decision"
    INTEGRATION_STARTED = "agent.integration.started"
    INTEGRATION_COMPLETED = "agent.integration.completed"
    STAGE_TRANSITION = "orchestrator.stage_transition"

    # Flow events
    FLOW_STARTED = "orchestrator.started"
    FLOW_COMPLETED = "orchestrator.completed"
    FLOW_ERROR = "orchestrator.error"


@dataclass
class AgentEvent:
    """
    An event emitted by an agent during processing.

    These events are streamed to the frontend for real-time visibility
    into the 7-agent pipeline activity.
    """

    event_type: AgentEventType
    agent_name: str
    request_context: RequestContext
    session_id: str
    request_id: str
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.request_context is None:
            raise ValueError("request_context is required for AgentEvent")
        if self.request_id and self.request_id != self.request_context.request_id:
            raise ValueError("request_id does not match request_context.request_id")
        if self.session_id and (self.request_context.session_id is None or self.session_id != self.request_context.session_id):
            raise ValueError("session_id does not match request_context.session_id")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Key names match what gateway/routers/chat.py expects:
        - event_type: The event type string (e.g., "perception.started")
        - agent_name: The agent that emitted the event
        """
        return {
            "event_type": self.event_type.value,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "timestamp_ms": self.timestamp_ms,
            "request_context": self.request_context.to_dict(),
            **self.payload,
        }

    def to_json(self) -> str:
        """Convert to JSON string for gRPC payload."""
        return json.dumps(self.to_dict())


class EventEmitter:
    """
    Async queue-based event emitter for agent activity.

    Used by the CodeAnalysisFlowService to emit events during processing,
    which are then consumed by the gRPC servicer and broadcast to WebSocket
    clients.

    Example:
        emitter = EventEmitter()

        # In service/nodes:
        await emitter.emit_agent_started("planner", request_context)
        # ... do work ...
        await emitter.emit_agent_completed("planner", request_context, payload)

        # In servicer:
        async for event in emitter.events():
            yield convert_to_flow_event(event)
    """

    def __init__(self, maxsize: int = 100):
        """
        Initialize the event emitter.

        Args:
            maxsize: Maximum queue size (prevents memory bloat)
        """
        self._queue: asyncio.Queue[Optional[AgentEvent]] = asyncio.Queue(maxsize=maxsize)
        self._closed = False

    async def emit(self, event: AgentEvent) -> None:
        """
        Emit an event to the queue.

        Args:
            event: The event to emit
        """
        if not self._closed:
            await self._queue.put(event)
            # Diagnostic: log queue state after emit
            from mission_system.adapters import get_logger
            logger = get_logger()
            logger.debug(
                "agent_event_emitter_queued",
                event_type=event.event_type.value,
                agent_name=event.agent_name,
                queue_size=self._queue.qsize(),
            )

    async def emit_agent_started(
        self,
        agent_name: str,
        request_context: RequestContext,
        **payload,
    ) -> None:
        """
        Emit an agent started event.

        Args:
            agent_name: Name of the agent (e.g., "planner", "critic")
            session_id: Current session ID
            request_id: Current request ID
            **payload: Additional payload data
        """
        # Map agent name to specific event type
        event_type_map = {
            "perception": AgentEventType.PERCEPTION_STARTED,
            "intent": AgentEventType.INTENT_STARTED,
            "planner": AgentEventType.PLANNER_STARTED,
            "executor": AgentEventType.TRAVERSER_STARTED,  # executor is the new name for traverser
            "traverser": AgentEventType.TRAVERSER_STARTED,
            "synthesizer": AgentEventType.SYNTHESIZER_STARTED,
            "critic": AgentEventType.CRITIC_STARTED,
            "integration": AgentEventType.INTEGRATION_STARTED,
        }
        event_type = event_type_map.get(agent_name.lower(), AgentEventType.AGENT_STARTED)

        event = AgentEvent(
            event_type=event_type,
            agent_name=agent_name,
            request_context=request_context,
            session_id=request_context.session_id or "",
            request_id=request_context.request_id,
            payload=payload,
        )
        await self.emit(event)

    async def emit_agent_completed(
        self,
        agent_name: str,
        request_context: RequestContext,
        **payload,
    ) -> None:
        """
        Emit an agent completed event.

        Args:
            agent_name: Name of the agent
            session_id: Current session ID
            request_id: Current request ID
            **payload: Additional payload data (results, stats, etc.)
        """
        # Map agent name to specific event type
        event_type_map = {
            "perception": AgentEventType.PERCEPTION_COMPLETED,
            "intent": AgentEventType.INTENT_COMPLETED,
            "planner": AgentEventType.PLANNER_COMPLETED,
            "executor": AgentEventType.TRAVERSER_COMPLETED,  # executor is the new name for traverser
            "traverser": AgentEventType.TRAVERSER_COMPLETED,
            "synthesizer": AgentEventType.SYNTHESIZER_COMPLETED,
            "critic": AgentEventType.CRITIC_DECISION,
            "integration": AgentEventType.INTEGRATION_COMPLETED,
        }
        event_type = event_type_map.get(agent_name.lower(), AgentEventType.AGENT_COMPLETED)

        event = AgentEvent(
            event_type=event_type,
            agent_name=agent_name,
            request_context=request_context,
            session_id=request_context.session_id or "",
            request_id=request_context.request_id,
            payload=payload,
        )
        await self.emit(event)

    async def emit_tool_started(
        self,
        tool_name: str,
        request_context: RequestContext,
        **payload,
    ) -> None:
        """Emit a tool execution started event."""
        event = AgentEvent(
            event_type=AgentEventType.TOOL_STARTED,
            agent_name="traverser",
            request_context=request_context,
            session_id=request_context.session_id or "",
            request_id=request_context.request_id,
            payload={"tool_name": tool_name, **payload},
        )
        await self.emit(event)

    async def emit_tool_completed(
        self,
        tool_name: str,
        request_context: RequestContext,
        status: str = "success",
        **payload,
    ) -> None:
        """Emit a tool execution completed event."""
        event = AgentEvent(
            event_type=AgentEventType.TOOL_COMPLETED,
            agent_name="traverser",
            request_context=request_context,
            session_id=request_context.session_id or "",
            request_id=request_context.request_id,
            payload={"tool_name": tool_name, "status": status, **payload},
        )
        await self.emit(event)

    async def emit_stage_transition(
        self,
        request_context: RequestContext,
        from_stage: int,
        to_stage: int,
        satisfied_goals: list = None,
        remaining_goals: list = None,
    ) -> None:
        """Emit a multi-stage transition event."""
        event = AgentEvent(
            event_type=AgentEventType.STAGE_TRANSITION,
            agent_name="orchestrator",
            request_context=request_context,
            session_id=request_context.session_id or "",
            request_id=request_context.request_id,
            payload={
                "from_stage": from_stage,
                "to_stage": to_stage,
                "satisfied_goals": satisfied_goals or [],
                "remaining_goals": remaining_goals or [],
            },
        )
        await self.emit(event)

    async def close(self) -> None:
        """
        Close the emitter, signaling no more events will be sent.

        This puts a None sentinel in the queue to signal the consumer
        that event streaming is complete.
        """
        self._closed = True
        await self._queue.put(None)

    async def events(self) -> AsyncIterator[AgentEvent]:
        """
        Iterate over emitted events.

        Yields events until close() is called and the sentinel is received.

        Yields:
            AgentEvent instances as they are emitted
        """
        while True:
            event = await self._queue.get()
            if event is None:
                # Sentinel received, stop iterating
                break
            yield event

    def get_nowait(self) -> Optional[AgentEvent]:
        """
        Get an event without waiting.

        Returns:
            AgentEvent if available, None if queue is empty
        """
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


def create_agent_event_emitter() -> EventEmitter:
    """Factory function to create an event emitter."""
    return EventEmitter()
