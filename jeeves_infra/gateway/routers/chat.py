"""
Chat router - REST + SSE streaming endpoints.

Provides:
- POST /messages - Send message (returns final response)
- GET /stream - SSE streaming of flow events
- GET /sessions - List sessions
- POST /sessions - Create session
- GET /sessions/{session_id} - Get session details
- GET /sessions/{session_id}/messages - List messages in session
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Optional, List, AsyncIterator, Dict

from fastapi import APIRouter, Request, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from jeeves_infra.gateway.sse import SSEStream, merge_sse_streams
from jeeves_infra.logging import get_current_logger
from jeeves_infra.utils.serialization import ms_to_iso

router = APIRouter()


# =============================================================================
# Event Publishing (Constitutional Pattern)
# =============================================================================

EVENT_CATEGORY_MAP: Dict[str, str] = {
    "agent.started": "AGENT_LIFECYCLE",
    "agent.completed": "AGENT_LIFECYCLE",
    "agent.decision": "AGENT_LIFECYCLE",
    "tool.started": "TOOL_EXECUTION",
    "tool.completed": "TOOL_EXECUTION",
    "tool.failed": "TOOL_EXECUTION",
    "orchestrator.started": "PIPELINE_FLOW",
    "orchestrator.completed": "PIPELINE_FLOW",
    "orchestrator.error": "PIPELINE_FLOW",
    "flow.started": "PIPELINE_FLOW",
    "flow.completed": "PIPELINE_FLOW",
    "orchestrator.stage_transition": "STAGE_TRANSITION",
    "stage.transition": "STAGE_TRANSITION",
    "stage.completed": "STAGE_TRANSITION",
}


def _classify_event_category(event_type: str) -> "EventCategory":
    from jeeves_infra.protocols.events import EventCategory

    if event_type in EVENT_CATEGORY_MAP:
        return getattr(EventCategory, EVENT_CATEGORY_MAP[event_type])

    prefix_map = {
        "agent.": "AGENT_LIFECYCLE",
        "tool.": "TOOL_EXECUTION",
        "orchestrator.": "PIPELINE_FLOW",
        "stage.": "STAGE_TRANSITION",
    }
    for prefix, category in prefix_map.items():
        if event_type.startswith(prefix):
            return getattr(EventCategory, category)

    return EventCategory.DOMAIN_EVENT


async def _publish_unified_event(event: dict):
    from jeeves_infra.gateway.event_bus import gateway_events
    from jeeves_infra.protocols.events import Event, EventCategory, EventSeverity
    from jeeves_infra.protocols.interfaces import RequestContext
    from datetime import datetime, timezone
    import uuid

    event_type = event.get("event_type", "agent.unknown")
    request_context_data = event.get("request_context")
    if not request_context_data:
        raise ValueError("request_context missing from event payload")
    request_context = RequestContext(**request_context_data)
    request_id = request_context.request_id
    session_id = request_context.session_id or ""
    timestamp_ms = event.get("timestamp_ms", int(datetime.now(timezone.utc).timestamp() * 1000))
    payload = event.get("payload", {})

    category = _classify_event_category(event_type)

    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    unified = Event(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        category=category,
        timestamp_iso=dt.isoformat(),
        timestamp_ms=timestamp_ms,
        request_context=request_context,
        request_id=request_id,
        session_id=session_id,
        user_id=event.get("user_id") or request_context.user_id,
        payload=payload,
        severity=EventSeverity.INFO,
        source="gateway",
        version="1.0",
    )

    await gateway_events.emit(unified)


# =============================================================================
# Request/Response Models
# =============================================================================

class MessageSend(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None
    mode: Optional[str] = None
    repo_path: Optional[str] = None


class MessageResponse(BaseModel):
    request_id: str
    session_id: str
    status: str
    response: Optional[str] = None
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    confirmation_message: Optional[str] = None
    confirmation_id: Optional[str] = None
    files_examined: Optional[List[str]] = None
    citations: Optional[List[str]] = None
    thread_id: Optional[str] = None


class SessionCreate(BaseModel):
    user_id: Optional[str] = None
    title: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    title: Optional[str] = None
    message_count: int = 0
    status: str = "active"
    created_at: str
    last_activity: Optional[str] = None


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
    total: int


class ChatMessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str


class MessageListResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int


# =============================================================================
# Event Constants (replace proto enums)
# =============================================================================

# Internal events: broadcast to frontend via SSE/WebSocket for visibility
INTERNAL_EVENT_TYPES = {
    "flow_started",
    "plan_created",
    "tool_started",
    "tool_completed",
    "critic_decision",
    "agent_started",
    "agent_completed",
    "synthesizer_complete",
    "stage_transition",
}

# Terminal events: returned in the POST response
TERMINAL_EVENT_TYPES = {
    "response_ready",
    "clarification",
    "confirmation",
    "error",
}


# =============================================================================
# Helpers
# =============================================================================

def _build_flow_request(user_id: str, body: MessageSend) -> Dict:
    context = {}
    if body.mode:
        context["mode"] = body.mode
    if body.repo_path:
        context["repo_path"] = body.repo_path

    return {
        "user_id": user_id,
        "session_id": body.session_id or "",
        "message": body.message,
        "context": context,
    }


def _get_flow_servicer(request: Request):
    servicer = getattr(request.app.state, "flow_servicer", None)
    if servicer is None:
        raise HTTPException(status_code=503, detail="Flow service not configured")
    return servicer


# =============================================================================
# Event Handler Strategy Pattern
# =============================================================================

class EventHandler(ABC):
    @abstractmethod
    def handle(self, payload: Dict, mode_config=None) -> Dict:
        pass


class ResponseReadyHandler(EventHandler):
    def handle(self, payload: Dict, mode_config=None) -> Dict:
        final_response = {
            "status": "completed",
            "response": payload.get("response_text") or payload.get("response"),
        }
        if mode_config:
            for field in mode_config.response_fields:
                if payload.get(field):
                    final_response[field] = payload.get(field)
        return final_response


class ClarificationHandler(EventHandler):
    def handle(self, payload: Dict, mode_config=None) -> Dict:
        _logger = get_current_logger()
        _logger.info(
            "gateway_received_clarification",
            clarification_question=payload.get("question"),
            thread_id=payload.get("thread_id"),
        )
        final_response = {
            "status": "clarification",
            "clarification_needed": True,
            "clarification_question": payload.get("question"),
        }
        if mode_config:
            for field in mode_config.response_fields:
                if payload.get(field):
                    final_response[field] = payload.get(field)
        return final_response


class ConfirmationHandler(EventHandler):
    def handle(self, payload: Dict, mode_config=None) -> Dict:
        return {
            "status": "confirmation",
            "confirmation_needed": True,
            "confirmation_message": payload.get("message"),
            "confirmation_id": payload.get("confirmation_id"),
        }


class ErrorHandler(EventHandler):
    def handle(self, payload: Dict, mode_config=None) -> Dict:
        return {
            "status": "error",
            "response": payload.get("error", "Unknown error"),
        }


EVENT_HANDLERS: Dict[str, EventHandler] = {
    "response_ready": ResponseReadyHandler(),
    "clarification": ClarificationHandler(),
    "confirmation": ConfirmationHandler(),
    "error": ErrorHandler(),
}


async def _process_event_stream(
    stream: AsyncIterator[Dict],
    user_id: str,
    mode_config=None,
) -> tuple[dict, str, str]:
    final_response = None
    request_id = ""
    session_id = ""

    async for event in stream:
        request_id = event.get("request_id") or request_id
        session_id = event.get("session_id") or session_id
        event_type = event.get("type", "")

        # Payload is already a dict (no JSON decode needed)
        payload = event.get("payload", {})
        if isinstance(payload, (bytes, str)):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}

        # Publish internal events for frontend visibility
        if event_type in INTERNAL_EVENT_TYPES:
            event_data = {
                "request_id": request_id,
                "session_id": session_id,
                "user_id": user_id,
                **payload,
            }
            await _publish_unified_event(event_data)

        # Handle terminal events
        handler = EVENT_HANDLERS.get(event_type)
        if handler:
            final_response = handler.handle(payload, mode_config)

    if final_response is None:
        raise HTTPException(
            status_code=500,
            detail="No response received from orchestrator",
        )

    return final_response, request_id, session_id


# =============================================================================
# Chat Message Endpoints
# =============================================================================

@router.post("/messages", response_model=MessageResponse)
async def send_message(
    request: Request,
    body: MessageSend,
    user_id: str = Query(..., min_length=1, max_length=255),
):
    _logger = get_current_logger()
    flow_servicer = _get_flow_servicer(request)

    from jeeves_infra.protocols import get_capability_resource_registry
    mode_registry = get_capability_resource_registry()
    mode_config = mode_registry.get_mode_config(body.mode) if body.mode else None

    flow_req = _build_flow_request(user_id, body)

    try:
        final_response, request_id, session_id = await _process_event_stream(
            flow_servicer.start_flow(
                user_id=flow_req["user_id"],
                session_id=flow_req["session_id"],
                message=flow_req["message"],
                context=flow_req["context"],
            ),
            user_id,
            mode_config,
        )

        _logger.info(
            "gateway_returning_response",
            request_id=request_id,
            session_id=session_id,
            status=final_response.get("status"),
            has_clarification=bool(final_response.get("clarification_question")),
        )

        return MessageResponse(
            request_id=request_id,
            session_id=session_id,
            **final_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        _logger.error("chat_message_failed", error=str(e), user_id=user_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stream")
async def stream_chat(
    request: Request,
    user_id: str = Query(..., min_length=1, max_length=255),
    message: str = Query(..., min_length=1, max_length=10000),
    session_id: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    repo_path: Optional[str] = Query(None),
):
    _logger = get_current_logger()
    flow_servicer = _get_flow_servicer(request)

    async def event_generator() -> AsyncIterator[str]:
        stream = SSEStream()

        context = {}
        if mode:
            context["mode"] = mode
        if repo_path:
            context["repo_path"] = repo_path

        try:
            async for event in flow_servicer.start_flow(
                user_id=user_id,
                session_id=session_id or "",
                message=message,
                context=context,
            ):
                event_type = event.get("type", "unknown")
                payload = event.get("payload", {})

                # Use specific event name from payload if available
                if isinstance(payload, dict) and "event_type" in payload:
                    event_type = payload["event_type"]

                payload_out = {
                    **(payload if isinstance(payload, dict) else {}),
                    "request_id": event.get("request_id", ""),
                    "session_id": event.get("session_id", ""),
                    "timestamp_ms": event.get("timestamp_ms", 0),
                }

                yield stream.event(payload_out, event=event_type)

            yield stream.done()

        except Exception as e:
            _logger.error("chat_stream_error", error=str(e))
            yield stream.error("Internal server error")

    return StreamingResponse(
        merge_sse_streams(event_generator()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# Session Endpoints
# =============================================================================

def _get_session_service(request: Request):
    svc = getattr(request.app.state, "session_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Session service not configured")
    return svc


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: Request,
    body: SessionCreate,
    user_id: str = Query(None, min_length=1, max_length=255),
):
    _logger = get_current_logger()
    svc = _get_session_service(request)

    actual_user_id = user_id
    if hasattr(body, "user_id") and body.user_id:
        actual_user_id = body.user_id
    if not actual_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        result = await svc.create_session(
            user_id=actual_user_id,
            title=body.title or "",
        )
        return SessionResponse(
            session_id=result["session_id"],
            user_id=result["user_id"],
            title=result.get("title") or None,
            message_count=0,
            status="active",
            created_at=ms_to_iso(result.get("created_at_ms", 0)),
        )
    except Exception as e:
        _logger.error("create_session_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    user_id: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_deleted: bool = Query(False),
):
    _logger = get_current_logger()
    svc = _get_session_service(request)

    try:
        result = await svc.list_sessions(
            user_id=user_id,
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
        )
        sessions = [
            SessionResponse(
                session_id=s["session_id"],
                user_id=s["user_id"],
                title=s.get("title") or None,
                message_count=s.get("message_count", 0),
                status=s.get("status", "active"),
                created_at=ms_to_iso(s.get("created_at_ms", 0)),
                last_activity=ms_to_iso(s["last_activity_ms"]) if s.get("last_activity_ms") else None,
            )
            for s in result.get("sessions", [])
        ]
        return SessionListResponse(sessions=sessions, total=result.get("total", len(sessions)))
    except Exception as e:
        _logger.error("list_sessions_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    request: Request,
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
):
    _logger = get_current_logger()
    svc = _get_session_service(request)

    try:
        s = await svc.get_session(session_id=session_id, user_id=user_id)
        return SessionResponse(
            session_id=s["session_id"],
            user_id=s["user_id"],
            title=s.get("title") or None,
            message_count=s.get("message_count", 0),
            status=s.get("status", "active"),
            created_at=ms_to_iso(s.get("created_at_ms", 0)),
            last_activity=ms_to_iso(s["last_activity_ms"]) if s.get("last_activity_ms") else None,
        )
    except Exception as e:
        _logger.error("get_session_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
async def get_session_messages(
    request: Request,
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _logger = get_current_logger()
    svc = _get_session_service(request)

    try:
        result = await svc.get_session_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        messages = [
            ChatMessageResponse(
                message_id=m["message_id"],
                session_id=m["session_id"],
                role=m["role"],
                content=m["content"],
                created_at=ms_to_iso(m.get("created_at_ms", 0)),
            )
            for m in result.get("messages", [])
        ]
        return MessageListResponse(messages=messages, total=result.get("total", len(messages)))
    except Exception as e:
        _logger.error("get_session_messages_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    request: Request,
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
):
    _logger = get_current_logger()
    svc = _get_session_service(request)

    try:
        result = await svc.delete_session(session_id=session_id, user_id=user_id)
        if not result.get("success", False):
            raise HTTPException(status_code=404, detail="Session not found")
        return None
    except HTTPException:
        raise
    except Exception as e:
        _logger.error("delete_session_failed", error=str(e), session_id=session_id)
        raise HTTPException(status_code=500, detail="Internal server error")
