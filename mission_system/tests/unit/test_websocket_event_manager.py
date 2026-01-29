"""Unit tests for the WebSocketEventManager security additions."""

import asyncio
import json

import pytest

from mission_system.gateway.websocket_manager import WebSocketEventManager


class FakeWebSocket:
    """Minimal websocket stub that records sent messages."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_websocket_manager_requires_token() -> None:
    manager = WebSocketEventManager(auth_token="secret", auth_required=True, idle_timeout=1)
    ws = FakeWebSocket()

    with pytest.raises(PermissionError):
        await manager.register(ws, token="wrong")

    await manager.register(ws, token="secret")
    await manager.broadcast("test.event", {"value": 1})

    assert ws.sent
    payload = json.loads(ws.sent[0])
    assert payload["event"] == "test.event"


@pytest.mark.asyncio
async def test_websocket_manager_enforces_idle_timeout() -> None:
    manager = WebSocketEventManager(auth_token="token", idle_timeout=0.05)
    ws = FakeWebSocket()
    await manager.register(ws, token="token")

    await asyncio.sleep(0.06)
    await manager.broadcast("keepalive", {})

    assert not ws.sent


@pytest.mark.asyncio
async def test_websocket_heartbeat_refreshes_connection() -> None:
    manager = WebSocketEventManager(auth_token="token", idle_timeout=0.05)
    ws = FakeWebSocket()
    await manager.register(ws, token="token")

    await asyncio.sleep(0.03)
    await manager.heartbeat(ws)
    await asyncio.sleep(0.03)
    await manager.broadcast("message", {})

    assert ws.sent
    assert manager.heartbeat_interval > 0
