"""CommBus Handler Registration for Memory Module.

Registers handlers for memory queries and commands with the CommBus.

Constitutional Reference:
- Memory Module CONSTITUTION P4: Memory operations publish events via CommBus
- Control Tower CONSTITUTION: CommBus communication for service dispatch

Usage:
    from memory_module.handlers import register_memory_handlers

    # In application startup
    register_memory_handlers(
        commbus=commbus,
        session_state_service=session_state_service,
        db=db_client,
    )
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # CommBus is now in Go (commbus/) - Python uses gRPC or protocol interface
    # Using Protocol for type hints during migration
    from typing import Protocol as CommBusProtocol
    from jeeves_infra.protocols import DatabaseClientProtocol, LoggerProtocol
    from jeeves_infra.memory.services.session_state_service import SessionStateService

# Stub type for CommBus during migration (actual implementation is Go)
class InMemoryCommBus:
    """Stub for CommBus - actual implementation is in Go commbus/."""
    def register_handler(self, name: str, handler: Any) -> None: ...


def register_memory_handlers(
    commbus: "InMemoryCommBus",
    session_state_service: Optional["SessionStateService"] = None,
    db: Optional["DatabaseClientProtocol"] = None,
    logger: Optional["LoggerProtocol"] = None,
) -> None:
    """Register memory query and command handlers with CommBus.

    This wires up the memory services to respond to CommBus queries.

    Args:
        commbus: The CommBus instance to register handlers with
        session_state_service: Optional pre-created SessionStateService
        db: Optional database client (used if session_state_service not provided)
        logger: Optional logger instance

    Note:
        Either session_state_service or db must be provided for full functionality.
    """
    from memory_module.messages import (
        GetSessionState,
        SearchMemory,
        GetClarificationContext,
        GetRecentEntities,
        ClearSession,
        UpdateFocus,
        AddEntityReference,
    )

    # =========================================================================
    # Query Handlers
    # =========================================================================

    async def handle_get_session_state(query: GetSessionState) -> Any:
        """Handle GetSessionState query."""
        service = _get_session_service(session_state_service, db, logger)
        if service is None:
            return {"error": "SessionStateService not configured"}

        state = await service.get_or_create(
            session_id=query.session_id,
            user_id=query.user_id,
        )
        return {
            "session_id": state.session_id,
            "user_id": state.user_id,
            "focus": {
                "type": state.focus_type,
                "id": state.focus_id,
                "label": state.focus_label,
                "context": state.focus_context,
            },
            "entities": state.entities,
            "short_term_context": state.short_term_context,
            "created_at": state.created_at.isoformat() if state.created_at else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }

    async def handle_get_recent_entities(query: GetRecentEntities) -> Any:
        """Handle GetRecentEntities query."""
        service = _get_session_service(session_state_service, db, logger)
        if service is None:
            return {"entities": []}

        entities = await service.get_recent_entities(
            session_id=query.session_id,
            limit=query.limit,
        )
        return {"entities": entities}

    async def handle_search_memory(query: SearchMemory) -> Any:
        """Handle SearchMemory query.

        Note: This is a placeholder. Full semantic search requires
        PgVectorRepository and EmbeddingService which are optional.
        """
        # For now, return empty results - semantic search requires more setup
        return {
            "results": [],
            "total": 0,
            "query": query.query,
            "note": "Semantic search requires PgVectorRepository configuration",
        }

    async def handle_get_clarification_context(query: GetClarificationContext) -> Any:
        """Handle GetClarificationContext query.

        Note: Clarification handling is now in InterruptService (Control Tower).
        This returns session-related clarification context if available.
        """
        return {
            "session_id": query.session_id,
            "has_pending": False,
            "note": "Clarification handling is via InterruptService",
        }

    # =========================================================================
    # Command Handlers
    # =========================================================================

    async def handle_clear_session(command: ClearSession) -> None:
        """Handle ClearSession command."""
        service = _get_session_service(session_state_service, db, logger)
        if service is None:
            return

        await service.clear_session(session_id=command.session_id)

    async def handle_update_focus(command: UpdateFocus) -> None:
        """Handle UpdateFocus command."""
        service = _get_session_service(session_state_service, db, logger)
        if service is None:
            return

        await service.update_focus(
            session_id=command.session_id,
            focus_type=command.focus_type,
            focus_id=command.focus_id,
            focus_label=command.focus_label,
            focus_context=command.focus_context,
        )

    async def handle_add_entity_reference(command: AddEntityReference) -> None:
        """Handle AddEntityReference command."""
        service = _get_session_service(session_state_service, db, logger)
        if service is None:
            return

        await service.add_entity_reference(
            session_id=command.session_id,
            entity_type=command.entity_type,
            entity_id=command.entity_id,
            label=command.label,
            context=command.context,
        )

    # =========================================================================
    # Register Handlers
    # =========================================================================

    # Queries
    commbus.register_handler("GetSessionState", handle_get_session_state)
    commbus.register_handler("GetRecentEntities", handle_get_recent_entities)
    commbus.register_handler("SearchMemory", handle_search_memory)
    commbus.register_handler("GetClarificationContext", handle_get_clarification_context)

    # Commands
    commbus.register_handler("ClearSession", handle_clear_session)
    commbus.register_handler("UpdateFocus", handle_update_focus)
    commbus.register_handler("AddEntityReference", handle_add_entity_reference)


# Cache for lazy-initialized service
_cached_session_service: Optional["SessionStateService"] = None


def _get_session_service(
    provided: Optional["SessionStateService"],
    db: Optional["DatabaseClientProtocol"],
    logger: Optional["LoggerProtocol"],
) -> Optional["SessionStateService"]:
    """Get or create SessionStateService."""
    global _cached_session_service

    if provided is not None:
        return provided

    if _cached_session_service is not None:
        return _cached_session_service

    if db is not None:
        from jeeves_infra.memory.services.session_state_service import SessionStateService
        _cached_session_service = SessionStateService(db=db, logger=logger)
        return _cached_session_service

    return None


def reset_cached_services() -> None:
    """Reset cached services (for testing)."""
    global _cached_session_service
    _cached_session_service = None


__all__ = [
    "register_memory_handlers",
    "reset_cached_services",
]
