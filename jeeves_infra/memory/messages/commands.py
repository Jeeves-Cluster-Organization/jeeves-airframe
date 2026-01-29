"""Memory Commands - Imperative operations on memory.

These commands can be sent via CommBus to modify memory state.
They differ from queries in that they cause side effects.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ClearSession:
    """Command to clear session state.

    Attributes:
        session_id: Session to clear
    """
    category: str = field(default="command", init=False)
    session_id: str = ""


@dataclass(frozen=True)
class InvalidateMemoryCache:
    """Command to invalidate memory cache.

    Attributes:
        user_id: Optional user ID (None = all users)
        layer: Optional layer (None = all layers)
    """
    category: str = field(default="command", init=False)
    user_id: Optional[str] = None
    layer: Optional[str] = None


@dataclass(frozen=True)
class UpdateFocus:
    """Command to update session focus.

    Attributes:
        session_id: Session identifier
        focus_type: New focus type
        focus_id: Optional focus target ID
        focus_label: Human-readable focus description
        focus_context: Additional context data
    """
    category: str = field(default="command", init=False)
    session_id: str = ""
    focus_type: str = ""
    focus_id: Optional[str] = None
    focus_label: Optional[str] = None
    focus_context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AddEntityReference:
    """Command to add an entity reference to a session.

    Attributes:
        session_id: Session identifier
        entity_type: Type of entity
        entity_id: Entity identifier
        label: Human-readable entity name
        context: Reference context
    """
    category: str = field(default="command", init=False)
    session_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    label: str = ""
    context: str = ""
