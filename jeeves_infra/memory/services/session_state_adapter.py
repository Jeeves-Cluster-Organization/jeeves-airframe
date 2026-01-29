"""Session State Adapter - Bridge Avionics to Core Protocol.

This adapter implements Core's SessionStateProtocol using the existing
avionics SessionStateService as the backend. It provides the translation
layer between:
- Core's WorkingMemory (domain-agnostic)
- Avionics' SessionState (infrastructure-specific)

Architectural Pattern:
- Core defines the protocol (what)
- Avionics provides the implementation (how)
- This adapter bridges them (translation)
"""

from typing import Optional, List
from datetime import datetime, timezone

from jeeves_infra.protocols import (
    WorkingMemory,
    FocusState,
    FocusType,
    EntityRef,
    ClarificationContext,
)
from jeeves_infra.protocols import SessionStateProtocol
from jeeves_infra.protocols import LoggerProtocol

from jeeves_infra.memory.services.session_state_service import SessionStateService
from jeeves_infra.memory.repositories.session_state_repository import SessionState
from shared import get_component_logger, parse_datetime
from jeeves_infra.protocols import DatabaseClientProtocol


class SessionStateAdapter:
    """Adapter implementing Core's SessionStateProtocol.

    This bridges the gap between Core's domain-agnostic WorkingMemory
    and Avionics' infrastructure-specific SessionState.

    Usage:
        adapter = SessionStateAdapter(db, service)
        memory = await adapter.get_or_create(session_id, user_id)
        # memory is a WorkingMemory instance

    The adapter handles:
    1. Converting SessionState <-> WorkingMemory
    2. Mapping focus types between the two representations
    3. Translating entity references
    4. Managing clarification state
    """

    def __init__(
        self,
        db: DatabaseClientProtocol,
        service: Optional[SessionStateService] = None,
        logger: Optional[LoggerProtocol] = None
    ):
        """Initialize adapter.

        Args:
            db: Database client instance
            service: Optional pre-configured SessionStateService
            logger: Optional logger instance
        """
        self._service = service or SessionStateService(db)
        self._logger = get_component_logger("SessionStateAdapter", logger)

    # ════════════════════════════════════════════════════════════════════════
    # SessionStateProtocol Implementation
    # ════════════════════════════════════════════════════════════════════════

    async def get_or_create(
        self,
        session_id: str,
        user_id: str
    ) -> WorkingMemory:
        """Get existing session state or create new.

        Args:
            session_id: Session identifier
            user_id: User identifier

        Returns:
            WorkingMemory instance
        """
        state = await self._service.get_or_create(session_id, user_id)
        return self._session_state_to_working_memory(state)

    async def save(
        self,
        session_id: str,
        state: WorkingMemory
    ) -> bool:
        """Save session state.

        This converts WorkingMemory back to SessionState and persists it.

        Args:
            session_id: Session identifier
            state: WorkingMemory to save

        Returns:
            True if saved successfully
        """
        try:
            # Convert WorkingMemory to SessionState
            session_state = self._working_memory_to_session_state(state)

            # Use repository directly for full update
            await self._service.repository.upsert(session_state)

            self._logger.debug(
                "session_state_saved",
                session_id=session_id
            )
            return True

        except Exception as e:
            self._logger.error(
                "session_state_save_failed",
                session_id=session_id,
                error=str(e)
            )
            return False

    async def delete(
        self,
        session_id: str
    ) -> bool:
        """Delete session state.

        Args:
            session_id: Session to delete

        Returns:
            True if deleted, False if not found
        """
        return await self._service.delete(session_id)

    async def update_focus(
        self,
        session_id: str,
        focus: FocusState
    ) -> bool:
        """Update just the focus state.

        Args:
            session_id: Session identifier
            focus: New focus state

        Returns:
            True if updated successfully
        """
        result = await self._service.update_focus(
            session_id=session_id,
            focus_type=self._core_focus_to_avionics(focus.focus_type),
            focus_id=focus.focus_id,
            focus_context=focus.focus_context
        )
        return result is not None

    async def add_entity_reference(
        self,
        session_id: str,
        entity: EntityRef
    ) -> bool:
        """Add an entity reference to session.

        Args:
            session_id: Session identifier
            entity: Entity reference to add

        Returns:
            True if added successfully
        """
        result = await self._service.record_entity_reference(
            session_id=session_id,
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            entity_title=entity.label
        )
        return result is not None

    async def save_clarification(
        self,
        session_id: str,
        clarification: ClarificationContext
    ) -> bool:
        """Save pending clarification.

        Args:
            session_id: Session identifier
            clarification: Clarification context

        Returns:
            True if saved successfully
        """
        clarification_dict = {
            "original_request": clarification.original_request,
            "clarification_question": clarification.question,
            "execution_context": clarification.execution_snapshot,
            "options": clarification.options,
            "clarification_type": clarification.clarification_type,
            "created_at": clarification.created_at.isoformat(),
            "expires_at": clarification.expires_at.isoformat(),
        }
        return await self._service.save_clarification(session_id, clarification_dict)

    async def get_clarification(
        self,
        session_id: str
    ) -> Optional[ClarificationContext]:
        """Get pending clarification if any.

        Args:
            session_id: Session identifier

        Returns:
            ClarificationContext if pending, None otherwise
        """
        clarification_dict = await self._service.get_clarification(session_id)
        if not clarification_dict:
            return None

        return self._dict_to_clarification(clarification_dict)

    async def clear_clarification(
        self,
        session_id: str
    ) -> bool:
        """Clear pending clarification.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared
        """
        return await self._service.clear_clarification(session_id)

    async def get_active_sessions(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[str]:
        """Get active session IDs for a user.

        Args:
            user_id: User identifier
            limit: Maximum sessions to return

        Returns:
            List of session IDs
        """
        # This requires querying the repository directly
        # Using the db client to get active sessions
        try:
            rows = await self._service.repository.db.fetch_all(
                """
                SELECT session_id
                FROM session_states
                WHERE user_id = :user_id
                ORDER BY updated_at DESC
                LIMIT :limit
                """,
                {"user_id": user_id, "limit": limit}
            )
            return [row["session_id"] for row in rows]
        except Exception as e:
            self._logger.error(
                "get_active_sessions_failed",
                user_id=user_id,
                error=str(e)
            )
            return []

    # ════════════════════════════════════════════════════════════════════════
    # Conversion Methods
    # ════════════════════════════════════════════════════════════════════════

    def _session_state_to_working_memory(self, state: SessionState) -> WorkingMemory:
        """Convert Avionics SessionState to Core WorkingMemory.

        Args:
            state: Avionics SessionState

        Returns:
            Core WorkingMemory
        """
        # Convert focus
        focus = FocusState(
            focus_type=self._avionics_focus_to_core(state.focus_type),
            focus_id=state.focus_id,
            focus_label=state.focus_context.get("label") if state.focus_context else None,
            focus_context=state.focus_context or {},
        )

        # Convert entity references
        entity_refs = []
        if state.referenced_entities:
            for ref in state.referenced_entities:
                entity_refs.append(EntityRef(
                    entity_type=ref.get("entity_type", "unknown"),
                    entity_id=ref.get("entity_id", ""),
                    label=ref.get("entity_title", ref.get("entity_id", "")),
                    reference_context=ref.get("context", ""),
                ))

        return WorkingMemory(
            session_id=state.session_id,
            user_id=state.user_id,
            focus=focus,
            referenced_entities=entity_refs,
            turn_count=state.turn_count,
            short_term_context=state.short_term_memory or "",
            created_at=state.created_at or datetime.now(timezone.utc),
            last_updated=state.updated_at or datetime.now(timezone.utc),
        )

    def _working_memory_to_session_state(self, memory: WorkingMemory) -> SessionState:
        """Convert Core WorkingMemory to Avionics SessionState.

        Args:
            memory: Core WorkingMemory

        Returns:
            Avionics SessionState
        """
        # Convert entity references
        referenced_entities = []
        for ref in memory.referenced_entities:
            referenced_entities.append({
                "entity_type": ref.entity_type,
                "entity_id": ref.entity_id,
                "entity_title": ref.label,
                "context": ref.reference_context,
                "referenced_at": ref.referenced_at.isoformat(),
            })

        # Build focus context
        focus_context = memory.focus.focus_context.copy()
        if memory.focus.focus_label:
            focus_context["label"] = memory.focus.focus_label

        return SessionState(
            session_id=memory.session_id,
            user_id=memory.user_id,
            focus_type=self._core_focus_to_avionics(memory.focus.focus_type),
            focus_id=memory.focus.focus_id,
            focus_context=focus_context,
            turn_count=memory.turn_count,
            referenced_entities=referenced_entities,
            short_term_memory=memory.short_term_context,
            created_at=memory.created_at,
            updated_at=memory.last_updated,
        )

    def _avionics_focus_to_core(self, focus_type: Optional[str]) -> FocusType:
        """Convert Avionics focus type string to Core FocusType enum.

        Args:
            focus_type: Avionics focus type string

        Returns:
            Core FocusType enum
        """
        if not focus_type or focus_type == "general":
            return FocusType.GENERAL
        if focus_type == "task":
            return FocusType.TASK
        if focus_type in ("exploration", "exploring"):
            return FocusType.EXPLORATION
        if focus_type in ("entity", "journal", "fact", "message"):
            return FocusType.ENTITY
        if focus_type == "clarification":
            return FocusType.CLARIFICATION
        # Default to general for unknown types
        return FocusType.GENERAL

    def _core_focus_to_avionics(self, focus_type: FocusType) -> str:
        """Convert Core FocusType enum to Avionics focus type string.

        Args:
            focus_type: Core FocusType enum

        Returns:
            Avionics focus type string
        """
        mapping = {
            FocusType.GENERAL: "general",
            FocusType.TASK: "task",
            FocusType.EXPLORATION: "exploration",
            FocusType.ENTITY: "entity",
            FocusType.CLARIFICATION: "clarification",
        }
        return mapping.get(focus_type, "general")

    def _dict_to_clarification(self, data: dict) -> ClarificationContext:
        """Convert clarification dict to ClarificationContext.

        Args:
            data: Clarification dict from storage

        Returns:
            ClarificationContext instance
        """
        created_at = parse_datetime(data.get("created_at"))
        expires_at = parse_datetime(data.get("expires_at"))

        return ClarificationContext(
            question=data.get("clarification_question", ""),
            original_request=data.get("original_request", ""),
            execution_snapshot=data.get("execution_context", {}),
            options=data.get("options", []),
            clarification_type=data.get("clarification_type", "general"),
            created_at=created_at or datetime.now(timezone.utc),
            expires_at=expires_at or datetime.now(timezone.utc),
        )
