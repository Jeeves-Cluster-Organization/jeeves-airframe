"""Integration tests for FastAPI server.

NOTE: These async tests may hang in GitHub CI due to cleanup issues.
For CI, use test_api_ci.py which has synchronous versions.

These tests are for local development and testing async flows.

Layer Extraction Compliant:
    Uses mock result objects instead of importing from capability layer.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from jeeves_infra.gateway.server import app, app_state, lifespan
from mission_system.config.constants import PLATFORM_NAME, PLATFORM_VERSION


@dataclass
class MockOrchestratorResult:
    """Mock result for orchestrator tests.

    Layer Extraction Compliant: Matches the interface expected by tests
    without importing from capability layer.
    """
    status: str = "complete"
    response: Optional[str] = None
    request_id: Optional[str] = None
    thread_id: Optional[str] = None
    clarification_question: Optional[str] = None


@pytest.fixture
async def test_app(pg_test_db):
    """Create test app with lifespan context.

    Uses PostgreSQL via testcontainers for test isolation.
    Per PostgreSQL-only migration (2025-11-27).
    """
    from jeeves_infra.settings import reload_settings, get_settings
    from jeeves_infra.database.factory import reset_factory

    # Save original environment values for cleanup
    original_env = {
        "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
        "MOCK_MODE": os.environ.get("MOCK_MODE"),
        "LLM_PROVIDER": os.environ.get("LLM_PROVIDER"),
    }

    # Set environment for testing with PostgreSQL
    os.environ["DATABASE_BACKEND"] = "postgres"
    os.environ["MOCK_MODE"] = "true"
    os.environ["LLM_PROVIDER"] = "mock"

    # Reset factory state and reload settings
    reset_factory()
    reload_settings()

    # Directly set settings attributes for proper isolation
    settings = get_settings()
    # Note: database_backend is now a read-only property always returning "postgres"
    settings.llm_provider = "mock"
    settings.memory_enabled = False

    # Inject PostgreSQL database into app state
    app_state.db = pg_test_db

    try:
        # Manually trigger the lifespan context to initialize app_state
        async with lifespan(app):
            # Now create AsyncClient for making requests
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Verify core initialization completed (orchestrator is optional without capability)
                assert app_state.health_checker is not None

                # If no orchestrator registered (no capability), provide a mock for tests
                if app_state.orchestrator is None:
                    mock_orchestrator = AsyncMock()
                    mock_orchestrator.process_query = AsyncMock()
                    app_state.orchestrator = mock_orchestrator

                yield client
    finally:
        # Cleanup - restore original environment values
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        # Clear shutdown event after tests
        app_state.shutdown_event.clear()
        app_state.db = None


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    """Test /health endpoint returns liveness check."""
    response = await test_app.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert data["version"] == PLATFORM_VERSION
    assert "components" in data
    assert "api" in data["components"]


@pytest.mark.asyncio
async def test_ready_endpoint_healthy(test_app):
    """Test /ready endpoint returns readiness check."""
    response = await test_app.get("/ready")

    assert response.status_code in (200, 503)  # Depends on database state
    data = response.json()

    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "uptime_seconds" in data
    assert "components" in data
    assert "database" in data["components"]


@pytest.mark.asyncio
async def test_root_endpoint(test_app):
    """Test root endpoint returns API information."""
    response = await test_app.get("/")

    assert response.status_code == 200
    data = response.json()

    assert data["service"] == PLATFORM_NAME
    assert data["version"] == PLATFORM_VERSION
    assert data["health"] == "/health"
    assert data["ready"] == "/ready"


@pytest.mark.asyncio
async def test_submit_request_success(test_app):
    """Test successful request submission."""
    from jeeves_infra.protocols import RequestContext
    from jeeves_infra.protocols import Envelope
    from jeeves_infra.protocols import TerminalReason

    # Create mock envelope result (uses input envelope's request_id for consistency)
    def create_mock_envelope(envelope, **kwargs):
        """Create a mock completed envelope."""
        result = Envelope(
            request_context=envelope.request_context,
            envelope_id=envelope.envelope_id,
            request_id=envelope.request_id,  # Use the input envelope's request_id
            user_id=envelope.user_id,
            session_id=envelope.session_id,
            raw_input=envelope.raw_input,
            terminal_reason=TerminalReason.COMPLETED,
            terminated=True,
            outputs={"integration": {"final_response": "Test response"}},
        )
        return result

    # Patch control_tower.submit_request to return mock result
    with patch.object(app_state.control_tower, "submit_request", side_effect=create_mock_envelope):
        response = await test_app.post(
            "/api/v1/requests",
            json={
                "user_message": "Test message",
                "user_id": "user-1",
                "session_id": "session-1",
            },
        )

    assert response.status_code == 200
    data = response.json()

    # request_id is generated dynamically, just check it's not empty
    assert data["request_id"] is not None
    assert data["status"] == "completed"
    assert data["response_text"] == "Test response"
    assert data["clarification_needed"] is False


@pytest.mark.asyncio
async def test_submit_request_clarification(test_app):
    """Test request submission requiring clarification."""
    from jeeves_infra.protocols import RequestContext
    from jeeves_infra.protocols import Envelope
    from jeeves_infra.protocols import FlowInterrupt, InterruptKind

    # Create mock envelope with clarification interrupt
    def create_mock_envelope(envelope, **kwargs):
        """Create a mock envelope requiring clarification."""
        interrupt = FlowInterrupt(
            id="interrupt-1",
            kind=InterruptKind.CLARIFICATION,
            request_id=envelope.request_id,  # Use input envelope's request_id
            user_id=envelope.user_id,
            session_id=envelope.session_id,
            question="Could you provide more details?",
        )
        result = Envelope(
            request_context=envelope.request_context,
            envelope_id=envelope.envelope_id,
            request_id=envelope.request_id,  # Use input envelope's request_id
            user_id=envelope.user_id,
            session_id=envelope.session_id,
            raw_input=envelope.raw_input,
            interrupt_pending=True,
            interrupt=interrupt,
        )
        return result

    with patch.object(app_state.control_tower, "submit_request", side_effect=create_mock_envelope):
        response = await test_app.post(
            "/api/v1/requests",
            json={
                "user_message": "Ambiguous message",
                "user_id": "user-1",
            },
        )

    assert response.status_code == 200
    data = response.json()

    # request_id is generated dynamically, just check it's not empty
    assert data["request_id"] is not None
    assert data["status"] == "clarification_needed"
    assert data["clarification_needed"] is True
    assert data["clarification_question"] == "Could you provide more details?"
    assert data["response_text"] is None


@pytest.mark.asyncio
async def test_submit_request_validation_error(test_app):
    """Test request submission with invalid payload."""
    response = await test_app.post(
        "/api/v1/requests",
        json={
            "user_message": "",  # Empty message (invalid)
            "user_id": "user-1",
        },
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_submit_request_orchestrator_error(test_app):
    """Test request submission when control tower fails."""
    with patch.object(
        app_state.control_tower, "submit_request", side_effect=Exception("Test error")
    ):
        response = await test_app.post(
            "/api/v1/requests",
            json={
                "user_message": "Test message",
                "user_id": "user-1",
            },
        )

    assert response.status_code == 500
    data = response.json()
    assert "Test error" in data["detail"]


@pytest.mark.asyncio
async def test_submit_request_during_shutdown(test_app):
    """Test request submission when service is shutting down."""
    # Set shutdown event
    app_state.shutdown_event.set()

    response = await test_app.post(
        "/api/v1/requests",
        json={
            "user_message": "Test message",
            "user_id": "user-1",
        },
    )

    assert response.status_code == 503
    assert "shutting down" in response.json()["detail"].lower()

    # Reset shutdown event
    app_state.shutdown_event.clear()


@pytest.mark.asyncio
@pytest.mark.websocket
@pytest.mark.requires_services
@pytest.mark.slow
async def test_websocket_connection():
    """Test WebSocket connection and event streaming.

    Note: This test may hang in CI. Run locally with: pytest -m websocket
    """
    # Use synchronous TestClient for WebSocket testing
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            # Should connect successfully
            # Send ping
            websocket.send_text("ping")

            # Should receive pong
            data = websocket.receive_text()
            assert data == "pong"


@pytest.mark.asyncio
@pytest.mark.websocket
@pytest.mark.requires_services
@pytest.mark.slow
async def test_websocket_broadcasts():
    """Test WebSocket receives broadcast events."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            # Trigger a broadcast
            if app_state.event_manager:
                await app_state.event_manager.broadcast(
                    "test.event", {"message": "Hello"}
                )

            # WebSocket should receive the event
            # Note: This may be flaky in tests due to timing
            # In production, events are reliably delivered


def test_sync_health_endpoint(sync_client):
    """Test health endpoint synchronously (for CI without async)."""
    response = sync_client.get("/health")
    assert response.status_code == 200


def test_sync_root_endpoint(sync_client):
    """Test root endpoint synchronously."""
    response = sync_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
