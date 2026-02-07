"""Memory Events - Published when memory operations occur.

These events enable event-driven architecture for memory operations.
Other components can subscribe to be notified of memory changes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MemoryStored:
    """Published when a memory item is stored.

    Attributes:
        item_id: Unique identifier of stored item
        layer: Memory layer (L1-L7)
        user_id: Owner user ID
        item_type: Type of item (fact, message, etc.)
        timestamp: When the item was stored
    """
    category: str = field(default="event", init=False)
    item_id: str = ""
    layer: str = ""
    user_id: str = ""
    item_type: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRetrieved:
    """Published when memory is queried.

    Attributes:
        query: Search query used
        layer: Memory layer searched
        results_count: Number of results returned
        latency_ms: Query latency in milliseconds
    """
    category: str = field(default="event", init=False)
    query: str = ""
    layer: str = ""
    results_count: int = 0
    latency_ms: float = 0.0
    user_id: Optional[str] = None


@dataclass(frozen=True)
class MemoryDeleted:
    """Published when a memory item is deleted.

    Attributes:
        item_id: Deleted item ID
        layer: Memory layer
        user_id: Owner user ID
        soft_delete: Whether this was a soft delete
    """
    category: str = field(default="event", init=False)
    item_id: str = ""
    layer: str = ""
    user_id: str = ""
    soft_delete: bool = True


@dataclass(frozen=True)
class SessionStateChanged:
    """Published when session state changes.

    Attributes:
        session_id: Session identifier
        user_id: User identifier
        change_type: Type of change (focus, entity_added, clarification)
    """
    category: str = field(default="event", init=False)
    session_id: str = ""
    user_id: str = ""
    change_type: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class FocusChanged:
    """Published when session focus changes.

    Attributes:
        session_id: Session identifier
        focus_type: New focus type
        focus_id: Optional focus target ID
        focus_label: Human-readable focus description
    """
    category: str = field(default="event", init=False)
    session_id: str = ""
    focus_type: str = ""
    focus_id: Optional[str] = None
    focus_label: Optional[str] = None


@dataclass(frozen=True)
class EntityReferenced:
    """Published when an entity is referenced in a session.

    Attributes:
        session_id: Session identifier
        entity_type: Type of entity
        entity_id: Entity identifier
        label: Human-readable entity name
    """
    category: str = field(default="event", init=False)
    session_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    label: str = ""


@dataclass(frozen=True)
class ClarificationRequested:
    """Published when clarification is needed.

    Attributes:
        session_id: Session identifier
        question: Clarification question
        original_request: Original user request
        options: Suggested answer options
    """
    category: str = field(default="event", init=False)
    session_id: str = ""
    question: str = ""
    original_request: str = ""
    options: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class ClarificationResolved:
    """Published when clarification is resolved.

    Attributes:
        session_id: Session identifier
        answer: User's answer
        was_expired: Whether clarification had expired
    """
    category: str = field(default="event", init=False)
    session_id: str = ""
    answer: str = ""
    was_expired: bool = False
