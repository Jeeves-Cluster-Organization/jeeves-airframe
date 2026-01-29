"""
ChatService: Centralized chat operations with WebSocket event broadcasting.

This service provides session and message management for the chat UI,
following the same patterns as TaskService for consistency.

Key Features:
- Session CRUD operations (create, list, update, delete)
- Message retrieval with pagination
- Soft delete support for sessions and messages
- WebSocket event broadcasting for real-time UI updates
- Full-text search across messages
- Export functionality for sessions
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from jeeves_infra.database.client import DatabaseClientProtocol
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol


@dataclass
class ChatMutationLock:
    """Asyncio lock manager for chat operations."""

    _locks: Dict[str, asyncio.Lock] = field(default_factory=dict)

    @asynccontextmanager
    async def acquire(self, user_id: str, resource_id: Optional[str] = None):
        """Acquire lock for a specific resource or user-wide lock."""
        key = f"{user_id}:{resource_id or '*'}"

        # Get or create lock for this key
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        lock = self._locks[key]

        # Acquire lock
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()


class ChatService:
    """
    Centralized chat operations service.

    All chat operations (session/message CRUD) go through this service
    to ensure consistency and proper event broadcasting.
    """

    def __init__(
        self,
        db: DatabaseClientProtocol,
        event_manager: Optional[Any] = None,
        logger: Optional[LoggerProtocol] = None,
    ):
        """
        Initialize ChatService.

        Args:
            db: Database client for persistence
            event_manager: WebSocketEventManager for broadcasting events (optional)
            logger: Optional logger instance
        """
        self._logger = logger or get_current_logger()
        self.db = db
        self.event_manager = event_manager
        self.lock = ChatMutationLock()
        self.logger = self._logger.bind(component="chat_service")
        try:
            from jeeves_infra.postgres.client import PostgreSQLClient
            self.is_postgres = isinstance(db, PostgreSQLClient)
        except Exception:
            self.is_postgres = hasattr(db, "database_url")

    # =========================================================================
    # SESSION OPERATIONS
    # =========================================================================

    async def create_session(
        self, user_id: str, title: Optional[str] = None, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new chat session.

        Args:
            user_id: User ID
            title: Optional session title (auto-generated if not provided)
            session_id: Optional session ID (generated if not provided)

        Returns:
            Created session with session_id and metadata
        """
        sid = session_id or str(uuid4())
        now = datetime.now(timezone.utc)

        session_data = {
            "session_id": sid,
            "user_id": user_id,
            "title": title,
            "message_count": 0,
            "created_at": now,
            "last_activity": now,
        }

        async with self.lock.acquire(user_id):
            await self.db.insert("sessions", session_data)

            self.logger.info(
                "chat_session_created",
                session_id=sid,
                user_id=user_id,
                title=title,
            )

        prepared = self._prepare_session_payload(session_data)

        # Broadcast event
        await self._broadcast(
            "chat.session.created",
            {
                "session_id": sid,
                "user_id": user_id,
                "session": prepared,
                "timestamp": now.isoformat(),
            },
        )

        return prepared

    async def list_sessions(
        self,
        user_id: str,
        filter: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List chat sessions for a user (read-only from requests table).

        NOTE: This queries the orchestrator's requests table for session history.
        Sessions are read-only; continuing conversations in same session not yet supported.

        Args:
            user_id: User ID
            filter: Time filter (today, week, month, all)
            include_deleted: Whether to include soft-deleted sessions
            limit: Maximum number of sessions
            offset: Pagination offset

        Returns:
            List of sessions sorted by last_activity DESC
        """
        # Query sessions from the orchestrator's sessions table with message counts from requests
        if self.is_postgres:
            query = """
                SELECT
                    s.session_id,
                    s.user_id,
                    s.title,
                    s.created_at,
                    s.last_activity,
                    s.deleted_at,
                    s.archived_at,
                    COALESCE(COUNT(r.request_id), 0) AS message_count,
                    COALESCE(MAX(r.received_at), s.created_at) AS last_message_at
                FROM sessions s
                LEFT JOIN requests r ON s.session_id = r.session_id
                WHERE s.user_id = :user_id
            """
            params: Dict[str, Any] = {"user_id": user_id, "limit": limit, "offset": offset}

            if not include_deleted:
                query += " AND s.deleted_at IS NULL"

            if filter == "today":
                query += " AND s.last_activity::date = CURRENT_DATE"
            elif filter == "week":
                query += " AND s.last_activity >= NOW() - INTERVAL '7 days'"
            elif filter == "month":
                query += " AND s.last_activity >= NOW() - INTERVAL '30 days'"

            query += """
                GROUP BY s.session_id, s.user_id, s.title, s.created_at, s.last_activity, s.deleted_at, s.archived_at
                ORDER BY last_message_at DESC
                LIMIT :limit OFFSET :offset
            """

            sessions = await self.db.fetch_all(query, params)
        else:
            query = """
                SELECT
                    s.session_id,
                    s.user_id,
                    s.title,
                    s.created_at,
                    s.last_activity,
                    s.deleted_at,
                    s.archived_at,
                    COALESCE(COUNT(r.request_id), 0) as message_count,
                    COALESCE(MAX(r.received_at), s.created_at) as last_message_at
                FROM sessions s
                LEFT JOIN requests r ON s.session_id = r.session_id
                WHERE s.user_id = ?
            """
            params = [user_id]

            # Filter deleted sessions unless requested
            if not include_deleted:
                query += " AND s.deleted_at IS NULL"

            # Apply time filter
            if filter == "today":
                query += " AND date(s.last_activity) = date('now')"
            elif filter == "week":
                query += " AND s.last_activity >= datetime('now', '-7 days')"
            elif filter == "month":
                query += " AND s.last_activity >= datetime('now', '-30 days')"

            query += """
                GROUP BY s.session_id
                ORDER BY last_message_at DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            sessions = await self.db.fetch_all(query, tuple(params))

        # Format sessions, auto-generating titles only if not set
        result = []
        for session in sessions:
            # Use existing title if set, otherwise auto-generate from first message
            title = session.get("title")

            if not title:
                # Get first request to generate title
                first_request = await self.db.fetch_one(
                    """SELECT user_message FROM requests
                       WHERE session_id = ?
                       ORDER BY received_at ASC LIMIT 1""",
                    (session["session_id"],)
                )

                if first_request and first_request["user_message"]:
                    # Use first 50 chars of first message as title
                    msg = first_request["user_message"]
                    title = msg[:50] + "..." if len(msg) > 50 else msg
                else:
                    title = "Untitled Chat"

            prepared = self._prepare_session_payload({
                "session_id": session["session_id"],
                "user_id": session["user_id"],
                "title": title,
                "message_count": session["message_count"],
                "created_at": session["created_at"],
                "last_activity": session["last_message_at"],
                "deleted_at": session.get("deleted_at"),
                "archived_at": session.get("archived_at")
            })

            result.append(prepared)

        return result

    async def get_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get a single session by ID.

        Args:
            session_id: Session ID
            user_id: User ID (for access control)

        Returns:
            Session data

        Raises:
            ValueError: If session not found or access denied
        """
        session = await self.db.fetch_one(
            "SELECT * FROM sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )

        if not session:
            raise ValueError(f"Session {session_id} not found or access denied")

        return self._prepare_session_payload(session)

    async def update_session(
        self, session_id: str, user_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a session (e.g., rename, archive).

        Args:
            session_id: Session ID
            user_id: User ID (for access control)
            updates: Fields to update (title, archived_at, etc.)

        Returns:
            Updated session data

        Raises:
            ValueError: If session not found or access denied
        """
        async with self.lock.acquire(user_id, session_id):
            # Verify session exists
            session = await self.db.fetch_one(
                "SELECT * FROM sessions WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            )

            if not session:
                raise ValueError(f"Session {session_id} not found or access denied")

            # Apply updates
            update_data = {}
            if "title" in updates:
                update_data["title"] = updates["title"]
            if "archived_at" in updates:
                update_data["archived_at"] = updates["archived_at"]

            update_data["last_activity"] = datetime.now(timezone.utc)

            await self.db.update("sessions", update_data, "session_id = ?", (session_id,))

            self.logger.info(
                "chat_session_updated",
                session_id=session_id,
                user_id=user_id,
                fields=list(update_data.keys()),
            )

        # Fetch updated session
        updated = await self.db.fetch_one(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )

        prepared = self._prepare_session_payload(updated)

        # Broadcast event
        await self._broadcast(
            "chat.session.updated",
            {
                "session_id": session_id,
                "user_id": user_id,
                "session": prepared,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return prepared

    async def delete_session(
        self, session_id: str, user_id: str, soft: bool = True
    ) -> Dict[str, Any]:
        """
        Delete a session (soft delete by default).

        Args:
            session_id: Session ID
            user_id: User ID (for access control)
            soft: If True, set deleted_at. If False, hard delete.

        Returns:
            Result dict with deleted: true
        """
        async with self.lock.acquire(user_id, session_id):
            # Verify session exists
            session = await self.db.fetch_one(
                "SELECT * FROM sessions WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            )

            if not session:
                raise ValueError(f"Session {session_id} not found or access denied")

            if soft:
                # Soft delete session
                await self.db.update(
                    "sessions",
                    {"deleted_at": datetime.now(timezone.utc)},
                    "session_id = ?",
                    (session_id,),
                )

                # Soft delete all messages in session
                await self.db.execute(
                    """
                    UPDATE messages
                    SET deleted_at = ?
                    WHERE session_id = ? AND deleted_at IS NULL
                    """,
                    (datetime.now(timezone.utc), session_id),
                )

                self.logger.info("chat_session_soft_deleted", session_id=session_id, user_id=user_id)
            else:
                # Hard delete messages
                await self.db.execute(
                    "DELETE FROM messages WHERE session_id = ?", (session_id,)
                )

                # Hard delete session
                await self.db.execute(
                    "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                )

                self.logger.info("chat_session_hard_deleted", session_id=session_id, user_id=user_id)

        # Broadcast event
        await self._broadcast(
            "chat.session.deleted",
            {
                "session_id": session_id,
                "user_id": user_id,
                "soft": soft,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {"deleted": True, "session_id": session_id}

    # =========================================================================
    # MESSAGE OPERATIONS
    # =========================================================================

    async def list_messages(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List messages in a session.

        Args:
            session_id: Session ID
            user_id: User ID (for access control)
            limit: Maximum number of messages
            offset: Pagination offset
            include_deleted: Whether to include soft-deleted messages

        Returns:
            List of messages sorted by created_at ASC
        """
        # Verify access
        session = await self.db.fetch_one(
            "SELECT * FROM sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )

        if not session:
            raise ValueError(f"Session {session_id} not found or access denied")

        # Query messages from messages table
        query = """
            SELECT
                message_id,
                session_id,
                role,
                content,
                created_at,
                deleted_at,
                edited_at,
                original_content
            FROM messages
            WHERE session_id = ?
        """
        params = [session_id]

        # Filter deleted messages unless requested
        if not include_deleted:
            query += " AND deleted_at IS NULL"

        query += " ORDER BY created_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self.db.fetch_all(query, tuple(params))

        # Use _prepare_message_payload for consistent serialization (handles PostgreSQL UUID/datetime)
        messages = [self._prepare_message_payload(dict(row)) for row in rows]

        return messages

    async def delete_message(
        self, message_id: int, user_id: str, soft: bool = True
    ) -> Dict[str, Any]:
        """
        Delete a message (soft delete by default).

        Args:
            message_id: Message ID
            user_id: User ID (for access control)
            soft: If True, set deleted_at. If False, hard delete.

        Returns:
            Result dict with deleted: true
        """
        # Verify message exists and belongs to user's session
        message = await self.db.fetch_one(
            """
            SELECT m.*, s.user_id
            FROM messages m
            JOIN sessions s ON m.session_id = s.session_id
            WHERE m.message_id = ?
            """,
            (message_id,),
        )

        if not message or message["user_id"] != user_id:
            raise ValueError(f"Message {message_id} not found or access denied")

        async with self.lock.acquire(user_id, str(message_id)):
            if soft:
                await self.db.update(
                    "messages",
                    {"deleted_at": datetime.now(timezone.utc)},
                    "message_id = ?",
                    (message_id,),
                )
                self.logger.info("chat_message_soft_deleted", message_id=message_id, user_id=user_id)
            else:
                await self.db.execute(
                    "DELETE FROM messages WHERE message_id = ?", (message_id,)
                )
                self.logger.info("chat_message_hard_deleted", message_id=message_id, user_id=user_id)

        # Broadcast event
        await self._broadcast(
            "chat.message.deleted",
            {
                "message_id": message_id,
                "session_id": message["session_id"],
                "user_id": user_id,
                "soft": soft,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {"deleted": True, "message_id": message_id}

    async def edit_message(
        self, message_id: int, user_id: str, new_content: str
    ) -> Dict[str, Any]:
        """
        Edit a message (user messages only).

        Args:
            message_id: Message ID
            user_id: User ID (for access control)
            new_content: New message content

        Returns:
            Updated message data
        """
        # Verify message exists and belongs to user
        message = await self.db.fetch_one(
            """
            SELECT m.*, s.user_id
            FROM messages m
            JOIN sessions s ON m.session_id = s.session_id
            WHERE m.message_id = ?
            """,
            (message_id,),
        )

        if not message or message["user_id"] != user_id:
            raise ValueError(f"Message {message_id} not found or access denied")

        if message["role"] != "user":
            raise ValueError("Only user messages can be edited")

        async with self.lock.acquire(user_id, str(message_id)):
            # Store original content if this is the first edit
            update_data = {
                "content": new_content,
                "edited_at": datetime.now(timezone.utc),
            }

            if not message.get("original_content"):
                update_data["original_content"] = message["content"]

            await self.db.update("messages", update_data, "message_id = ?", (message_id,))

            self.logger.info("chat_message_edited", message_id=message_id, user_id=user_id)

        # Fetch updated message
        updated = await self.db.fetch_one(
            "SELECT * FROM messages WHERE message_id = ?", (message_id,)
        )

        prepared = self._prepare_message_payload(updated)

        # Broadcast event
        await self._broadcast(
            "chat.message.edited",
            {
                "message_id": message_id,
                "session_id": message["session_id"],
                "user_id": user_id,
                "message": prepared,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return prepared

    # =========================================================================
    # SEARCH & EXPORT
    # =========================================================================

    async def search_messages(
        self, user_id: str, query: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Full-text search across all messages.

        Args:
            user_id: User ID (for access control)
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching messages with session info

        Note:
            Uses PostgreSQL ILIKE for pattern matching.
            For better full-text search, consider using tsvector/tsquery.
        """
        # Use PostgreSQL ILIKE for simple text search
        # Wrap query in wildcards for substring matching
        search_pattern = f"%{query}%"
        search_results = await self.db.fetch_all(
            """
            SELECT
                m.*,
                s.user_id,
                s.title as session_title
            FROM messages m
            JOIN sessions s ON m.session_id = s.session_id
            WHERE m.content ILIKE ?
                AND s.user_id = ?
                AND m.deleted_at IS NULL
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (search_pattern, user_id, limit),
        )

        return [self._prepare_message_payload(msg) for msg in search_results]

    async def export_session(
        self, session_id: str, user_id: str, format: str = "json"
    ) -> str:
        """
        Export a session to JSON, TXT, or Markdown.

        Args:
            session_id: Session ID
            user_id: User ID (for access control)
            format: Export format (json, txt, md)

        Returns:
            Exported session as string
        """
        # Get session
        session = await self.get_session(session_id, user_id)

        # Get all messages
        messages = await self.list_messages(session_id, user_id, limit=10000)

        if format == "json":
            return json.dumps(
                {
                    "session": session,
                    "messages": messages,
                },
                indent=2,
                default=str,
            )
        elif format == "txt":
            lines = [
                f"Session: {session.get('title', session_id)}",
                f"Created: {session['created_at']}",
                f"Messages: {len(messages)}",
                "=" * 80,
                "",
            ]
            for msg in messages:
                lines.append(f"[{msg['role'].upper()}] {msg['created_at']}")
                lines.append(msg["content"])
                lines.append("")
            return "\n".join(lines)
        elif format == "md":
            lines = [
                f"# {session.get('title', session_id)}",
                "",
                f"**Created:** {session['created_at']}  ",
                f"**Messages:** {len(messages)}",
                "",
                "---",
                "",
            ]
            for msg in messages:
                role_emoji = "👤" if msg["role"] == "user" else "🤖"
                lines.append(f"## {role_emoji} {msg['role'].title()}")
                lines.append(f"*{msg['created_at']}*")
                lines.append("")
                lines.append(msg["content"])
                lines.append("")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    # =========================================================================
    # HELPERS
    # =========================================================================

    async def _broadcast(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast event via WebSocketEventManager if available."""
        if self.event_manager:
            try:
                await self.event_manager.broadcast(event_type, payload)
            except Exception as e:
                self.logger.warning(
                    "event_broadcast_failed", event_type=event_type, error=str(e)
                )

    def _prepare_session_payload(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize session dictionaries with consistent serialization."""
        result = dict(session)

        # Normalize UUIDs to strings for API responses
        if "session_id" in result and not isinstance(result["session_id"], str):
            result["session_id"] = str(result["session_id"])

        # Convert datetime columns to ISO8601 strings
        for field in ["created_at", "last_activity", "deleted_at", "archived_at"]:
            value = result.get(field)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                result[field] = value.isoformat().replace("+00:00", "Z")

        return result

    def _prepare_message_payload(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize message dictionaries with consistent serialization."""
        result = dict(message)

        # Normalize UUIDs to strings for API responses (PostgreSQL returns UUID objects)
        if "session_id" in result and not isinstance(result["session_id"], str):
            result["session_id"] = str(result["session_id"])

        # Convert datetime columns to ISO8601 strings
        for field in ["created_at", "deleted_at", "edited_at"]:
            value = result.get(field)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                result[field] = value.isoformat().replace("+00:00", "Z")

        return result
