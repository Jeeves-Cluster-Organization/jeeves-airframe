"""WebSocket client management and event subscription.

Constitutional Pattern:
- WebSocket handler subscribes to gateway_events
- Routers publish events, don't know about WebSocket
- This module bridges events to WebSocket clients

UNIFIED EVENT SUPPORT (2025-12-14):
- Now receives Event instances from gateway_events
- Converts to JSON format for WebSocket transmission
- Constitutional compliance with EventEmitterProtocol

Usage:
    # In main.py at startup
    from jeeves_infra.gateway.websocket import setup_websocket_subscriptions
    setup_websocket_subscriptions()
"""

from typing import Set
from fastapi import WebSocket

from jeeves_infra.logging import get_current_logger
from protocols.events import Event


# Connected WebSocket clients (module-level state)
_connected_clients: Set[WebSocket] = set()


def get_connected_clients() -> Set[WebSocket]:
    """Get the set of connected WebSocket clients."""
    return _connected_clients


def register_client(websocket: WebSocket) -> int:
    """Register a WebSocket client.

    Returns:
        Current count of connected clients
    """
    _connected_clients.add(websocket)
    return len(_connected_clients)


def unregister_client(websocket: WebSocket) -> int:
    """Unregister a WebSocket client.

    Returns:
        Current count of connected clients
    """
    _connected_clients.discard(websocket)
    return len(_connected_clients)


async def broadcast_to_clients(message: dict) -> int:
    """Broadcast a message to all connected WebSocket clients.

    Returns:
        Number of clients message was sent to
    """
    if not _connected_clients:
        return 0

    _logger = get_current_logger()
    disconnected = set()
    sent_count = 0

    for client in _connected_clients:
        try:
            await client.send_json(message)
            sent_count += 1
        except Exception as e:
            _logger.debug(
                "websocket_send_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            disconnected.add(client)

    # Clean up disconnected clients
    for client in disconnected:
        _connected_clients.discard(client)

    return sent_count


# =============================================================================
# Event Bus Integration
# =============================================================================

async def _handle_agent_event(event: Event) -> None:
    """
    Handle unified events by broadcasting to WebSocket clients.

    This is the subscriber that bridges gateway events to WebSocket.

    Args:
        event: Event instance from gateway_events

    The event is converted to JSON-friendly format before broadcast:
    - type: "event" (message type indicator)
    - event_id: Unique event identifier
    - event_type: Namespaced event type (e.g., "agent.started")
    - category: Event category for filtering
    - timestamp: ISO 8601 timestamp
    - payload: Event-specific data
    - severity: Event severity level
    - session_id: Session correlation ID
    - request_id: Request correlation ID
    """
    await broadcast_to_clients({
        "type": "event",
        "event_id": event.event_id,
        "event_type": event.event_type,
        "category": event.category.value,
        "timestamp": event.timestamp_iso,
        "timestamp_ms": event.timestamp_ms,
        "payload": event.payload,
        "severity": event.severity.value,
        "session_id": event.session_id,
        "request_id": event.request_id,
        "source": event.source,
    })


async def setup_websocket_subscriptions() -> None:
    """
    Subscribe to gateway events for WebSocket broadcasting.

    Call this once at application startup (in main.py lifespan).

    Subscribes to all pipeline event categories:
    - agent.* (generic agent lifecycle)
    - perception.*, intent.*, planner.*, executor.*, synthesizer.*, critic.*, integration.*
    - orchestrator.* (flow-level events)
    """
    from jeeves_infra.gateway.event_bus import gateway_events

    _logger = get_current_logger()

    # Subscribe to all agent-related events with Event handler
    patterns = [
        "agent.*",
        "perception.*",
        "intent.*",
        "planner.*",
        "executor.*",
        "synthesizer.*",
        "critic.*",
        "integration.*",
        "orchestrator.*",
    ]

    for pattern in patterns:
        subscription_id = await gateway_events.subscribe(pattern, _handle_agent_event)
        _logger.debug("websocket_subscribed", pattern=pattern, subscription_id=subscription_id)


__all__ = [
    "get_connected_clients",
    "register_client",
    "unregister_client",
    "broadcast_to_clients",
    "setup_websocket_subscriptions",
]
