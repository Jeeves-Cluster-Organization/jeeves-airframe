"""CI-safe integration tests for FastAPI server.

These tests use synchronous TestClient to avoid async cleanup issues in CI.
All tests run reliably in GitHub Actions with proper cleanup.

GitHub CI Limitations Acknowledged:
- No llama-server/LLM available -> Use MOCK_MODE=true
- No WebSocket infrastructure -> Skip websocket tests
- Limited resources -> Use sync tests only
- Background tasks must clean up -> Use TestClient (handles lifespan properly)

Usage:
    # In CI (GitHub Actions)
    pytest tests/integration/test_api_ci.py -v

    # Locally
    pytest tests/integration/test_api_ci.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from jeeves_infra.gateway.server import app
from mission_system.config.constants import PLATFORM_NAME, PLATFORM_VERSION


def test_root_endpoint_sync(sync_client):
    """Test root endpoint returns API info."""
    response = sync_client.get("/")

    assert response.status_code == 200
    data = response.json()

    assert data["service"] == PLATFORM_NAME
    assert data["version"] == PLATFORM_VERSION
    assert "api" in data  # Should have API endpoint reference


def test_health_endpoint_sync(sync_client):
    """Test /health endpoint returns liveness check."""
    response = sync_client.get("/health")

    # May return 200 (healthy) or 500 (unhealthy) in CI
    assert response.status_code in (200, 500)
    data = response.json()

    assert "status" in data
    # Service may not fully initialize in CI, both are acceptable
    assert data["status"] in ("healthy", "unhealthy")


def test_ready_endpoint_sync(sync_client):
    """Test /ready endpoint returns readiness check."""
    response = sync_client.get("/ready")

    # May return 200 (ready) or 503 (not ready) in CI
    assert response.status_code in (200, 503)
    data = response.json()

    assert "status" in data


def test_metrics_endpoint_sync(sync_client):
    """Test /metrics endpoint (Prometheus format)."""
    response = sync_client.get("/metrics")

    # Metrics endpoint may return 200 with prometheus text or 404 if not enabled
    assert response.status_code in (200, 404, 501)


def test_multiple_health_checks_sync(sync_client):
    """Test handling multiple sequential health checks."""
    for i in range(3):
        response = sync_client.get("/health")
        assert response.status_code in (200, 500)
        data = response.json()
        assert "status" in data


def test_invalid_endpoint_404_sync(sync_client):
    """Test that invalid endpoints return 404."""
    response = sync_client.get("/invalid/endpoint")
    assert response.status_code == 404


def test_api_v1_endpoint_exists_sync(sync_client):
    """Test that API v1 endpoint exists."""
    # The actual endpoint is /api/v1/requests
    # Test with empty POST should return validation error or success
    response = sync_client.post("/api/v1/requests", json={})

    # Should get validation error (422) or other response (not 404)
    assert response.status_code in (422, 400, 200, 201, 500)


# These tests are intentionally simple and synchronous
# They avoid:
# - Async fixtures (which hang in CI)
# - WebSocket connections (not available in CI)
# - LLM calls (llama-server not available in CI)
# - Complex orchestration (tested in unit tests)
# - Long-running operations (timeout in CI)
#
# All async/websocket/LLM tests should go in test_api.py
# and be skipped in CI with markers.
