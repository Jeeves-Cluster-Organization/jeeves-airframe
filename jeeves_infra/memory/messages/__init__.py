"""Memory CommBus Messages.

This module defines memory-specific events, queries, and commands
for communication via jeeves_commbus.

Memory Module Audit (2025-12-09):
- Created as part of memory centralization
- All memory operations can publish events
- Enables event-driven memory updates
"""

from memory_module.messages.events import (
    MemoryStored,
    MemoryRetrieved,
    MemoryDeleted,
    SessionStateChanged,
    FocusChanged,
    EntityReferenced,
    ClarificationRequested,
    ClarificationResolved,
)

from memory_module.messages.queries import (
    GetSessionState,
    SearchMemory,
    GetClarificationContext,
    GetRecentEntities,
)

from memory_module.messages.commands import (
    ClearSession,
    InvalidateMemoryCache,
    UpdateFocus,
    AddEntityReference,
)

__all__ = [
    # Events
    "MemoryStored",
    "MemoryRetrieved",
    "MemoryDeleted",
    "SessionStateChanged",
    "FocusChanged",
    "EntityReferenced",
    "ClarificationRequested",
    "ClarificationResolved",
    # Queries
    "GetSessionState",
    "SearchMemory",
    "GetClarificationContext",
    "GetRecentEntities",
    # Commands
    "ClearSession",
    "InvalidateMemoryCache",
    "UpdateFocus",
    "AddEntityReference",
]
