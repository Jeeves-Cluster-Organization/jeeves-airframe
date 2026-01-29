"""
Jeeves Gateway - Main FastAPI Application.

HTTP gateway that translates REST/SSE to internal gRPC services.
Capability-agnostic: discovers service identity via CapabilityResourceRegistry.

Endpoints:
- REST: /api/v1/chat/*, /api/v1/governance/*
- SSE: /api/v1/chat/stream/{session_id}
- Health: /health, /ready

The gateway is stateless - all state lives in the orchestrator/database.

Constitutional Compliance:
- Infrastructure R3: No domain logic - gateway is pure transport
- Infrastructure R4: Swappable - queries CapabilityResourceRegistry for identity
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import Request
import json
from prometheus_client import make_asgi_app

from mission_system.gateway.grpc_client import GrpcClientManager, set_grpc_client, get_grpc_client
from mission_system.gateway.websocket import (
    register_client,
    unregister_client,
    setup_websocket_subscriptions,
)
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import get_capability_resource_registry
from jeeves_infra.observability.tracing import init_tracing, instrument_fastapi, instrument_grpc_client, shutdown_tracing


def _get_service_identity() -> str:
    """Get service identity from CapabilityResourceRegistry (Infrastructure R4)."""
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
        self.cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
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
    - gRPC client connection to orchestrator
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
    instrument_grpc_client()
    _logger.info("tracing_initialized", service=service_name, jaeger=jaeger_endpoint)

    # Initialize gRPC client
    client = GrpcClientManager(
        orchestrator_host=config.orchestrator_host,
        orchestrator_port=config.orchestrator_port,
    )

    try:
        await client.connect()
        set_grpc_client(client)

        # Store in app state for dependency injection
        app.state.grpc_client = client

        # Note: InterruptService is injected by the composition root (mission_system.bootstrap)
        # The gateway does not create it directly to maintain proper layer separation.
        # If interrupt_service is not set, interrupt endpoints will return 503.
        if not hasattr(app.state, "interrupt_service"):
            _logger.warning("interrupt_service_not_configured",
                          hint="Interrupt endpoints will return 503 until service is injected")

        # Setup event bus subscriptions for WebSocket broadcasting
        await setup_websocket_subscriptions()
        _logger.info("websocket_subscriptions_configured")

        _logger.info("gateway_startup_complete", status="READY")
        yield

    except Exception as e:
        _logger.error("gateway_startup_failed", error=str(e))
        raise

    finally:
        # Shutdown
        _logger.info("gateway_shutdown_initiated")
        await client.disconnect()
        shutdown_tracing()
        _logger.info("gateway_shutdown_complete")


# =============================================================================
# FastAPI Application
# =============================================================================

_service_id = _get_service_identity()
app = FastAPI(
    title=f"{_service_id.replace('_', ' ').title()} Gateway",
    description="HTTP Gateway - translates REST/SSE to internal gRPC",
    version="4.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI with OpenTelemetry
instrument_fastapi(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    - gRPC connection to orchestrator
    - InterruptService availability
    """
    checks = {
        "orchestrator": "unknown",
        "interrupt_service": "unknown",
    }

    try:
        # Check gRPC client
        client = get_grpc_client()
        is_grpc_healthy = await client.health_check()
        checks["orchestrator"] = "connected" if is_grpc_healthy else "disconnected"
    except Exception as e:
        checks["orchestrator"] = f"error: {str(e)}"

    # Check InterruptService is initialized
    try:
        if hasattr(app.state, "interrupt_service") and app.state.interrupt_service is not None:
            checks["interrupt_service"] = "initialized"
        else:
            checks["interrupt_service"] = "not_initialized"
    except Exception as e:
        checks["interrupt_service"] = f"error: {str(e)}"

    # Determine overall status
    all_ok = (
        checks["orchestrator"] == "connected"
        and checks["interrupt_service"] == "initialized"
    )

    if all_ok:
        return JSONResponse({
            "status": "ready",
            **checks,
        })
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                **checks,
            }
        )


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

from mission_system.gateway.routers import chat, governance, interrupts

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
# WebSocket Support
# =============================================================================


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """
    WebSocket endpoint for real-time communication.

    The frontend connects here for real-time updates.
    Messages are JSON with format: {"event": "...", "payload": {...}}
    """
    _logger = get_current_logger()
    await websocket.accept()
    client_count = register_client(websocket)
    _logger.info("websocket_connected", client_count=client_count)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "event": "connected",
            "payload": {"message": "WebSocket connected successfully"}
        })

        while True:
            try:
                # Receive message from client
                data = await websocket.receive_json()
                msg_type = data.get("type", "unknown")
                payload = data.get("payload", {})

                _logger.debug("websocket_message", type=msg_type)

                # Handle different message types
                if msg_type == "ping":
                    await websocket.send_json({"event": "pong", "payload": {}})
                elif msg_type == "subscribe":
                    await websocket.send_json({
                        "event": "subscribed",
                        "payload": {"channel": payload.get("channel", "default")}
                    })
                else:
                    await websocket.send_json({
                        "event": "ack",
                        "payload": {"received": msg_type}
                    })

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json({
                    "event": "error",
                    "payload": {"message": "Invalid JSON"}
                })

    except Exception as e:
        _logger.error("websocket_error", error=str(e))
    finally:
        client_count = unregister_client(websocket)
        _logger.info("websocket_disconnected", client_count=client_count)


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
        "gateway.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
        log_level="info",
    )
