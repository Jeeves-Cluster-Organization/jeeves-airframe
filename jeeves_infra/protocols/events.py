"""Unified event types for the gateway event bus."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional
import uuid

from jeeves_infra.protocols.interfaces import RequestContext


class EventCategory(str, Enum):
    AGENT_LIFECYCLE = "agent_lifecycle"
    CRITIC_DECISION = "critic_decision"
    TOOL_EXECUTION = "tool_execution"
    PIPELINE_FLOW = "pipeline_flow"
    STAGE_TRANSITION = "stage_transition"
    DOMAIN_EVENT = "domain_event"


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Event:
    """A structured event emitted by the gateway event bus."""
    event_id: str
    event_type: str
    category: EventCategory
    timestamp_iso: str
    timestamp_ms: int
    request_context: RequestContext
    request_id: str
    session_id: str
    user_id: Optional[str]
    payload: Dict[str, Any]
    severity: EventSeverity
    source: str
    version: str = "1.0"

    @classmethod
    def create_now(
        cls,
        event_type: str,
        category: EventCategory,
        request_context: RequestContext,
        payload: Optional[Dict[str, Any]] = None,
        severity: EventSeverity = EventSeverity.INFO,
        source: str = "",
        version: str = "1.0",
    ) -> "Event":
        now = datetime.now(timezone.utc)
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            category=category,
            timestamp_iso=now.isoformat(),
            timestamp_ms=int(now.timestamp() * 1000),
            request_context=request_context,
            request_id=request_context.request_id,
            session_id=request_context.session_id or "",
            user_id=request_context.user_id,
            payload=payload or {},
            severity=severity,
            source=source,
            version=version,
        )


class EventEmitterProtocol:
    """Protocol for event bus emitter implementations."""

    async def emit(self, event: Event) -> None:
        raise NotImplementedError

    async def subscribe(
        self, pattern: str, handler: Callable[[Event], Awaitable[None]]
    ) -> str:
        raise NotImplementedError

    async def unsubscribe(self, subscription_id: str) -> None:
        raise NotImplementedError
