"""Memory Queries - Request/Response patterns for memory operations.

These queries can be sent via CommBus to retrieve memory data.
Handlers in the memory module process these and return responses.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GetSessionState:
    """Query for session working memory.

    Attributes:
        session_id: Session identifier
        user_id: User identifier

    Returns:
        WorkingMemory instance
    """
    category: str = field(default="query", init=False)
    session_id: str = ""
    user_id: str = ""


@dataclass(frozen=True)
class SearchMemory:
    """Query for memory search.

    Attributes:
        query: Search query string
        layer: Optional layer to search (None = all)
        user_id: Optional owner filter
        limit: Maximum results to return
        filters: Additional search filters

    Returns:
        List[SearchResult]
    """
    category: str = field(default="query", init=False)
    query: str = ""
    layer: Optional[str] = None
    user_id: Optional[str] = None
    limit: int = 10
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GetClarificationContext:
    """Query for pending clarification.

    Attributes:
        session_id: Session identifier

    Returns:
        Optional[ClarificationContext]
    """
    category: str = field(default="query", init=False)
    session_id: str = ""


@dataclass(frozen=True)
class GetRecentEntities:
    """Query for recently referenced entities.

    Attributes:
        session_id: Session identifier
        limit: Maximum entities to return

    Returns:
        List[EntityRef]
    """
    category: str = field(default="query", init=False)
    session_id: str = ""
    limit: int = 10
