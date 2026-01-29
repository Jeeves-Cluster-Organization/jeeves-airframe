"""Event types for the gateway event bus.

Provides:
- Event: Core event dataclass
- EventCategory: Event categorization enum
- EventSeverity: Event severity enum
- EventEmitterProtocol: Protocol for event emission
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol
import uuid


class EventCategory(str, Enum):
    """Categories for event classification."""
    AGENT_LIFECYCLE = "agent_lifecycle"
    TOOL_EXECUTION = "tool_execution"
    CRITIC_DECISION = "critic_decision"
    PIPELINE_FLOW = "pipeline_flow"
    STAGE_TRANSITION = "stage_transition"
    DOMAIN_EVENT = "domain_event"
    SYSTEM = "system"


class EventSeverity(str, Enum):
    """Severity levels for events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Event:
    """Unified event for gateway pub/sub.

    Attributes:
        event_id: Unique identifier for this event
        event_type: Namespaced event type (e.g., "agent.started")
        category: Event category for filtering
        timestamp_iso: ISO 8601 timestamp
        timestamp_ms: Unix timestamp in milliseconds
        request_context: Request context (optional)
        request_id: Request correlation ID
        session_id: Session correlation ID
        user_id: User identifier
        payload: Event-specific data
        severity: Event severity level
        source: Event source identifier
        version: Event schema version
    """
    event_id: str
    event_type: str
    category: EventCategory
    timestamp_iso: str
    timestamp_ms: int
    request_context: Optional[Any] = None
    request_id: str = ""
    session_id: str = ""
    user_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    severity: EventSeverity = EventSeverity.INFO
    source: str = ""
    version: str = "1.0"

    @classmethod
    def create_now(
        cls,
        event_type: str,
        category: EventCategory,
        request_context: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
        severity: EventSeverity = EventSeverity.INFO,
        source: str = "gateway",
    ) -> "Event":
        """Create an event with current timestamp.

        Args:
            event_type: Namespaced event type
            category: Event category
            request_context: Optional request context
            payload: Optional event payload
            severity: Event severity level
            source: Event source identifier

        Returns:
            New Event instance
        """
        now = datetime.now(timezone.utc)
        request_id = ""
        session_id = ""
        user_id = ""

        if request_context:
            request_id = getattr(request_context, "request_id", "")
            session_id = getattr(request_context, "session_id", "")
            user_id = getattr(request_context, "user_id", "")

        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            category=category,
            timestamp_iso=now.isoformat(),
            timestamp_ms=int(now.timestamp() * 1000),
            request_context=request_context,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            payload=payload or {},
            severity=severity,
            source=source,
        )


class EventEmitterProtocol(Protocol):
    """Protocol for event emission."""

    async def emit(self, event: Event) -> None:
        """Emit an event to subscribers."""
        ...

    async def subscribe(
        self,
        pattern: str,
        handler: Callable[[Event], Awaitable[None]],
    ) -> str:
        """Subscribe to events matching a pattern."""
        ...

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from events."""
        ...


__all__ = [
    "Event",
    "EventCategory",
    "EventSeverity",
    "EventEmitterProtocol",
]
