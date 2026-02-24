"""
Jeeves Gateway - Main FastAPI Application.

HTTP gateway for REST/SSE endpoints.
Capability-agnostic: discovers service identity via CapabilityResourceRegistry.

Endpoints:
- REST: /api/v1/chat/*, /api/v1/governance/*
- SSE: /api/v1/chat/stream/{session_id}
- Health: /health, /ready

The gateway is stateless - all state lives in the orchestrator/database.

Constitutional Compliance:
- Constitution R3: No domain logic - gateway is pure transport
- Constitution R4: Swappable - queries CapabilityResourceRegistry for identity
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import Request
from prometheus_client import make_asgi_app

from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import get_capability_resource_registry
from jeeves_infra.observability.tracing import init_tracing, instrument_fastapi, shutdown_tracing


def _get_service_identity() -> str:
    """Get service identity from CapabilityResourceRegistry (Constitution R4)."""
    registry = get_capability_resource_registry()
    return registry.get_default_service() or "jeeves"


# =============================================================================
# Configuration
# =============================================================================

class GatewayConfig:
    """Gateway configuration from environment."""

    def __init__(self):
        self.orchestrator_host = os.getenv("ORCHESTRATOR_HOST", "localhost")
        self.orchestrator_port = int(os.getenv("ORCHESTRATOR_PORT", "50051"))
        self.api_host = os.getenv("API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("API_PORT", "8000"))
        self.cors_origins = os.getenv(
            "CORS_ORIGINS", "http://localhost:8000,http://localhost:3000"
        ).split(",")
        self.allow_credentials = True
        self.max_request_body_bytes = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1 * 1024 * 1024)))
        self.debug = os.getenv("DEBUG", "false").lower() == "true"


config = GatewayConfig()


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifecycle manager.

    Handles:
    - Service initialization
    - Graceful shutdown
    """
    _logger = get_current_logger()
    _logger.info(
        "gateway_startup_initiated",
        orchestrator=f"{config.orchestrator_host}:{config.orchestrator_port}",
    )

    # Initialize tracing
    jaeger_endpoint = os.getenv("JAEGER_ENDPOINT", "jaeger:4317")
    service_name = _get_service_identity() + "-gateway"
    init_tracing(service_name, jaeger_endpoint)
    _logger.info("tracing_initialized", service=service_name, jaeger=jaeger_endpoint)

    try:
        # Note: flow_servicer, health_servicer, session_service are injected
        # by the composition root (jeeves_infra.bootstrap) via app.state.
        # If not set, endpoints will return 503.
        if not hasattr(app.state, "interrupt_service"):
            _logger.warning("interrupt_service_not_configured",
                          hint="Interrupt endpoints will return 503 until service is injected")

        # Async init for state_backend (ConnectionManager.get_state_backend() is async)
        ctx = getattr(app.state, "context", None)
        if ctx is not None:
            from jeeves_infra.redis.connection_manager import ConnectionManager
            if isinstance(ctx.state_backend, ConnectionManager):
                ctx.state_backend = await ctx.state_backend.get_state_backend()
                _logger.info("state_backend_async_init_complete")

            # Connect database if pre-wired
            if ctx.db is not None and hasattr(ctx.db, "connect"):
                await ctx.db.connect()
                _logger.info("database_connected")

            # Connect kernel transport
            if ctx.kernel_client is not None:
                await ctx.kernel_client._transport.connect()
                _logger.info("kernel_transport_connected")

        _logger.info("gateway_startup_complete", status="READY")
        yield

    except Exception as e:
        _logger.error("gateway_startup_failed", error=str(e))
        raise

    finally:
        _logger.info("gateway_shutdown_initiated")

        # Graceful shutdown of async resources
        ctx = getattr(app.state, "context", None)
        if ctx is not None:
            if ctx.db is not None and hasattr(ctx.db, "disconnect"):
                try:
                    await ctx.db.disconnect()
                    _logger.info("database_disconnected")
                except Exception as e:
                    _logger.warning("database_disconnect_error", error=str(e))

            if ctx.state_backend is not None and hasattr(ctx.state_backend, "close"):
                try:
                    await ctx.state_backend.close()
                    _logger.info("state_backend_closed")
                except Exception as e:
                    _logger.warning("state_backend_close_error", error=str(e))

            if ctx.kernel_client is not None:
                try:
                    await ctx.kernel_client.close()
                    _logger.info("kernel_transport_closed")
                except Exception as e:
                    _logger.warning("kernel_transport_close_error", error=str(e))

        shutdown_tracing()
        _logger.info("gateway_shutdown_complete")


# =============================================================================
# FastAPI Application
# =============================================================================

_service_id = _get_service_identity()
app = FastAPI(
    title=f"{_service_id.replace('_', ' ').title()} Gateway",
    description="HTTP Gateway for REST/SSE endpoints",
    version="4.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI with OpenTelemetry
instrument_fastapi(app)

# CORS middleware — reject wildcard + credentials (insecure combination)
if "*" in config.cors_origins and config.allow_credentials:
    raise ValueError(
        "CORS wildcard ('*') with allow_credentials=True is forbidden. "
        "Set CORS_ORIGINS to explicit origins or disable credentials."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=config.allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request body size limit (1 MB default, override via MAX_REQUEST_BODY_BYTES)
from jeeves_infra.middleware.body_limit import BodyLimitMiddleware

app.add_middleware(BodyLimitMiddleware, max_bytes=config.max_request_body_bytes)

# Metrics middleware
from jeeves_infra.observability.metrics import record_http_request

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record Prometheus metrics for all HTTP requests."""
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Record metrics
    duration_seconds = time.time() - start_time
    record_http_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=duration_seconds
    )

    return response

# Mount static files (for UI templates)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    # Try gateway/templates first, fall back to api/templates (shared templates)
    import os
    template_dir = "gateway/templates"
    if not os.path.exists(template_dir):
        template_dir = "api/templates"
    templates = Jinja2Templates(directory=template_dir)
except RuntimeError:
    templates = None


# =============================================================================
# Health Endpoints
# =============================================================================

@app.get("/health")
async def health() -> JSONResponse:
    """
    Liveness probe - is the gateway running?

    Always returns 200 if the process is alive.
    """
    service_id = _get_service_identity()
    return JSONResponse({"status": "healthy", "service": f"{service_id}-gateway"})


@app.get("/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe - can the gateway serve traffic?

    Checks:
    - Service availability (flow_servicer, health_servicer)
    - InterruptService availability
    """
    checks = {
        "flow_service": "unknown",
        "interrupt_service": "unknown",
    }

    # Check flow servicer
    try:
        if hasattr(app.state, "flow_servicer") and app.state.flow_servicer is not None:
            checks["flow_service"] = "initialized"
        else:
            checks["flow_service"] = "not_initialized"
    except Exception as e:
        checks["flow_service"] = f"error: {str(e)}"

    # Check InterruptService
    try:
        if hasattr(app.state, "interrupt_service") and app.state.interrupt_service is not None:
            checks["interrupt_service"] = "initialized"
        else:
            checks["interrupt_service"] = "not_initialized"
    except Exception as e:
        checks["interrupt_service"] = f"error: {str(e)}"

    all_ok = all(v == "initialized" for v in checks.values())

    if all_ok:
        return JSONResponse({"status": "ready", **checks})
    else:
        return JSONResponse(status_code=503, content={"status": "not_ready", **checks})


@app.get("/")
async def root():
    """Root endpoint with API information."""
    service_id = _get_service_identity()
    return {
        "service": f"{service_id.replace('_', ' ').title()} Gateway",
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


# =============================================================================
# Mount Routers
# =============================================================================

from jeeves_infra.gateway.routers import chat, governance, interrupts

app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(governance.router, prefix="/api/v1/governance", tags=["governance"])
app.include_router(interrupts.router, prefix="/api/v1", tags=["interrupts"])


# =============================================================================
# Metrics Endpoint
# =============================================================================

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# =============================================================================
# UI Routes (optional - serve templates if available)
# =============================================================================

@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    """Serve Chat UI."""
    if not templates:
        raise HTTPException(status_code=503, detail="UI templates not available")
    return templates.TemplateResponse(request, "chat.html", {"active_page": "chat"})


@app.get("/governance", response_class=HTMLResponse)
async def governance_ui(request: Request):
    """Serve Governance UI."""
    if not templates:
        raise HTTPException(status_code=503, detail="UI templates not available")
    return templates.TemplateResponse(request, "governance.html", {"active_page": "governance"})


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "jeeves_infra.gateway.app:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
        log_level="info",
    )
