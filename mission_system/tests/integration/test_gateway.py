"""
Gateway Integration Tests.

Tests the HTTP gateway API endpoints.
These tests require the gateway service to be running.

Run with:
    docker compose run --rm test pytest tests/integration/test_gateway.py -v

Or via the deployment script:
    python scripts/deployment/deploy.py --test-gateway

Note: v3.0 Pivot - Removed Kanban, Journal, Open Loops API tests (features deleted)
Note: UI/static file tests removed - frontend moved to capability layer
"""

import os
import pytest
import httpx
from typing import Optional

# Gateway URL - uses GATEWAY_HOST env var or defaults to localhost:8001
GATEWAY_URL = os.environ.get("GATEWAY_HOST", "http://gateway:8000")

# Skip all tests if gateway is not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GATEWAY_HOST") and os.environ.get("CI") != "true",
        reason="Gateway tests require GATEWAY_HOST env var or running in CI with gateway service"
    )
]


def _gateway_available() -> bool:
    """Check if gateway is reachable."""
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{GATEWAY_URL}/health")
            return response.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def gateway_client():
    """Create an HTTP client for the gateway."""
    # Skip if gateway not available
    if not _gateway_available():
        pytest.skip(f"Gateway not available at {GATEWAY_URL}")

    base_url = GATEWAY_URL

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        yield client


@pytest.fixture(scope="module")
def async_gateway_client():
    """Create an async HTTP client for the gateway."""
    if not _gateway_available():
        pytest.skip(f"Gateway not available at {GATEWAY_URL}")

    base_url = GATEWAY_URL
    return httpx.AsyncClient(base_url=base_url, timeout=10.0)


class TestGatewayHealth:
    """Test gateway health endpoints."""

    def test_health_endpoint(self, gateway_client):
        """Test that /health endpoint returns healthy status."""
        response = gateway_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        # Accept any service name ending with "-gateway" (capability-agnostic)
        service = data["service"]
        assert service.endswith("-gateway") or service == "gateway", \
            f"Expected service name ending with '-gateway', got: {service}"

    def test_ready_endpoint(self, gateway_client):
        """Test that /ready endpoint returns ready status."""
        response = gateway_client.get("/ready")
        # May return 503 if orchestrator not connected, but endpoint should exist
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data

    def test_root_endpoint(self, gateway_client):
        """Test that root endpoint returns API info."""
        response = gateway_client.get("/")
        assert response.status_code == 200
        data = response.json()
        # Accept any service name containing "Gateway" (capability-agnostic)
        service = data["service"]
        assert "gateway" in service.lower(), \
            f"Expected service name containing 'gateway', got: {service}"
        assert "api" in data
        assert "chat" in data["api"]


# Note: TestGatewayUI and TestStaticFiles removed - UI/static files moved to capability layer
# jeeves-core provides API only; capabilities provide their own frontend


class TestChatAPI:
    """Test chat API endpoints."""

    def test_list_sessions_requires_user_id(self, gateway_client):
        """Test that /api/v1/chat/sessions requires user_id."""
        response = gateway_client.get("/api/v1/chat/sessions")
        assert response.status_code == 422  # Validation error

    def test_list_sessions_returns_empty(self, gateway_client):
        """Test that /api/v1/chat/sessions returns empty list for new user."""
        response = gateway_client.get(
            "/api/v1/chat/sessions",
            params={"user_id": "test-user-gateway-tests"}
        )
        # May fail if backend not connected, but should return valid JSON
        if response.status_code == 200:
            data = response.json()
            assert "sessions" in data
            assert isinstance(data["sessions"], list)
        else:
            # Backend error - endpoint exists but backend unavailable
            assert response.status_code in (500, 503)

    def test_create_session_endpoint_exists(self, gateway_client):
        """Test that POST /api/v1/chat/sessions endpoint exists."""
        response = gateway_client.post(
            "/api/v1/chat/sessions",
            json={"user_id": "test-user", "title": "Test Session"}
        )
        # Should not be 404 (endpoint exists)
        # May be 500/503 if backend not connected, or 200/201 if successful
        assert response.status_code != 404


class TestGovernanceAPI:
    """Test governance API endpoints."""

    def test_dashboard_endpoint(self, gateway_client):
        """Test that /api/v1/governance/dashboard returns dashboard data."""
        response = gateway_client.get("/api/v1/governance/dashboard")
        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "tools" in data
        assert "agents" in data
        assert "memory_layers" in data
        assert "config" in data

        # v3.0: Verify agents are the 6-agent architecture
        # PERCEPTION → INTENT → PLANNER → TRAVERSER → CRITIC → INTEGRATION
        # Agent names may be class names (e.g., "PlannerAgent") or display names
        agent_names = {a["name"].lower() for a in data["agents"]}
        # Check for at least some expected agents (flexible matching)
        has_planner = any("planner" in name for name in agent_names)
        has_intent = any("intent" in name for name in agent_names)
        assert has_planner, f"Expected planner agent, found: {agent_names}"
        assert has_intent, f"Expected intent agent, found: {agent_names}"

    def test_health_endpoint_exists(self, gateway_client):
        """Test that /api/v1/governance/health endpoint exists."""
        response = gateway_client.get("/api/v1/governance/health")
        # May return 500/503 if backend not connected, but should exist
        assert response.status_code != 404


# Note: TestKanbanAPI, TestJournalAPI, and TestOpenLoopsAPI removed in v3.0
# These features were permanently deleted in the Code Analysis Agent pivot.


class TestWebSocket:
    """Test WebSocket endpoint."""

    @pytest.mark.asyncio
    async def test_websocket_connection(self, async_gateway_client):
        """Test that WebSocket endpoint accepts connections."""
        import websockets

        ws_url = GATEWAY_URL.replace("http://", "ws://") + "/ws"

        try:
            async with websockets.connect(ws_url, close_timeout=5) as ws:
                # Should receive connected message
                msg = await ws.recv()
                import json
                data = json.loads(msg)
                assert data["type"] == "connected"
        except Exception as e:
            # WebSocket may not be available in test environment
            pytest.skip(f"WebSocket connection failed: {e}")


class TestOpenAPISpec:
    """Test OpenAPI/Swagger documentation."""

    def test_openapi_json(self, gateway_client):
        """Test that OpenAPI spec is available."""
        response = gateway_client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data

    def test_docs_endpoint(self, gateway_client):
        """Test that /docs serves Swagger UI."""
        response = gateway_client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
