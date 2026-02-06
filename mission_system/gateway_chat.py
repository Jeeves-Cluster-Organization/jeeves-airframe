"""Chat API router for conversational interface.

This module provides REST endpoints for chat session and message management:
- GET /api/v1/chat/sessions - List user sessions
- POST /api/v1/chat/sessions - Create new session
- GET /api/v1/chat/sessions/{session_id} - Get session details
- PATCH /api/v1/chat/sessions/{session_id} - Update session (rename, archive)
- DELETE /api/v1/chat/sessions/{session_id} - Delete session
- GET /api/v1/chat/sessions/{session_id}/messages - List messages
- POST /api/v1/chat/messages - Send message (triggers orchestrator)
- DELETE /api/v1/chat/messages/{message_id} - Delete message
- PATCH /api/v1/chat/messages/{message_id} - Edit message
- GET /api/v1/chat/search - Full-text search
- GET /api/v1/chat/sessions/{session_id}/export - Export session
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, status
from pydantic import BaseModel, Field

from services.chat_service import ChatService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SessionCreate(BaseModel):
    """Request model for creating a session."""

    user_id: str = Field(..., min_length=1, max_length=255)
    title: Optional[str] = Field(None, max_length=500)


class SessionUpdate(BaseModel):
    """Request model for updating a session."""

    title: Optional[str] = Field(None, max_length=500)
    archived_at: Optional[str] = None  # ISO8601 format


class SessionResponse(BaseModel):
    """Response model for session data."""

    session_id: str
    user_id: str
    title: Optional[str] = None
    message_count: int
    created_at: str
    last_activity: str
    deleted_at: Optional[str] = None
    archived_at: Optional[str] = None


class MessageResponse(BaseModel):
    """Response model for message data."""

    message_id: int
    session_id: str
    role: str  # user, assistant, system
    content: str
    created_at: str
    deleted_at: Optional[str] = None
    edited_at: Optional[str] = None
    original_content: Optional[str] = None


class MessageEdit(BaseModel):
    """Request model for editing a message."""

    content: str = Field(..., min_length=1, max_length=10000)


class MessageSend(BaseModel):
    """Request model for sending a chat message."""

    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None  # Optional - if provided, continue that session


class MessageSendResponse(BaseModel):
    """Response model for sent message."""

    request_id: str
    session_id: str
    status: str  # completed, processing, failed
    response: Optional[str] = None
    # Confirmation support
    confirmation_needed: bool = False
    confirmation_message: Optional[str] = None
    confirmation_id: Optional[str] = None


class SearchRequest(BaseModel):
    """Request model for search."""

    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=50, ge=1, le=500)


class SearchResultResponse(BaseModel):
    """Response model for search results."""

    message_id: int
    session_id: str
    session_title: Optional[str] = None
    role: str
    content: str
    created_at: str


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str
    detail: str
    status_code: int


# =============================================================================
# Dependency Injection
# =============================================================================


def get_chat_service() -> ChatService:
    """Dependency injection for ChatService.

    NOTE: In production, this would be injected from app state.
    For now, we create instances directly (will be updated during server integration).
    """
    # This is a placeholder - will be properly injected from app_state
    # during server integration
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ChatService not initialized. Update server.py to inject dependencies.",
    )


# =============================================================================
# Session Endpoints
# =============================================================================


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    user_id: str = Query(..., min_length=1, max_length=255),
    filter: Optional[str] = Query(None, pattern="^(today|week|month|all)$"),
    include_deleted: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    chat_service: ChatService = Depends(get_chat_service),
):
    """List all sessions for a user."""
    try:
        sessions = await chat_service.list_sessions(
            user_id=user_id,
            filter=filter,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        return sessions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}",
        )


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    chat_service: ChatService = Depends(get_chat_service),
):
    """Create a new chat session."""
    try:
        session = await chat_service.create_session(
            user_id=body.user_id,
            title=body.title,
        )
        return session
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}",
        )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Get a single session by ID."""
    try:
        session = await chat_service.get_session(
            session_id=session_id,
            user_id=user_id,
        )
        return session
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}",
        )


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    body: SessionUpdate,
    user_id: str = Query(..., min_length=1, max_length=255),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Update a session (rename, archive)."""
    try:
        updates = {}
        if body.title is not None:
            updates["title"] = body.title
        if body.archived_at is not None:
            updates["archived_at"] = body.archived_at

        session = await chat_service.update_session(
            session_id=session_id,
            user_id=user_id,
            updates=updates,
        )
        return session
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}",
        )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
    soft: bool = Query(True),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Delete a session and all its messages."""
    try:
        await chat_service.delete_session(
            session_id=session_id,
            user_id=user_id,
            soft=soft,
        )
        return None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )


# =============================================================================
# Message Endpoints
# =============================================================================


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def list_messages(
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_deleted: bool = Query(False),
    chat_service: ChatService = Depends(get_chat_service),
):
    """List messages in a specific session."""
    try:
        messages = await chat_service.list_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
        )
        return messages
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list messages: {str(e)}",
        )


@router.post("/messages", response_model=MessageSendResponse)
async def send_chat_message(
    user_id: str = Query(..., min_length=1, max_length=255),
    body: MessageSend = ...,
    chat_service: ChatService = Depends(get_chat_service),
):
    """
    Send a chat message and trigger orchestrator processing.

    This endpoint supports multi-turn conversations within a session:
    1. If session_id is provided: continues that session (multi-turn)
    2. If session_id is None: creates a new session (first message)
    3. Triggers orchestrator to process the message
    4. Returns immediately with the response
    5. Messages are saved to DB by orchestrator

    Note: Old sessions can be viewed but not resumed (simplified mode)
    """
    from api.server import app_state

    if not app_state.orchestrator:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not available"
        )

    # Use provided session_id or create new session
    session_id = body.session_id
    if not session_id:
        # Create new session (first message)
        session = await chat_service.create_session(user_id)
        session_id = session["session_id"]
    else:
        # Verify session exists and belongs to user
        try:
            await chat_service.get_session(session_id=session_id, user_id=user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or access denied"
            )

    # Trigger orchestrator processing
    try:
        result = await app_state.orchestrator.process(
            user_message=body.message,
            user_id=user_id,
            session_id=session_id
        )

        # Build response with confirmation support
        response_data = {
            "request_id": result.envelope.request_id,
            "session_id": session_id,
        }

        # Check if confirmation is needed
        if result.confirmation_needed:
            response_data.update({
                "status": "completed",
                "response": None,
                "confirmation_needed": True,
                "confirmation_message": result.confirmation_message,
                "confirmation_id": result.confirmation_id,
            })
        elif result.response:
            response_data.update({
                "status": "completed",
                "response": result.response,  # response is already a string
                "confirmation_needed": False,
            })
        else:
            response_data.update({
                "status": "processing",
                "response": None,
                "confirmation_needed": False,
            })

        return MessageSendResponse(**response_data)

    except AttributeError as e:
        # P6: Observable - Provide specific error for missing components
        if "NoneType" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Service component not initialized. This may indicate a startup failure. "
                    "Check server logs for initialization errors, particularly memory manager or orchestrator. "
                    f"Error: {str(e)}"
                )
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )
    except Exception as e:
        # P6: Observable - Log full error context for debugging
        from jeeves_infra.logging import create_logger
        logger = create_logger(__name__)
        logger.error(
            "chat_message_processing_failed",
            user_id=user_id,
            session_id=session_id,
            message_length=len(body.message),
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    user_id: str = Query(..., min_length=1, max_length=255),
    soft: bool = Query(True),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Delete a message."""
    try:
        await chat_service.delete_message(
            message_id=message_id,
            user_id=user_id,
            soft=soft,
        )
        return None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete message: {str(e)}",
        )


@router.patch("/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: int,
    body: MessageEdit,
    user_id: str = Query(..., min_length=1, max_length=255),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Edit a message (user messages only)."""
    try:
        message = await chat_service.edit_message(
            message_id=message_id,
            user_id=user_id,
            new_content=body.content,
        )
        return message
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit message: {str(e)}",
        )


# =============================================================================
# Search & Export Endpoints
# =============================================================================


@router.get("/search", response_model=List[MessageResponse])
async def search_messages(
    query: str = Query(..., min_length=1, max_length=500),
    user_id: str = Query(..., min_length=1, max_length=255),
    limit: int = Query(50, ge=1, le=500),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Full-text search across all messages."""
    try:
        results = await chat_service.search_messages(
            user_id=user_id,
            query=query,
            limit=limit,
        )
        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    user_id: str = Query(..., min_length=1, max_length=255),
    format: str = Query("json", pattern="^(json|txt|md)$"),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Export a session to JSON, TXT, or Markdown."""
    try:
        content = await chat_service.export_session(
            session_id=session_id,
            user_id=user_id,
            format=format,
        )

        # Set content type based on format
        media_types = {
            "json": "application/json",
            "txt": "text/plain",
            "md": "text/markdown",
        }

        from fastapi.responses import Response

        return Response(
            content=content,
            media_type=media_types[format],
            headers={
                "Content-Disposition": f"attachment; filename=session_{session_id}.{format}"
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}",
        )
