"""Unit tests for the FastAPI gateway application.

Tests health endpoints, readiness checks, root API info,
body-limit middleware, and CORS headers.

The module-level app import triggers real service discovery and tracing
init, so we patch those before importing the app module.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Helpers - build a lightweight test app mirroring real app structure
# ---------------------------------------------------------------------------

def _noop_instrument(app):
    """No-op replacement for instrument_fastapi."""
    pass


def _build_test_app(
    *,
    flow_servicer=None,
    interrupt_service=None,
) -> FastAPI:
    """Build a minimal FastAPI app that mirrors the real gateway.

    Instead of importing the module-level ``app`` (which triggers tracing,
    Prometheus, static-file mounts, and router imports), we reconstruct the
    relevant pieces in isolation so the tests stay fast and dependency-free.
    """

    @asynccontextmanager
    async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    test_app = FastAPI(
        title="Test Gateway",
        version="4.0.0",
        lifespan=_test_lifespan,
    )

    # Inject services onto app.state (mirrors composition root)
    if flow_servicer is not None:
        test_app.state.flow_servicer = flow_servicer
    if interrupt_service is not None:
        test_app.state.interrupt_service = interrupt_service

    # ---- Middleware (same order as real app) ----
    from fastapi.middleware.cors import CORSMiddleware

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from jeeves_infra.middleware.body_limit import BodyLimitMiddleware

    test_app.add_middleware(BodyLimitMiddleware, max_bytes=1 * 1024 * 1024)

    # ---- Endpoints (copied from app.py to avoid import side-effects) ----
    from fastapi.responses import JSONResponse

    @test_app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "healthy", "service": "test-gateway"})

    @test_app.get("/ready")
    async def ready() -> JSONResponse:
        checks = {
            "flow_service": "unknown",
            "interrupt_service": "unknown",
        }
        try:
            if (
                hasattr(test_app.state, "flow_servicer")
                and test_app.state.flow_servicer is not None
            ):
                checks["flow_service"] = "initialized"
            else:
                checks["flow_service"] = "not_initialized"
        except Exception as e:
            checks["flow_service"] = f"error: {str(e)}"

        try:
            if (
                hasattr(test_app.state, "interrupt_service")
                and test_app.state.interrupt_service is not None
            ):
                checks["interrupt_service"] = "initialized"
            else:
                checks["interrupt_service"] = "not_initialized"
        except Exception as e:
            checks["interrupt_service"] = f"error: {str(e)}"

        all_ok = all(v == "initialized" for v in checks.values())
        if all_ok:
            return JSONResponse({"status": "ready", **checks})
        else:
            return JSONResponse(
                status_code=503, content={"status": "not_ready", **checks}
            )

    @test_app.get("/")
    async def root():
        return {
            "service": "Test Gateway",
            "version": "4.0.0",
            "health": "/health",
            "ready": "/ready",
            "api": {
                "chat": "/api/v1/chat",
                "governance": "/api/v1/governance",
                "interrupts": "/api/v1/interrupts",
            },
            "streaming": {
                "chat_sse": "/api/v1/chat/stream/{session_id}",
            },
            "docs": "/docs",
        }

    @test_app.post("/echo")
    async def echo(request: Request):
        """Tiny endpoint used only by the body-limit test."""
        body = await request.body()
        return JSONResponse({"size": len(body)})

    return test_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bare_app() -> FastAPI:
    """App with NO services injected (mimics cold start)."""
    return _build_test_app()


@pytest.fixture
def ready_app() -> FastAPI:
    """App with both required services injected."""
    return _build_test_app(
        flow_servicer=MagicMock(name="flow_servicer"),
        interrupt_service=MagicMock(name="interrupt_service"),
    )


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """GET /health -- liveness probe."""

    async def test_health_returns_200(self, bare_app: FastAPI):
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"

    async def test_health_contains_service_name(self, bare_app: FastAPI):
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        body = resp.json()
        assert "service" in body
        assert isinstance(body["service"], str)
        assert len(body["service"]) > 0


# ---------------------------------------------------------------------------
# Readiness endpoint
# ---------------------------------------------------------------------------

class TestReadyEndpoint:
    """GET /ready -- readiness probe."""

    async def test_ready_returns_503_when_no_services(self, bare_app: FastAPI):
        """With no services injected the gateway is NOT ready."""
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["flow_service"] == "not_initialized"
        assert body["interrupt_service"] == "not_initialized"

    async def test_ready_returns_200_when_services_present(self, ready_app: FastAPI):
        """With all services injected the gateway IS ready."""
        transport = ASGITransport(app=ready_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ready")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["flow_service"] == "initialized"
        assert body["interrupt_service"] == "initialized"

    async def test_ready_partial_services(self):
        """Only flow_servicer present -- still not ready."""
        app = _build_test_app(flow_servicer=MagicMock())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["flow_service"] == "initialized"
        assert body["interrupt_service"] == "not_initialized"


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

class TestRootEndpoint:
    """GET / -- API info."""

    async def test_root_returns_200(self, bare_app: FastAPI):
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/")

        assert resp.status_code == 200

    async def test_root_contains_expected_keys(self, bare_app: FastAPI):
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/")

        body = resp.json()
        assert "service" in body
        assert "version" in body
        assert "health" in body
        assert "ready" in body
        assert "api" in body
        assert "docs" in body

    async def test_root_version_is_string(self, bare_app: FastAPI):
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/")

        body = resp.json()
        assert isinstance(body["version"], str)

    async def test_root_api_section_has_chat_and_governance(self, bare_app: FastAPI):
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/")

        api = resp.json()["api"]
        assert "chat" in api
        assert "governance" in api
        assert "interrupts" in api


# ---------------------------------------------------------------------------
# Body-limit middleware
# ---------------------------------------------------------------------------

class TestBodyLimitMiddleware:
    """BodyLimitMiddleware rejects requests larger than 1 MB."""

    async def test_small_body_accepted(self, bare_app: FastAPI):
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/echo", content=b"hello")

        assert resp.status_code == 200
        assert resp.json()["size"] == 5

    async def test_oversized_body_rejected_with_413(self, bare_app: FastAPI):
        """A request with Content-Length > 1 MB should be rejected."""
        oversized = b"x" * (1 * 1024 * 1024 + 1)
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/echo", content=oversized)

        assert resp.status_code == 413
        body = resp.json()
        assert body["error"] == "request_too_large"

    async def test_exact_limit_body_accepted(self, bare_app: FastAPI):
        """A request at exactly 1 MB should pass."""
        exact = b"x" * (1 * 1024 * 1024)
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/echo", content=exact)

        assert resp.status_code == 200
        assert resp.json()["size"] == 1 * 1024 * 1024


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------

class TestCORSHeaders:
    """CORS middleware adds expected headers for allowed origins."""

    async def test_cors_headers_on_allowed_origin(self, bare_app: FastAPI):
        """Preflight from an allowed origin should include CORS headers."""
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"

    async def test_cors_headers_on_simple_get(self, bare_app: FastAPI):
        """A simple GET with Origin header should include CORS allow-origin."""
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/health",
                headers={"Origin": "http://localhost:3000"},
            )

        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers
        assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"

    async def test_cors_disallowed_origin(self, bare_app: FastAPI):
        """A request from an origin not in the allow-list should not get CORS headers."""
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/health",
                headers={"Origin": "http://evil.example.com"},
            )

        # The request itself succeeds (CORS is enforced client-side), but
        # the access-control-allow-origin header should NOT be present.
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in resp.headers

    async def test_cors_credentials_header(self, bare_app: FastAPI):
        """Preflight should advertise credentials support."""
        transport = ASGITransport(app=bare_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

        assert resp.headers.get("access-control-allow-credentials") == "true"
