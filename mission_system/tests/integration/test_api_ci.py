"""CI-safe integration tests for FastAPI gateway.

Session 25 Update:
- Gateway uses gRPC-based app.py
- Health endpoints work without gRPC
- API endpoints require running orchestrator (skipped in CI)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from mission_system.gateway.app import app


@pytest.mark.asyncio
async def test_root_endpoint_sync():
    """Test root endpoint returns API info."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_endpoint_sync():
    """Test /health endpoint returns liveness check."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_endpoint_without_orchestrator():
    """Test /ready returns not_ready without gRPC orchestrator."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    # Without orchestrator, should return 503
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"


@pytest.mark.asyncio
async def test_invalid_endpoint_404():
    """Test that invalid endpoints return 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/invalid/endpoint")

    assert response.status_code == 404
