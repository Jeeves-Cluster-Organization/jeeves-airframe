"""Chat API router - re-exports from mission_system.gateway_chat.

app_server.py imports `from mission_system.api.chat import router, get_chat_service`.
The actual implementation lives in gateway_chat.py.
"""

from mission_system.gateway_chat import router, get_chat_service

__all__ = ["router", "get_chat_service"]
