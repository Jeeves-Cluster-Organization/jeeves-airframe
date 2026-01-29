"""Integration tests for FastAPI gateway.

Session 25 Update:
- Gateway uses gRPC-based app.py
- Tests requiring orchestrator backend are skipped
- Health endpoints work without gRPC
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from mission_system.gateway.app import app


# ============================================================
# Health Endpoints (no gRPC required)
# ============================================================

@pytest.mark.asyncio
async def test_health_endpoint():
    """Test /health endpoint returns liveness check."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint returns API information."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "version" in data
    assert "api" in data


@pytest.mark.asyncio
async def test_ready_endpoint_returns_not_ready_without_grpc():
    """Test /ready endpoint returns not_ready when no gRPC connection."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    # Should return 503 since no orchestrator is running
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"


# ============================================================
# API Endpoints (require gRPC orchestrator - skipped)
# ============================================================

@pytest.mark.skip(reason="Requires running gRPC orchestrator")
@pytest.mark.asyncio
async def test_chat_messages_endpoint():
    """Test /api/v1/chat/messages endpoint."""
    pass


@pytest.mark.skip(reason="Requires running gRPC orchestrator")
@pytest.mark.asyncio
async def test_governance_dashboard():
    """Test /api/v1/governance/dashboard endpoint."""
    pass


@pytest.mark.skip(reason="Requires running gRPC orchestrator")
@pytest.mark.asyncio
async def test_interrupts_endpoint():
    """Test /api/v1/interrupts endpoint."""
    pass
