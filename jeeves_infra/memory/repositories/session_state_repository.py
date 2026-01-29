"""
Session State Repository for L4 Working Memory.

Provides hot-path storage for active session context including:
- Current conversation focus
- Active entities referenced
- Short-term working memory
- Session-level summaries

Constitutional Alignment:
- M2: Append-only with soft-delete semantics
- M4: Structured JSONB for payload flexibility
- M5: Always passes through database client abstraction
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
import json

from shared import get_component_logger, parse_datetime
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


class SessionState:
    """Represents the current state of a user session.

    Session state includes:
    - Focus context (what the user is currently working on)
    - Referenced entities (tasks, journal entries, etc.)
    - Short-term memory (recent conversation summary)
    - Session metadata
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        focus_type: Optional[str] = None,
        focus_id: Optional[str] = None,
        focus_context: Optional[Dict[str, Any]] = None,
        referenced_entities: Optional[List[Dict[str, str]]] = None,
        short_term_memory: Optional[str] = None,
        turn_count: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ):
        """
        Initialize session state.

        Args:
            session_id: Session identifier
            user_id: User identifier
            focus_type: Type of current focus ('task', 'journal', 'general', etc.)
            focus_id: ID of focused entity if applicable
            focus_context: Additional context about the focus
            referenced_entities: List of entities referenced in session
                                 [{'type': 'task', 'id': 'xxx', 'title': 'yyy'}]
            short_term_memory: Compressed summary of recent conversation
            turn_count: Number of conversation turns in this session
            created_at: When the session state was created
            updated_at: When the session state was last updated
        """
        self.session_id = session_id
        self.user_id = user_id
        self.focus_type = focus_type
        self.focus_id = focus_id
        self.focus_context = focus_context or {}
        self.referenced_entities = referenced_entities or []
        self.short_term_memory = short_term_memory
        self.turn_count = turn_count
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "focus_type": self.focus_type,
            "focus_id": self.focus_id,
            "focus_context": self.focus_context,
            "referenced_entities": self.referenced_entities,
            "short_term_memory": self.short_term_memory,
            "turn_count": self.turn_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Create from dictionary."""
        created_at = parse_datetime(data.get("created_at"))
        updated_at = parse_datetime(data.get("updated_at"))

        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            focus_type=data.get("focus_type"),
            focus_id=data.get("focus_id"),
            focus_context=data.get("focus_context"),
            referenced_entities=data.get("referenced_entities"),
            short_term_memory=data.get("short_term_memory"),
            turn_count=data.get("turn_count", 0),
            created_at=created_at,
            updated_at=updated_at
        )


class SessionStateRepository:
    """
    Repository for session state persistence.

    Manages hot-path session context for L4 Working Memory layer.
    Uses upsert semantics for state updates.
    """

    # Note: This SQL should match postgres_schema.sql
    # The authoritative schema is in postgres_schema.sql
    CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS session_state (
            session_id UUID PRIMARY KEY,
            user_id TEXT NOT NULL,
            focus_type TEXT,
            focus_id TEXT,
            focus_context TEXT,
            referenced_entities TEXT,
            short_term_memory TEXT,
            turn_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """

    CREATE_INDEX_SQL = """
        CREATE INDEX IF NOT EXISTS idx_session_state_user ON session_state(user_id)
    """

    def __init__(self, db: DatabaseClientProtocol, logger: Optional[LoggerProtocol] = None):
        """
        Initialize repository.

        Args:
            db: Database client instance (DatabaseClient or PostgreSQLClient)
            logger: Optional logger instance
        """
        self._logger = get_component_logger("SessionStateRepository", logger)
        self.db = db

    async def ensure_table(self) -> None:
        """Ensure the session_state table exists."""
        await self.db.execute(self.CREATE_TABLE_SQL)
        await self.db.execute(self.CREATE_INDEX_SQL)

    async def get(self, session_id: str) -> Optional[SessionState]:
        """
        Get session state by session ID.

        Args:
            session_id: Session identifier

        Returns:
            SessionState if found, None otherwise
        """
        query = """
            SELECT session_id, user_id, focus_type, focus_id,
                   focus_context, referenced_entities, short_term_memory,
                   turn_count, created_at, updated_at
            FROM session_state
            WHERE session_id = ?
        """

        row = await self.db.fetch_one(query, (session_id,))
        if not row:
            return None

        return self._row_to_session_state(row)

    async def upsert(self, state: SessionState) -> SessionState:
        """
        Insert or update session state.

        Args:
            state: SessionState to save

        Returns:
            Updated SessionState
        """
        state.updated_at = datetime.now(timezone.utc)

        query = """
            INSERT INTO session_state
            (session_id, user_id, focus_type, focus_id, focus_context,
             referenced_entities, short_term_memory, turn_count,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (session_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                focus_type = EXCLUDED.focus_type,
                focus_id = EXCLUDED.focus_id,
                focus_context = EXCLUDED.focus_context,
                referenced_entities = EXCLUDED.referenced_entities,
                short_term_memory = EXCLUDED.short_term_memory,
                turn_count = EXCLUDED.turn_count,
                updated_at = EXCLUDED.updated_at
        """

        params = (
            state.session_id,
            state.user_id,
            state.focus_type,
            state.focus_id,
            json.dumps(state.focus_context) if state.focus_context else None,
            json.dumps(state.referenced_entities) if state.referenced_entities else None,
            state.short_term_memory,
            state.turn_count,
            state.created_at,
            state.updated_at
        )

        await self.db.execute(query, params)

        self._logger.debug(
            "session_state_upserted",
            session_id=state.session_id,
            turn_count=state.turn_count
        )

        return state

    async def update_focus(
        self,
        session_id: str,
        focus_type: str,
        focus_id: Optional[str] = None,
        focus_context: Optional[Dict[str, Any]] = None
    ) -> Optional[SessionState]:
        """
        Update the focus of a session.

        Args:
            session_id: Session identifier
            focus_type: New focus type
            focus_id: ID of focused entity (optional)
            focus_context: Additional context (optional)

        Returns:
            Updated SessionState or None if session not found
        """
        state = await self.get(session_id)
        if not state:
            return None

        state.focus_type = focus_type
        state.focus_id = focus_id
        if focus_context:
            state.focus_context = focus_context

        return await self.upsert(state)

    async def add_referenced_entity(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        entity_title: Optional[str] = None
    ) -> Optional[SessionState]:
        """
        Add an entity to the session's referenced entities.

        Args:
            session_id: Session identifier
            entity_type: Type of entity ('task', 'journal', etc.)
            entity_id: Entity identifier
            entity_title: Human-readable title (optional)

        Returns:
            Updated SessionState or None if session not found
        """
        state = await self.get(session_id)
        if not state:
            return None

        # Check if entity already referenced
        for entity in state.referenced_entities:
            if entity.get("type") == entity_type and entity.get("id") == entity_id:
                return state  # Already referenced

        # Add new entity reference
        state.referenced_entities.append({
            "type": entity_type,
            "id": entity_id,
            "title": entity_title,
            "referenced_at": datetime.now(timezone.utc).isoformat()
        })

        # Keep only last 20 references to prevent unbounded growth
        if len(state.referenced_entities) > 20:
            state.referenced_entities = state.referenced_entities[-20:]

        return await self.upsert(state)

    async def increment_turn(self, session_id: str) -> Optional[SessionState]:
        """
        Increment the turn count for a session.

        Args:
            session_id: Session identifier

        Returns:
            Updated SessionState or None if session not found
        """
        state = await self.get(session_id)
        if not state:
            return None

        state.turn_count += 1
        return await self.upsert(state)

    async def update_short_term_memory(
        self,
        session_id: str,
        memory: str
    ) -> Optional[SessionState]:
        """
        Update the short-term memory (conversation summary).

        Args:
            session_id: Session identifier
            memory: Compressed summary of recent conversation

        Returns:
            Updated SessionState or None if session not found
        """
        state = await self.get(session_id)
        if not state:
            return None

        state.short_term_memory = memory
        return await self.upsert(state)

    async def delete(self, session_id: str) -> bool:
        """
        Delete session state.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM session_state WHERE session_id = ?"
        result = await self.db.execute(query, (session_id,))

        # Check if any rows were affected
        deleted = result is not None
        if deleted:
            self._logger.info("session_state_deleted", session_id=session_id)

        return deleted

    async def get_by_user(self, user_id: str) -> List[SessionState]:
        """
        Get all session states for a user.

        Args:
            user_id: User identifier

        Returns:
            List of SessionState objects
        """
        query = """
            SELECT session_id, user_id, focus_type, focus_id,
                   focus_context, referenced_entities, short_term_memory,
                   turn_count, created_at, updated_at
            FROM session_state
            WHERE user_id = ?
            ORDER BY updated_at DESC
        """

        rows = await self.db.fetch_all(query, (user_id,))
        return [self._row_to_session_state(row) for row in rows]

    def _row_to_session_state(self, row: Dict[str, Any]) -> SessionState:
        """Convert a database row to SessionState."""
        from uuid import UUID

        # Parse JSON fields
        focus_context = row.get("focus_context")
        if isinstance(focus_context, str):
            focus_context = json.loads(focus_context) if focus_context else {}

        referenced_entities = row.get("referenced_entities")
        if isinstance(referenced_entities, str):
            referenced_entities = json.loads(referenced_entities) if referenced_entities else []

        # Parse timestamps
        created_at = parse_datetime(row.get("created_at"))
        updated_at = parse_datetime(row.get("updated_at"))

        # Convert UUID objects to strings (PostgreSQL returns native UUID objects)
        session_id = row["session_id"]
        if isinstance(session_id, UUID):
            session_id = str(session_id)

        user_id = row["user_id"]
        if isinstance(user_id, UUID):
            user_id = str(user_id)

        return SessionState(
            session_id=session_id,
            user_id=user_id,
            focus_type=row.get("focus_type"),
            focus_id=row.get("focus_id"),
            focus_context=focus_context,
            referenced_entities=referenced_entities,
            short_term_memory=row.get("short_term_memory"),
            turn_count=row.get("turn_count", 0),
            created_at=created_at,
            updated_at=updated_at
        )
