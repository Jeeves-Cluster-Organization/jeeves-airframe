"""CommBus Handler Registration for Memory Module.

Registers handlers for memory queries and commands with the CommBus.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from jeeves_infra.protocols import DatabaseClientProtocol, LoggerProtocol


def register_memory_handlers(
    commbus: Any,
    session_state_service: Any,
    logger: Optional["LoggerProtocol"] = None,
) -> None:
    """Register memory query and command handlers with CommBus.

    Args:
        commbus: The CommBus instance to register handlers with
        session_state_service: SessionStateService instance (required)
        logger: Optional logger instance
    """
    from jeeves_infra.memory.messages import (
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
        service = session_state_service
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
        service = session_state_service
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
        VectorRepository and EmbeddingService which are optional.
        """
        # For now, return empty results - semantic search requires more setup
        return {
            "results": [],
            "total": 0,
            "query": query.query,
            "note": "Semantic search requires VectorRepository configuration",
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
        service = session_state_service
        if service is None:
            return

        await service.clear_session(session_id=command.session_id)

    async def handle_update_focus(command: UpdateFocus) -> None:
        """Handle UpdateFocus command."""
        service = session_state_service
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
        service = session_state_service
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


__all__ = [
    "register_memory_handlers",
]
