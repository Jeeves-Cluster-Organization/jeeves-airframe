"""FlowServicer - gRPC service for conversational flow orchestration.

Implements JeevesFlowServiceServicer to handle:
- StartFlow: Stream events from capability servicer
- CreateSession / GetSession / ListSessions / DeleteSession
- GetSessionMessages

Layer Extraction Compliant:
- Delegates to CapabilityServicerProtocol (no hardcoded capabilities)
- Uses CapabilityResourceRegistry for default titles
- Database access via DatabaseClientProtocol
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

try:
    import grpc
    from jeeves_infra.gateway.proto import jeeves_pb2, jeeves_pb2_grpc
    _GRPC_AVAILABLE = True
except ImportError:
    _GRPC_AVAILABLE = False

from jeeves_infra.protocols import get_capability_resource_registry


def _timestamp_ms() -> int:
    """Current UTC time in milliseconds."""
    return int(time.time() * 1000)


def _datetime_to_ms(dt: datetime) -> int:
    """Convert datetime to milliseconds since epoch."""
    return int(dt.timestamp() * 1000)


if _GRPC_AVAILABLE:
    _Base = jeeves_pb2_grpc.JeevesFlowServiceServicer
else:
    _Base = object


class FlowServicer(_Base):
    """gRPC servicer for conversational flow management."""

    def __init__(
        self,
        db,
        capability_servicer=None,
        logger=None,
    ):
        self._db = db
        self._servicer = capability_servicer
        self._logger = logger

    # -----------------------------------------------------------------
    # StartFlow (server-streaming)
    # -----------------------------------------------------------------

    async def StartFlow(self, request, context):
        """Start a conversational flow, streaming events back."""
        user_id = request.user_id
        session_id = request.session_id
        message = request.message
        req_context = request.context

        if self._logger:
            self._logger.info(
                "flow_started",
                user_id=user_id,
                session_id=session_id,
            )

        async for event in self._servicer.process_request(
            user_id, session_id, message, req_context
        ):
            yield event

    # -----------------------------------------------------------------
    # GetSession
    # -----------------------------------------------------------------

    async def GetSession(self, request, context):
        """Retrieve a single session by ID."""
        row = await self._db.fetch_one(
            "SELECT session_id, user_id, title, created_at, message_count "
            "FROM sessions WHERE session_id = :session_id AND user_id = :user_id",
            {"session_id": request.session_id, "user_id": request.user_id},
        )

        if row is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Session {request.session_id} not found",
            )
            return  # unreachable after abort, but keeps linters happy

        session = jeeves_pb2.Session(
            session_id=row["session_id"],
            user_id=row["user_id"],
            title=row.get("title", ""),
            message_count=row.get("message_count", 0),
            status="active",
            created_at_ms=_datetime_to_ms(row["created_at"]),
        )
        return session

    # -----------------------------------------------------------------
    # ListSessions
    # -----------------------------------------------------------------

    async def ListSessions(self, request, context):
        """List sessions for a user with pagination."""
        limit = request.limit or 50
        offset = request.offset or 0

        query = (
            "SELECT session_id, user_id, title, created_at, "
            "message_count, last_activity FROM sessions "
            "WHERE user_id = :user_id"
        )
        if not request.include_deleted:
            query += " AND deleted_at IS NULL"
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        rows = await self._db.fetch_all(
            query,
            {"user_id": request.user_id, "limit": limit, "offset": offset},
        )

        count_row = await self._db.fetch_one(
            "SELECT COUNT(*) as total FROM sessions WHERE user_id = :user_id",
            {"user_id": request.user_id},
        )
        total = count_row["total"] if count_row else 0

        sessions = []
        for row in rows:
            sessions.append(
                jeeves_pb2.Session(
                    session_id=row["session_id"],
                    user_id=row["user_id"],
                    title=row.get("title", ""),
                    message_count=row.get("message_count", 0),
                    status="active",
                    created_at_ms=_datetime_to_ms(row["created_at"]),
                )
            )

        return jeeves_pb2.ListSessionsResponse(
            sessions=sessions,
            total=total,
        )

    # -----------------------------------------------------------------
    # CreateSession
    # -----------------------------------------------------------------

    async def CreateSession(self, request, context):
        """Create a new session."""
        session_id = str(uuid4())
        title = request.title if request.title else self._get_default_session_title()
        now = datetime.now(timezone.utc)

        await self._db.execute(
            "INSERT INTO sessions (session_id, user_id, title, created_at, message_count) "
            "VALUES (:session_id, :user_id, :title, :created_at, 0)",
            {
                "session_id": session_id,
                "user_id": request.user_id,
                "title": title,
                "created_at": now,
            },
        )

        return jeeves_pb2.Session(
            session_id=session_id,
            user_id=request.user_id,
            title=title,
            message_count=0,
            status="active",
            created_at_ms=_datetime_to_ms(now),
        )

    # -----------------------------------------------------------------
    # DeleteSession (soft delete)
    # -----------------------------------------------------------------

    async def DeleteSession(self, request, context):
        """Soft-delete a session by setting deleted_at."""
        result = await self._db.execute(
            "UPDATE sessions SET deleted_at = :deleted_at "
            "WHERE session_id = :session_id AND user_id = :user_id AND deleted_at IS NULL",
            {
                "session_id": request.session_id,
                "user_id": request.user_id,
                "deleted_at": datetime.now(timezone.utc),
            },
        )

        success = getattr(result, "rowcount", 0) > 0
        return jeeves_pb2.DeleteSessionResponse(success=success)

    # -----------------------------------------------------------------
    # GetSessionMessages
    # -----------------------------------------------------------------

    async def GetSessionMessages(self, request, context):
        """Retrieve messages for a session with pagination."""
        # Verify session exists
        session = await self._db.fetch_one(
            "SELECT session_id FROM sessions "
            "WHERE session_id = :session_id",
            {"session_id": request.session_id},
        )

        if session is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Session {request.session_id} not found",
            )
            return

        limit = request.limit or 100
        offset = request.offset or 0

        rows = await self._db.fetch_all(
            "SELECT message_id, session_id, role, content, created_at "
            "FROM messages WHERE session_id = :session_id "
            "ORDER BY created_at ASC LIMIT :limit OFFSET :offset",
            {"session_id": request.session_id, "limit": limit, "offset": offset},
        )

        count_row = await self._db.fetch_one(
            "SELECT COUNT(*) as total FROM messages WHERE session_id = :session_id",
            {"session_id": request.session_id},
        )
        total = count_row["total"] if count_row else 0

        messages = []
        for row in rows:
            messages.append(
                jeeves_pb2.ChatMessage(
                    message_id=str(row["message_id"]),
                    role=row["role"],
                    content=row["content"],
                    created_at_ms=_datetime_to_ms(row["created_at"]),
                )
            )

        return jeeves_pb2.GetSessionMessagesResponse(
            messages=messages,
            total=total,
        )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _get_default_session_title(self) -> str:
        """Get default session title from CapabilityResourceRegistry."""
        registry = get_capability_resource_registry()
        default_service = registry.get_default_service()
        if default_service is None:
            return "Session"
        config = registry.get_service_config(default_service)
        if config is None:
            return "Session"
        return getattr(config, "default_session_title", "Session")

    def _make_event(
        self,
        event_type: int,
        request_id: str,
        session_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """Create a FlowEvent proto message."""
        payload_bytes = json.dumps(payload or {}).encode("utf-8")
        return jeeves_pb2.FlowEvent(
            type=event_type,
            request_id=request_id,
            session_id=session_id,
            payload=payload_bytes,
            timestamp_ms=_timestamp_ms(),
        )
