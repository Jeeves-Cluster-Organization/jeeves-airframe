"""
Session State Service for L4 Working Memory.

High-level service for managing session state, providing:
- Session lifecycle management
- Focus tracking across conversations
- Entity reference management
- Short-term memory coordination with summarization

Constitutional Alignment:
- P1: Uses LLM for context understanding (via SummarizationService)
- P5: Deterministic spine with clear state transitions
- M5: Always uses repository abstraction
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
import json

from jeeves_infra.logging import get_component_logger
from jeeves_infra.utils.datetime import parse_datetime
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol
from jeeves_infra.memory.repositories.session_state_repository import (
    SessionStateRepository,
    SessionState
)



class SessionStateService:
    """
    Service for managing session state.

    Provides high-level operations for:
    - Creating and managing session contexts
    - Tracking conversation focus
    - Managing entity references
    - Coordinating with summarization for memory compression
    """

    def __init__(
        self,
        db: DatabaseClientProtocol,
        repository: Optional[SessionStateRepository] = None,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize service.

        Args:
            db: Database client instance
            repository: Optional pre-configured repository (for testing)
            logger: Optional logger instance (ADR-001 DI)
        """
        self.db = db
        self.repository = repository or SessionStateRepository(db)
        self._logger = get_component_logger("SessionStateService", logger)

    async def ensure_initialized(self) -> None:
        """Ensure the repository table exists."""
        await self.repository.ensure_table()

    async def get_or_create(
        self,
        session_id: str,
        user_id: str
    ) -> SessionState:
        """
        Get existing session state or create a new one.

        Args:
            session_id: Session identifier
            user_id: User identifier

        Returns:
            SessionState (existing or newly created)
        """
        existing = await self.repository.get(session_id)
        if existing:
            return existing

        # Create new session state
        new_state = SessionState(
            session_id=session_id,
            user_id=user_id,
            focus_type="general",
            turn_count=0
        )

        await self.repository.upsert(new_state)

        self._logger.info(
            "session_state_created",
            session_id=session_id,
            user_id=user_id
        )

        return new_state

    async def get(self, session_id: str) -> Optional[SessionState]:
        """
        Get session state by ID.

        Args:
            session_id: Session identifier

        Returns:
            SessionState or None if not found
        """
        return await self.repository.get(session_id)

    async def update_focus(
        self,
        session_id: str,
        focus_type: str,
        focus_id: Optional[str] = None,
        focus_context: Optional[Dict[str, Any]] = None
    ) -> Optional[SessionState]:
        """
        Update the current focus of a session.

        Used when the conversation shifts to a specific topic or entity.

        Args:
            session_id: Session identifier
            focus_type: Type of focus ('task', 'journal', 'planning', 'general')
            focus_id: ID of focused entity if applicable
            focus_context: Additional context about the focus

        Returns:
            Updated SessionState or None if session not found
        """
        result = await self.repository.update_focus(
            session_id=session_id,
            focus_type=focus_type,
            focus_id=focus_id,
            focus_context=focus_context
        )

        if result:
            self._logger.info(
                "session_focus_updated",
                session_id=session_id,
                focus_type=focus_type,
                focus_id=focus_id
            )

        return result

    async def record_entity_reference(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        entity_title: Optional[str] = None
    ) -> Optional[SessionState]:
        """
        Record that an entity was referenced in the conversation.

        Used to track what tasks, journal entries, etc. have been
        discussed in this session for context awareness.

        Args:
            session_id: Session identifier
            entity_type: Type of entity ('task', 'journal', 'fact', etc.)
            entity_id: Entity identifier
            entity_title: Human-readable title (optional)

        Returns:
            Updated SessionState or None if session not found
        """
        return await self.repository.add_referenced_entity(
            session_id=session_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_title=entity_title
        )

    async def on_user_turn(
        self,
        session_id: str,
        user_message: str
    ) -> Optional[SessionState]:
        """
        Handle a new user message (increment turn counter).

        Called at the start of each user interaction.

        Args:
            session_id: Session identifier
            user_message: The user's message (for potential analysis)

        Returns:
            Updated SessionState or None if session not found
        """
        return await self.repository.increment_turn(session_id)

    async def update_memory(
        self,
        session_id: str,
        memory_summary: str
    ) -> Optional[SessionState]:
        """
        Update the short-term memory summary.

        Called after summarization service compresses recent context.

        Args:
            session_id: Session identifier
            memory_summary: Compressed summary of recent conversation

        Returns:
            Updated SessionState or None if session not found
        """
        return await self.repository.update_short_term_memory(
            session_id=session_id,
            memory=memory_summary
        )

    async def get_context_for_prompt(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Get session context formatted for LLM prompts.

        Returns a structured context dictionary that can be included
        in agent prompts for context awareness.

        Args:
            session_id: Session identifier

        Returns:
            Dictionary with session context for prompts
        """
        state = await self.repository.get(session_id)
        if not state:
            return {}

        context = {
            "turn_count": state.turn_count,
            "focus": {
                "type": state.focus_type,
                "id": state.focus_id,
                "context": state.focus_context
            } if state.focus_type else None,
        }

        # Add recent entity references
        if state.referenced_entities:
            context["recent_entities"] = state.referenced_entities[-5:]  # Last 5

        # Add short-term memory if available
        if state.short_term_memory:
            context["conversation_summary"] = state.short_term_memory

        return context

    async def clear_focus(self, session_id: str) -> Optional[SessionState]:
        """
        Clear the current focus (return to general mode).

        Args:
            session_id: Session identifier

        Returns:
            Updated SessionState or None if session not found
        """
        return await self.repository.update_focus(
            session_id=session_id,
            focus_type="general",
            focus_id=None,
            focus_context={}
        )

    async def delete(self, session_id: str) -> bool:
        """
        Delete session state.

        Called when a session is terminated or cleaned up.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not found
        """
        return await self.repository.delete(session_id)

    async def should_summarize(
        self,
        session_id: str,
        summarize_every_n_turns: int = 5
    ) -> bool:
        """
        Check if the session should trigger summarization.

        Args:
            session_id: Session identifier
            summarize_every_n_turns: Summarize after this many turns

        Returns:
            True if summarization should be triggered
        """
        state = await self.repository.get(session_id)
        if not state:
            return False

        # Summarize every N turns
        return state.turn_count > 0 and state.turn_count % summarize_every_n_turns == 0

"""
REMOVED: Clarification and Critic Decision Methods

These methods have been removed as part of the Unified Interrupt System (v4.0):
- save_clarification()
- get_clarification()
- clear_clarification()
- is_clarification_expired()
- get_clarification_context_for_prompt()
- save_critic_decision()
- get_critic_decisions()

These methods are no longer needed - interrupt handling is done at the kernel level.
"""
