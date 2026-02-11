"""FlowServicer - service for conversational flow orchestration.

Handles:
- StartFlow: Stream events from capability servicer

Session CRUD is owned by capability layer (e.g. chat_router.py + ChatService).

Layer Extraction Compliant:
- Delegates to CapabilityServicerProtocol (no hardcoded capabilities)
- Database access via DatabaseClientProtocol
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Dict, Optional


def _timestamp_ms() -> int:
    """Current UTC time in milliseconds."""
    return int(time.time() * 1000)


class FlowServicer:
    """Service for conversational flow management."""

    def __init__(
        self,
        db,
        capability_servicer,
        logger=None,
    ):
        self._db = db
        self._servicer = capability_servicer
        self._logger = logger

    # -----------------------------------------------------------------
    # StartFlow (server-streaming)
    # -----------------------------------------------------------------

    async def start_flow(
        self,
        user_id: str,
        session_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Start a conversational flow, streaming events back.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            message: User message text.
            context: Optional request context dict.

        Yields:
            Event dicts from the capability servicer.
        """
        if self._logger:
            self._logger.info(
                "flow_started",
                user_id=user_id,
                session_id=session_id,
            )

        async for event in self._servicer.process_request(
            user_id, session_id, message, context
        ):
            yield event

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def make_event(
        event_type: str,
        request_id: str,
        session_id: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a flow event dict.

        Args:
            event_type: Event type string (e.g. "response_ready").
            request_id: Request identifier.
            session_id: Session identifier.
            payload: Optional event payload.

        Returns:
            Event dict.
        """
        return {
            "type": event_type,
            "request_id": request_id,
            "session_id": session_id,
            "payload": payload or {},
            "timestamp_ms": _timestamp_ms(),
        }
