"""FlowServicer - gRPC service for conversational flow orchestration.

Implements JeevesFlowServiceServicer to handle:
- StartFlow: Stream events from capability servicer

Session CRUD is owned by capability layer (e.g. chat_router.py + ChatService).

Layer Extraction Compliant:
- Delegates to CapabilityServicerProtocol (no hardcoded capabilities)
- Database access via DatabaseClientProtocol
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

try:
    import grpc
    from jeeves_infra.gateway.proto import jeeves_pb2, jeeves_pb2_grpc
    _GRPC_AVAILABLE = True
except ImportError:
    _GRPC_AVAILABLE = False


def _timestamp_ms() -> int:
    """Current UTC time in milliseconds."""
    return int(time.time() * 1000)


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
    # Helpers
    # -----------------------------------------------------------------

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
