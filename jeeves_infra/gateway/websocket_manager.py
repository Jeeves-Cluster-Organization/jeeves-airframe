"""
WebSocket Event Manager for streaming orchestration events.

Extracted from agents/orchestrator.py for separation of concerns.

This module provides:
- WebSocket connection management with authentication
- Event broadcasting to registered clients
- Heartbeat/idle timeout handling
- Local queue subscriptions (for testing)

Constitutional Alignment:
- P6: Testable/Observable - Full event streaming capability
- P4: Cognitive Offload - Real-time updates to clients
"""

from __future__ import annotations

import asyncio
import json
from time import monotonic
from typing import Any, Dict, Optional, Protocol, Set

from jeeves_infra.settings import settings


class WebSocketProtocol(Protocol):
    """Protocol for websocket connections (duck typing).

    Uses duck typing - any object with async send() method works.
    Supports FastAPI WebSocket, websockets library, etc.
    """
    async def send(self, data: str) -> None: ...


class WebSocketEventManager:
    """Utility for streaming orchestration events to websocket clients.

    Provides:
    - Connection registration with optional authentication
    - Event broadcasting to all connected clients
    - Queue-based subscriptions for testing
    - Heartbeat tracking for idle connection cleanup
    """

    def __init__(
        self,
        *,
        auth_token: Optional[str] = None,
        auth_required: Optional[bool] = None,
        heartbeat_interval: Optional[float] = None,
        idle_timeout: Optional[float] = None,
    ) -> None:
        """Initialize the WebSocket event manager.

        Args:
            auth_token: Token required for authentication (uses settings default)
            auth_required: Whether authentication is required (uses settings default)
            heartbeat_interval: Interval for heartbeat checks (uses settings default)
            idle_timeout: Timeout for idle connections (uses settings default)
        """
        self._connections: Set[WebSocketProtocol] = set()
        self._queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._auth_token = auth_token if auth_token is not None else settings.websocket_auth_token
        self._auth_required = auth_required if auth_required is not None else settings.websocket_auth_required
        self._heartbeat_interval = (
            heartbeat_interval if heartbeat_interval is not None else settings.websocket_heartbeat_interval
        )
        self._idle_timeout = idle_timeout if idle_timeout is not None else settings.websocket_idle_timeout
        self._heartbeats: Dict[WebSocketProtocol, float] = {}

    async def register(self, websocket: WebSocketProtocol, *, token: Optional[str] = None) -> None:
        """Register an active websocket connection.

        Args:
            websocket: WebSocket connection to register
            token: Authentication token (if auth_required)

        Raises:
            PermissionError: If authentication fails
        """
        # Only validate token if auth is required
        if self._auth_required and self._auth_token and token != self._auth_token:
            raise PermissionError("invalid websocket token")

        async with self._lock:
            self._connections.add(websocket)
            self._heartbeats[websocket] = monotonic()

    async def unregister(self, websocket: WebSocketProtocol) -> None:
        """Remove a websocket connection.

        Args:
            websocket: WebSocket connection to unregister
        """
        async with self._lock:
            self._connections.discard(websocket)
            self._heartbeats.pop(websocket, None)

    def create_subscription(self, name: Optional[str] = None, maxsize: int = 0) -> asyncio.Queue:
        """Create an asyncio queue subscription (primarily for testing).

        Args:
            name: Optional name for the subscription
            maxsize: Maximum queue size (0 = unlimited)

        Returns:
            Queue that will receive broadcast events
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        key = name or str(id(queue))
        self._queues[key] = queue
        return queue

    def drop_subscription(self, queue: asyncio.Queue) -> None:
        """Remove a subscription queue.

        Args:
            queue: Queue to unsubscribe
        """
        for key, stored in list(self._queues.items()):
            if stored is queue:
                del self._queues[key]
                break

    async def broadcast(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast an event to websocket clients and local subscribers.

        Args:
            event_type: Type of event (e.g., 'orchestrator.completed')
            payload: Event payload dictionary
        """
        message = {"event": event_type, "payload": payload}
        serialized = json.dumps(message, default=str)

        async with self._lock:
            connections = list(self._connections)
            heartbeats = dict(self._heartbeats)

        send_tasks = []
        now = monotonic()
        for ws in connections:
            last_seen = heartbeats.get(ws)
            if last_seen is not None and now - last_seen > self._idle_timeout:
                await self.unregister(ws)
                continue
            send_tasks.append(asyncio.create_task(self._safe_send(ws, serialized)))

        for queue in list(self._queues.values()):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Drop oldest item to make room for most recent event
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(message)

        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)

    async def _safe_send(self, websocket: WebSocketProtocol, data: str) -> None:
        """Safely send data to a websocket, unregistering on failure.

        Args:
            websocket: Target websocket
            data: Data to send
        """
        try:
            await websocket.send(data)
        except Exception:
            await self.unregister(websocket)

    async def heartbeat(self, websocket: WebSocketProtocol) -> None:
        """Record an explicit heartbeat for a websocket client.

        Args:
            websocket: WebSocket to refresh heartbeat for
        """
        async with self._lock:
            if websocket in self._connections:
                self._heartbeats[websocket] = monotonic()

    @property
    def heartbeat_interval(self) -> float:
        """Expose the configured heartbeat interval for clients."""
        return self._heartbeat_interval

    @property
    def connection_count(self) -> int:
        """Get the number of connected websockets."""
        return len(self._connections)
