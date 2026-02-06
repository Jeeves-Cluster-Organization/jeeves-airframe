"""Chat API router - re-exports from mission_system.gateway_chat.

Fixes the import path so app_server.py can import from
`mission_system.api.chat` consistently.
"""

# gateway_chat.py has a broken `from services.chat_service` import.
# Re-export the fixed version here.
from mission_system.services.chat_service import ChatService

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# Dependency injection placeholder
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Dependency injection for ChatService."""
    if _chat_service is None:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    return _chat_service


def set_chat_service(service: ChatService) -> None:
    """Set the chat service instance (called during app startup)."""
    global _chat_service
    _chat_service = service
