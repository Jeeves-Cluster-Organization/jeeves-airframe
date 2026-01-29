"""Gateway Event Bus - Pub/Sub for internal gateway events.

Constitutional Pattern:
- Routers PUBLISH events (fire and forget)
- WebSocket handler SUBSCRIBES to events
- Zero coupling between routers and WebSocket implementation

UNIFIED EVENT SUPPORT (2025-12-14):
- Now uses Event from protocols.events
- Implements EventEmitterProtocol for constitutional compliance
- Backward compatible with legacy string-based publish (deprecated)

Usage:
    # NEW: Using Event (preferred)
    from mission_system.gateway.event_bus import gateway_events
    from protocols.events import Event, EventCategory

    event = Event.create_now(
        event_type="agent.started",
        category=EventCategory.AGENT_LIFECYCLE,
        request_context=RequestContext(
            request_id="req_123",
            capability="example",
            session_id="sess_456",
        ),
        payload={"agent": "planner"},
    )
    await gateway_events.emit(event)

    # In main.py (subscriber)
    from mission_system.gateway.event_bus import gateway_events
    gateway_events.subscribe("agent.*", broadcast_handler)
"""

import asyncio
import fnmatch
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Set
from weakref import WeakSet

from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols.events import (
    Event,
    EventCategory,
    EventSeverity,
    EventEmitterProtocol,
)


# Type alias for event handlers (now receives Event)
EventHandler = Callable[[Event], Awaitable[None]]


class GatewayEventBus(EventEmitterProtocol):
    """Constitutional async event bus for gateway internal communication.

    Features:
    - Pattern-based subscriptions (e.g., "agent.*" matches "agent.started")
    - Async handlers receiving Event instances
    - Fire-and-forget publishing (errors logged, not propagated)
    - Implements EventEmitterProtocol for swappable implementations

    Constitutional Compliance:
    - Infrastructure R2 (Configuration Over Code): Event schema defined declaratively
    - Infrastructure R3 (No Domain Logic): Pure transport - no business logic
    - Infrastructure R4 (Swappable Implementations): Implements EventEmitterProtocol
    - Decouples publishers from subscribers
    - Routers don't need to know about WebSocket implementation
    - WebSocket handler doesn't need to know about router internals
    """

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._subscriptions: Dict[str, str] = {}  # subscription_id -> pattern
        self._logger = None

    @property
    def logger(self):
        if self._logger is None:
            self._logger = get_current_logger()
        return self._logger

    async def emit(self, event: Event) -> None:
        """
        Emit a unified event to all matching subscribers.

        Fire-and-forget: errors in handlers are logged but not propagated.

        Args:
            event: Event instance to emit
        """
        handlers_invoked = 0

        for pattern, handlers in self._handlers.items():
            if self._matches_pattern(event.event_type, pattern):
                for handler in handlers:
                    try:
                        await handler(event)
                        handlers_invoked += 1
                    except Exception as e:
                        self.logger.error(
                            "event_bus_handler_error",
                            event_type=event.event_type,
                            event_id=event.event_id,
                            pattern=pattern,
                            error=str(e),
                            error_type=type(e).__name__,
                        )

        if handlers_invoked > 0:
            self.logger.debug(
                "event_emitted",
                event_type=event.event_type,
                event_id=event.event_id,
                handlers_invoked=handlers_invoked,
            )

    async def subscribe(
        self,
        pattern: str,
        handler: Callable[[Event], Awaitable[None]],
    ) -> str:
        """
        Subscribe to events matching a pattern.

        Args:
            pattern: Event type pattern (supports * wildcards)
                     e.g., "agent.*" matches "agent.started", "agent.completed"
            handler: Async function to call with Event

        Returns:
            Subscription ID for later unsubscription
        """
        if pattern not in self._handlers:
            self._handlers[pattern] = []
        self._handlers[pattern].append(handler)

        subscription_id = str(uuid.uuid4())
        self._subscriptions[subscription_id] = pattern

        self.logger.debug("event_bus_subscribed", pattern=pattern, subscription_id=subscription_id)
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """
        Unsubscribe from events.

        Args:
            subscription_id: ID returned from subscribe()
        """
        if subscription_id in self._subscriptions:
            pattern = self._subscriptions[subscription_id]
            # Note: We don't remove handlers here because we don't track
            # which handler corresponds to which subscription ID.
            # This is a limitation of the current implementation.
            del self._subscriptions[subscription_id]
            self.logger.debug("event_bus_unsubscribed", subscription_id=subscription_id, pattern=pattern)

    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """
        Check if event_type matches subscription pattern.

        Args:
            event_type: Event type string (e.g., "agent.started")
            pattern: Subscription pattern (e.g., "agent.*")

        Returns:
            True if event_type matches pattern
        """
        return fnmatch.fnmatch(event_type, pattern)

    def clear(self) -> None:
        """Clear all subscriptions (for testing)."""
        self._handlers.clear()
        self._subscriptions.clear()


# Global event bus instance for gateway
gateway_events = GatewayEventBus()


__all__ = [
    "GatewayEventBus",
    "gateway_events",
]
