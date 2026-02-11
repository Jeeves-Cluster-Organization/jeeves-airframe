"""
Agent event streaming for real-time frontend updates.

Provides an async queue-based mechanism to stream events from
capability orchestrators to the IPC transport, enabling real-time
visibility into agent activity.

Agent names and pipeline structure are capability-owned -- this module
provides only generic event types. Events are dynamically qualified as
``agent.{name}.started`` / ``agent.{name}.completed`` at serialization time.
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
    """Generic event types -- no agent names hardcoded.

    Capabilities define their own agent names; airframe only knows
    about lifecycle categories.
    """

    # Agent lifecycle (capability provides agent_name at emit time)
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_DECISION = "agent.decision"

    # Tool execution
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"

    # Orchestrator-level events
    STAGE_TRANSITION = "orchestrator.stage_transition"
    FLOW_STARTED = "orchestrator.started"
    FLOW_COMPLETED = "orchestrator.completed"
    FLOW_ERROR = "orchestrator.error"


@dataclass
class AgentEvent:
    """An event emitted by an agent during processing.

    These events are streamed to the frontend for real-time visibility
    into capability pipeline activity.
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

        Emits a qualified event_type: ``agent.{agent_name}.started``
        so consumers can filter by agent without airframe knowing names.
        """
        # Build qualified event string: "agent.planner.started" etc.
        base = self.event_type.value  # e.g. "agent.started"
        parts = base.split(".")
        if parts[0] == "agent" and self.agent_name:
            qualified = f"agent.{self.agent_name}.{parts[-1]}"
        else:
            qualified = base

        return {
            "event_type": qualified,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "timestamp_ms": self.timestamp_ms,
            "request_context": self.request_context.to_dict(),
            **self.payload,
        }

    def to_json(self) -> str:
        """Convert to JSON string for IPC transport payload."""
        return json.dumps(self.to_dict())


class EventEmitter:
    """Async queue-based event emitter for agent activity.

    Capability orchestrators use this to emit events during processing,
    which are consumed by the IPC transport and broadcast to WebSocket clients.

    Example:
        emitter = EventEmitter()

        # In capability nodes:
        await emitter.emit_agent_started("planner", request_context)
        # ... do work ...
        await emitter.emit_agent_completed("planner", request_context, result=data)

        # In servicer:
        async for event in emitter.events():
            yield convert_to_flow_event(event)
    """

    def __init__(self, maxsize: int = 100):
        self._queue: asyncio.Queue[Optional[AgentEvent]] = asyncio.Queue(maxsize=maxsize)
        self._closed = False

    async def emit(self, event: AgentEvent) -> None:
        """Emit an event to the queue."""
        if not self._closed:
            await self._queue.put(event)
            from jeeves_infra.logging import get_current_logger as get_logger
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
        """Emit an agent started event.

        Args:
            agent_name: Capability-defined agent name (e.g., "planner", "critic")
            request_context: Current request context
            **payload: Additional payload data
        """
        event = AgentEvent(
            event_type=AgentEventType.AGENT_STARTED,
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
        """Emit an agent completed event.

        Args:
            agent_name: Capability-defined agent name
            request_context: Current request context
            **payload: Additional payload data (results, stats, etc.)
        """
        event = AgentEvent(
            event_type=AgentEventType.AGENT_COMPLETED,
            agent_name=agent_name,
            request_context=request_context,
            session_id=request_context.session_id or "",
            request_id=request_context.request_id,
            payload=payload,
        )
        await self.emit(event)

    async def emit_agent_decision(
        self,
        agent_name: str,
        request_context: RequestContext,
        action: str,
        confidence: float = 1.0,
        **payload,
    ) -> None:
        """Emit an agent decision event (e.g., critic verdict).

        Args:
            agent_name: The deciding agent (capability-defined)
            request_context: Current request context
            action: Decision action (capability-defined, e.g., "approved", "loop_back")
            confidence: Decision confidence (0.0-1.0)
            **payload: Additional payload (issue, feedback, etc.)
        """
        event = AgentEvent(
            event_type=AgentEventType.AGENT_DECISION,
            agent_name=agent_name,
            request_context=request_context,
            session_id=request_context.session_id or "",
            request_id=request_context.request_id,
            payload={"action": action, "confidence": confidence, **payload},
        )
        await self.emit(event)

    async def emit_tool_started(
        self,
        tool_name: str,
        request_context: RequestContext,
        agent_name: str,
        **payload,
    ) -> None:
        """Emit a tool execution started event.

        Args:
            tool_name: Name of the tool being executed
            request_context: Current request context
            agent_name: Agent executing the tool (capability-defined)
            **payload: Additional payload data
        """
        event = AgentEvent(
            event_type=AgentEventType.TOOL_STARTED,
            agent_name=agent_name,
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
        agent_name: str,
        status: str = "success",
        **payload,
    ) -> None:
        """Emit a tool execution completed event.

        Args:
            tool_name: Name of the tool that completed
            request_context: Current request context
            agent_name: Agent that executed the tool (capability-defined)
            status: Execution status
            **payload: Additional payload data
        """
        event = AgentEvent(
            event_type=AgentEventType.TOOL_COMPLETED,
            agent_name=agent_name,
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
        """Close the emitter, signaling no more events will be sent."""
        self._closed = True
        await self._queue.put(None)

    async def events(self) -> AsyncIterator[AgentEvent]:
        """Iterate over emitted events until close() is called."""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event

    def get_nowait(self) -> Optional[AgentEvent]:
        """Get an event without waiting, or None if queue is empty."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


def create_agent_event_emitter() -> EventEmitter:
    """Factory function to create an event emitter."""
    return EventEmitter()
