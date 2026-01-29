"""FastAPI server for the Mission System.

Provides HTTP endpoints for:
- Health checks (/health, /ready)
- Request processing (/api/v1/requests)
- WebSocket streaming (/ws)

Layer Extraction Compliant:
- No direct imports from capability layer (L5)
- Uses CapabilityResourceRegistry for dynamic discovery
- Orchestrator and tools are created via registered factories
"""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional
from uuid import uuid4

from mission_system.common import httpx_compat  # noqa: F401
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from jeeves_infra.gateway.websocket_manager import WebSocketEventManager
from mission_system.events.bridge import EventBridge
from mission_system.bootstrap import create_app_context, core_config_to_resource_quota
from jeeves_infra.wiring import create_llm_provider_factory, create_tool_executor
from mission_system.api.health import HealthChecker, health_check_to_dict
from jeeves_infra.settings import settings, get_settings
from jeeves_infra.database.client import DatabaseClientProtocol
from jeeves_infra.database.factory import create_database_client, reset_factory
from jeeves_infra.logging import get_current_logger
from mission_system.services.chat_service import ChatService
from jeeves_infra.observability.tracing import init_tracing, instrument_fastapi, shutdown_tracing

from jeeves_infra.protocols import (
    Envelope,
    RequestContext,
    create_envelope,
    TerminalReason,
    get_capability_resource_registry,
)
# KernelClient replaces ControlTower (control_tower deleted - Session 14)
from jeeves_infra.kernel_client import KernelClient

# SchedulingPriority is now a string enum: "REALTIME", "HIGH", "NORMAL", "LOW", "IDLE"
SchedulingPriority = str  # Type alias for migration
from mission_system.capability_wiring import wire_capabilities


class SubmitRequestBody(BaseModel):
    """Request submission payload."""

    user_message: str = Field(..., min_length=1, max_length=10000)
    user_id: str = Field(..., min_length=1, max_length=255)
    session_id: Optional[str] = Field(None, max_length=255)
    conversation_history: Optional[list] = None
    context: Optional[Dict[str, Any]] = None


class SubmitRequestResponse(BaseModel):
    """Response for request submission."""

    request_id: str
    status: str
    response_text: Optional[str] = None
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    thread_id: Optional[str] = None  # For resuming clarification flow
    confirmation_needed: bool = False
    confirmation_message: Optional[str] = None
    confirmation_id: Optional[str] = None


class ConfirmationResponse(BaseModel):
    """Request body for confirmation response."""

    confirmation_id: str = Field(..., min_length=1)
    user_response: str = Field(..., min_length=1, max_length=1000)
    user_id: str = Field(..., min_length=1, max_length=255)


class ClarificationBody(BaseModel):
    """Request body for clarification response.

    P1 Compliance: Allows users to respond to clarification requests
    when the system is uncertain about their query.
    """

    thread_id: str = Field(..., min_length=1, description="Thread ID from clarification request")
    clarification: str = Field(..., min_length=1, max_length=2000, description="User's clarification")
    user_id: str = Field(..., min_length=1, max_length=255)
    session_id: Optional[str] = Field(None, max_length=255)


class AppState:
    """Application-level state for dependency injection.

    Control Tower Integration:
    - control_tower: Central orchestration kernel (routes all requests)
    - event_bridge: Bridges kernel events to WebSocket streaming
    - orchestrator: Capability orchestrator (registered with Control Tower)

    Layer Extraction Compliant:
    - Uses Any type for orchestrator (capability-agnostic)
    - No direct imports from capability layer
    """

    def __init__(self) -> None:
        from typing import Union
        from jeeves_infra.database.client import DatabaseClientProtocol
        from jeeves_infra.postgres.client import PostgreSQLClient
        self.db: Optional[Union[DatabaseClientProtocol, PostgreSQLClient]] = None
        self.tool_catalog = None  # Tool catalog (single source of truth)

        # Control Tower - central orchestration
        self.control_tower: Optional[ControlTower] = None
        self.event_bridge: Optional[EventBridge] = None

        # Services (registered with Control Tower)
        self.orchestrator: Optional[Any] = None  # Capability-specific orchestrator (dynamic)
        self.health_checker: Optional[HealthChecker] = None
        self.event_manager: Optional[WebSocketEventManager] = None
        self.chat_service: Optional[ChatService] = None
        self.tool_health_service = None  # L7 governance service
        self.shutdown_event: asyncio.Event = asyncio.Event()


# Lazy initialization - no module-level instantiation (ADR-001 compliance)
_app_state: Optional[AppState] = None


def get_app_state() -> AppState:
    """Get the global app state instance.

    Creates a new AppState instance lazily if none exists.
    Prefer dependency injection over this global getter for testability.

    Returns:
        Global AppState instance
    """
    global _app_state
    if _app_state is None:
        _app_state = AppState()
    return _app_state


def set_app_state(state: AppState) -> None:
    """Set the global app state instance.

    Use at bootstrap time to inject a pre-configured AppState.
    Primarily for testing purposes.

    Args:
        state: AppState instance to use as global
    """
    global _app_state
    _app_state = state


def reset_app_state() -> None:
    """Reset the global app state instance.

    Forces re-creation on next get_app_state() call.
    Primarily for testing purposes.
    """
    global _app_state
    _app_state = None


# Module-level accessor for backward compatibility
# All internal code should use get_app_state() for testability
def __getattr__(name: str):
    """Module-level __getattr__ to provide lazy app_state access."""
    if name == "app_state":
        return get_app_state()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle manager for FastAPI application.

    Database Ownership Model:
    - If app_state.db is pre-injected (async tests): use it, don't close on shutdown
    - Otherwise (production, sync tests): create our own, close on shutdown

    This ensures clean separation between test fixtures and production lifecycle.
    """
    app_state = get_app_state()
    _logger = get_current_logger()
    current_settings = get_settings()

    _logger.info(
        "server_startup_initiated",
        database_backend=current_settings.database_backend,
        vector_backend=current_settings.vector_backend,
        llm_provider=current_settings.llm_provider,
        chat_enabled=current_settings.chat_enabled,
    )

    # Initialize tracing
    jaeger_endpoint = os.getenv("JAEGER_ENDPOINT", "jaeger:4317")
    service_name = "jeeves-orchestrator"
    init_tracing(service_name, jaeger_endpoint)
    _logger.info("tracing_initialized", service=service_name, jaeger=jaeger_endpoint)

    # Database initialization with clear ownership
    db = None
    db_owned_by_lifespan = False

    if app_state.db is not None:
        # Pre-injected database (async tests in same event loop)
        try:
            await app_state.db.fetch_one("SELECT 1")
            db = app_state.db
            db_owned_by_lifespan = False  # Fixture owns cleanup
            _logger.info("using_preinjected_database", backend=current_settings.database_backend)
        except (RuntimeError, Exception) as e:
            # Event loop mismatch (sync TestClient) or connection issue
            # Create our own connection for this event loop
            _logger.info(
                "preinjected_db_unusable",
                backend=current_settings.database_backend,
                reason=str(e)[:100]
            )
            reset_factory()  # Clear any stale global state
            db = None

    if db is None:
        # Create new connection (production or sync tests)
        db = await create_database_client(current_settings)
        db_owned_by_lifespan = True  # We own cleanup
        _logger.info("database_client_created", backend=current_settings.database_backend)

    # Initialize event manager (needed for real-time updates)
    event_manager = WebSocketEventManager()

    # Wire capabilities before querying registry
    _logger.info("wiring_capabilities")
    wire_capabilities()

    # Initialize Control Tower (central orchestration kernel)
    _logger.info("initializing_control_tower")
    app_context = create_app_context()
    control_tower = app_context.control_tower

    # Get capability registry for dynamic discovery (layer extraction support)
    capability_registry = get_capability_resource_registry()
    services = capability_registry.get_services()
    default_service = capability_registry.get_default_service() or "default"

    _logger.info(
        "control_tower_initialized",
        default_service=default_service,
        registered_capabilities=capability_registry.list_capabilities(),
    )

    # Initialize tools via capability registry (no direct imports from capability)
    tools_config = capability_registry.get_tools()
    if tools_config:
        _logger.info("initializing_tools_from_registry")
        tool_instances = tools_config.initializer(db=db)
        catalog = tool_instances["catalog"]
    else:
        _logger.warning("no_tools_registered", message="No capability tools in registry")
        catalog = None

    # Create tool executor from catalog
    tool_executor = create_tool_executor(catalog) if catalog else None

    # Initialize orchestrator via capability registry (no direct imports from capability)
    orchestrator_config = capability_registry.get_orchestrator()
    llm_factory = create_llm_provider_factory(current_settings)

    if orchestrator_config:
        _logger.info("initializing_orchestrator_from_registry")
        orchestrator = orchestrator_config.factory(
            llm_provider_factory=llm_factory,
            tool_executor=tool_executor,
            logger=_logger,
            persistence=db,
            control_tower=control_tower,
        )
    else:
        _logger.warning("no_orchestrator_registered", message="No capability orchestrator in registry")
        orchestrator = None

    _logger.info(
        "orchestrator_initialized",
        resource_tracking_enabled=orchestrator is not None,
    )

    # Register services with Control Tower from capability registry
    if orchestrator:
        for service_config in services:
            _logger.info("registering_service", service_id=service_config.service_id)
            control_tower.register_service(
                name=service_config.service_id,
                service_type=service_config.service_type,
                handler=orchestrator.get_dispatch_handler(),  # Handler from orchestrator
                capabilities=service_config.capabilities,
                max_concurrent=service_config.max_concurrent,
            )
            _logger.info("service_registered", service_id=service_config.service_id)

        # Fallback: if no services registered, register default service
        if not services:
            _logger.warning("no_services_in_registry", message="Registering default service")
            control_tower.register_service(
                name="default",
                service_type="flow",
                handler=orchestrator.get_dispatch_handler(),
                capabilities=["analyze", "clarification"],
                max_concurrent=10,
            )
    else:
        _logger.error("no_orchestrator_available", message="Cannot register services without orchestrator")

    # Create EventBridge to connect Control Tower events to WebSocket
    _logger.info("initializing_event_bridge")
    event_bridge = EventBridge(
        event_aggregator=control_tower.events,
        websocket_manager=event_manager,
        logger=_logger,
    )
    event_bridge.start()
    _logger.info("event_bridge_started")

    health_checker = HealthChecker(db)
    _logger.info("health_checker_initialized")

    # Initialize ChatService for Chat UI integration
    _logger.info("initializing_chat_service")
    chat_service = ChatService(db, event_manager)
    _logger.info("chat_service_initialized")

    # Initialize ToolHealthService for L7 governance
    _logger.info("initializing_tool_health_service")
    from jeeves_infra.memory.services.tool_health_service import ToolHealthService
    tool_health_service = ToolHealthService(db)
    await tool_health_service.ensure_initialized()
    _logger.info("tool_health_service_initialized")

    # Store in app state
    app_state.db = db
    app_state.tool_catalog = catalog
    app_state.control_tower = control_tower
    app_state.event_bridge = event_bridge
    app_state.orchestrator = orchestrator
    app_state.health_checker = health_checker
    app_state.event_manager = event_manager
    app_state.chat_service = chat_service
    app_state.tool_health_service = tool_health_service

    # Setup graceful shutdown handlers
    _setup_signal_handlers()

    # P6: Observable - Log successful startup
    _logger.info(
        "server_startup_complete",
        tools_registered=len(catalog.get_all_tool_ids()) if catalog else 0,
        status="READY"
    )

    try:
        yield
    finally:
        # Shutdown - wait for in-flight requests to complete
        _logger.info("server_shutdown_initiated")

        # Stop event bridge
        if app_state.event_bridge:
            app_state.event_bridge.stop()
            _logger.info("event_bridge_stopped")

        # Only close database if we created it (not if injected by test fixture)
        if db_owned_by_lifespan and app_state.db:
            await app_state.db.close()
            _logger.info("database_connection_closed")

        # Shutdown tracing
        shutdown_tracing()
        _logger.info("tracing_shutdown_complete")

        _logger.info("server_shutdown_complete")


def _setup_signal_handlers() -> None:
    """Setup handlers for graceful shutdown on SIGTERM/SIGINT."""
    _logger = get_current_logger()

    def handle_signal(sig: int, frame: Any) -> None:
        _logger.info("graceful_shutdown_initiated", signal=sig)
        get_app_state().shutdown_event.set()
        # For immediate shutdown in tests, exit on second signal
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
    except ValueError:
        # Signal handlers can only be set in the main thread
        # This is expected when running in test environments with TestClient
        pass


from mission_system.config.constants import PLATFORM_NAME, PLATFORM_DESCRIPTION, PLATFORM_VERSION

app = FastAPI(
    title=f"{PLATFORM_NAME} API",
    description=PLATFORM_DESCRIPTION,
    version=PLATFORM_VERSION,
    lifespan=lifespan,
)

# Instrument FastAPI for automatic trace propagation
instrument_fastapi(app)

# Mount static files for UI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request

try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="api/templates")
except RuntimeError:
    # Directories don't exist (e.g., in tests)
    templates = None

# Mount Chat router if feature flag enabled
if settings.chat_enabled:
    from mission_system.api.chat import router as chat_router, get_chat_service

    # Override dependency to use app_state.chat_service
    app.dependency_overrides[get_chat_service] = lambda: get_app_state().chat_service
    app.include_router(chat_router)

    # Add Chat UI route
    @app.get("/chat", response_class=HTMLResponse)
    async def chat_ui(request: Request):
        """Serve Chat UI."""
        if not templates:
            raise HTTPException(
                status_code=503,
                detail="Chat UI templates not available"
            )

        return templates.TemplateResponse(request, "chat.html", {"active_page": "chat"})

# Mount Governance router (L7 System Introspection)
# Always enabled - governance is a core feature for observability (P6)
from mission_system.api.governance import router as governance_router, get_tool_health_service

# Override dependency to use app_state.tool_health_service
app.dependency_overrides[get_tool_health_service] = lambda: get_app_state().tool_health_service
app.include_router(governance_router)

get_current_logger().info("governance_router_mounted", endpoints=[
    "/api/v1/governance/health",
    "/api/v1/governance/tools/{tool_name}",
    "/api/v1/governance/dashboard"
])

# Add Governance UI route
@app.get("/governance", response_class=HTMLResponse)
async def governance_ui(request: Request):
    """Serve Governance UI."""
    if not templates:
        raise HTTPException(
            status_code=503,
            detail="Governance UI templates not available"
        )

    return templates.TemplateResponse(request, "governance.html", {"active_page": "governance"})


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness probe - is the service running?

    Returns:
        200: Service is alive
        500: Service is down (should trigger pod restart)
    """
    app_state = get_app_state()
    if not app_state.health_checker:
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "message": "Service not initialized"},
        )

    result = await app_state.health_checker.check_liveness()
    return JSONResponse(
        status_code=200,
        content=health_check_to_dict(result),
    )


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe - can the service accept traffic?

    Returns:
        200: Service is ready (healthy/degraded)
        503: Service is not ready (should be removed from load balancer)
    """
    app_state = get_app_state()
    if not app_state.health_checker:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "message": "Service not initialized"},
        )

    result = await app_state.health_checker.check_readiness()

    # Return 503 if unhealthy (should be removed from load balancer)
    # Return 200 for healthy or degraded (can still serve traffic)
    status_code = 503 if result.status == "unhealthy" else 200

    return JSONResponse(
        status_code=status_code,
        content=health_check_to_dict(result),
    )


# =============================================================================
# Request Submission Helpers
# =============================================================================


def _validate_submit_request_state() -> None:
    """Validate server state for request submission."""
    app_state = get_app_state()
    if app_state.shutdown_event.is_set():
        raise HTTPException(status_code=503, detail="Service is shutting down")
    if not app_state.control_tower:
        raise HTTPException(status_code=503, detail="Control Tower not ready")


def _resolve_capability(body: SubmitRequestBody) -> str:
    """Resolve and validate the capability to use for the request."""
    capability_registry = get_capability_resource_registry()
    capabilities = capability_registry.list_capabilities()

    requested_capability = None
    if body.context and isinstance(body.context, dict):
        requested_capability = body.context.get("capability")

    if requested_capability:
        if requested_capability not in capabilities:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown capability: {requested_capability}",
            )
        return requested_capability

    if len(capabilities) == 1:
        return capabilities[0]

    raise HTTPException(
        status_code=400,
        detail="capability is required when multiple capabilities are registered",
    )


def _resolve_request_id(body: SubmitRequestBody) -> str:
    """Extract or generate request ID from request body."""
    if body.context and isinstance(body.context, dict):
        request_id = body.context.get("request_id")
        if request_id:
            return request_id
    return f"req_{uuid4().hex[:16]}"


def _determine_response_status(result_envelope: Envelope) -> tuple[str, Optional[str], bool]:
    """Determine response status from result envelope.

    Returns:
        Tuple of (status, response_text, clarification_needed)
    """
    from jeeves_infra.protocols import InterruptKind

    clarification_needed = (
        result_envelope.interrupt_pending
        and result_envelope.interrupt
        and result_envelope.interrupt.kind == InterruptKind.CLARIFICATION
    )

    if clarification_needed:
        return "clarification_needed", None, True

    integration = result_envelope.outputs.get("integration", {})
    if result_envelope.terminal_reason == TerminalReason.COMPLETED:
        return "completed", integration.get("final_response"), False

    return "failed", result_envelope.termination_reason, False


def _get_confirmation_settings() -> tuple[bool, Optional[Any]]:
    """Get confirmation settings from capability registry.

    Returns:
        Tuple of (requires_confirmation, service_config)
    """
    capability_registry = get_capability_resource_registry()
    default_service = capability_registry.get_default_service()
    service_config = capability_registry.get_service_config(default_service) if default_service else None
    requires_confirmation = service_config.requires_confirmation if service_config else False
    return requires_confirmation, service_config


def _build_submit_response(
    result_envelope: Envelope,
    status: str,
    response_text: Optional[str],
    clarification_needed: bool,
    requires_confirmation: bool,
    service_config: Optional[Any],
) -> SubmitRequestResponse:
    """Build the submit request response object."""
    # Get clarification question from interrupt if present
    clarification_question = None
    if result_envelope.interrupt and result_envelope.interrupt.question:
        clarification_question = result_envelope.interrupt.question

    return SubmitRequestResponse(
        request_id=result_envelope.request_id or "",
        status=status,
        response_text=response_text,
        clarification_needed=clarification_needed,
        clarification_question=clarification_question,
        thread_id=result_envelope.envelope_id if clarification_needed else None,
        confirmation_needed=requires_confirmation and not service_config.is_readonly if service_config else False,
        confirmation_message=None,
        confirmation_id=None,
    )


@app.post("/api/v1/requests", response_model=SubmitRequestResponse)
async def submit_request(body: SubmitRequestBody) -> SubmitRequestResponse:
    """Submit a new capability request for processing.

    Routes through Control Tower for lifecycle management, resource tracking,
    and service dispatch. The registered capability determines request behavior.

    Args:
        body: Request submission payload

    Returns:
        SubmitRequestResponse: Result of request processing

    Raises:
        HTTPException: If orchestration fails
    """
    app_state = get_app_state()
    _validate_submit_request_state()

    try:
        # Resolve capability and request ID
        capability_id = _resolve_capability(body)
        request_id = _resolve_request_id(body)
        session_id = body.session_id or f"session_{body.user_id}"

        # Build request context and envelope
        request_context = RequestContext(
            request_id=request_id,
            capability=capability_id,
            session_id=session_id,
            user_id=body.user_id,
        )

        envelope = create_envelope(
            raw_input=body.user_message,
            request_context=request_context,
            metadata=body.context,
        )

        # Submit to Control Tower
        result_envelope = await app_state.control_tower.submit_request(
            envelope=envelope,
            priority=SchedulingPriority.NORMAL,
        )

        # Determine response status and build response
        status, response_text, clarification_needed = _determine_response_status(result_envelope)
        requires_confirmation, service_config = _get_confirmation_settings()

        return _build_submit_response(
            result_envelope,
            status,
            response_text,
            clarification_needed,
            requires_confirmation,
            service_config,
        )

    except HTTPException:
        raise
    except Exception as exc:
        get_current_logger().error(
            "submit_request_error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/confirmations", response_model=SubmitRequestResponse)
async def submit_confirmation(body: ConfirmationResponse) -> SubmitRequestResponse:
    """Submit user's response to a confirmation request.

    Confirmation handling depends on the registered capability's configuration.
    Read-only capabilities do not require confirmations.

    Args:
        body: Confirmation response payload

    Returns:
        SubmitRequestResponse: Result of processing the confirmation

    Raises:
        HTTPException: 404 if capability doesn't support confirmations
    """
    # Check if capability requires confirmations (from registry)
    capability_registry = get_capability_resource_registry()
    default_service = capability_registry.get_default_service()
    service_config = capability_registry.get_service_config(default_service) if default_service else None

    # If capability is read-only or doesn't require confirmations, reject
    if service_config and (service_config.is_readonly or not service_config.requires_confirmation):
        raise HTTPException(
            status_code=404,
            detail=f"{service_config.service_id} does not require confirmations"
        )

    # TODO: Implement confirmation handling for write-capable capabilities
    # For now, return not implemented
    raise HTTPException(
        status_code=501,
        detail="Confirmation handling not yet implemented for this capability"
    )


@app.post("/api/v1/chat/clarifications", response_model=SubmitRequestResponse)
async def submit_clarification(body: ClarificationBody) -> SubmitRequestResponse:
    """Submit user's clarification response to resume interrupted workflow.

    Routes through Control Tower's resume_request for lifecycle continuity.

    P1 Compliance: When the system is uncertain about a query, it requests
    clarification. This endpoint allows users to provide that clarification
    and resume the analysis flow.

    Args:
        body: Clarification response payload with thread_id and user's response

    Returns:
        SubmitRequestResponse: Result of resuming the analysis

    Raises:
        HTTPException: If thread not found or processing fails
    """
    app_state = get_app_state()
    if app_state.shutdown_event.is_set():
        raise HTTPException(status_code=503, detail="Service is shutting down")

    if not app_state.control_tower:
        raise HTTPException(status_code=503, detail="Control Tower not ready")

    try:
        # Resume through Control Tower with clarification response
        # thread_id is the envelope_id (pid) from the original request
        result_envelope = await app_state.control_tower.resume_request(
            pid=body.thread_id,
            response_data={"clarification_response": body.clarification},
        )

        # Extract result from envelope
        integration = result_envelope.outputs.get("integration", {})

        # Check for further clarification (EventBridge handles WebSocket broadcast)
        # Use unified interrupt mechanism
        from jeeves_infra.protocols import InterruptKind
        clarification_needed = (
            result_envelope.interrupt_pending
            and result_envelope.interrupt
            and result_envelope.interrupt.kind == InterruptKind.CLARIFICATION
        )

        # Determine status
        if clarification_needed:
            status = "clarification_needed"
            response_text = None
        elif result_envelope.terminal_reason == TerminalReason.COMPLETED:
            status = "completed"
            response_text = integration.get("final_response")
        else:
            status = "failed"
            response_text = result_envelope.termination_reason

        return SubmitRequestResponse(
            request_id=result_envelope.request_id or "",
            status=status,
            response_text=response_text,
            clarification_needed=clarification_needed,
            clarification_question=result_envelope.clarification_question,
            thread_id=body.thread_id if clarification_needed else None,
        )

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        get_current_logger().error(
            "submit_clarification_error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None) -> None:
    """WebSocket endpoint for real-time event streaming.

    Clients connect to receive orchestration events from the registered capability.
    Event types depend on the capability's pipeline stages (configured in registry).

    Common event patterns:
    - {agent}.started / {agent}.completed - Agent lifecycle events
    - tool.called / tool.completed - Tool invocation events
    - orchestrator.completed / orchestrator.failed - Overall status

    Args:
        websocket: WebSocket connection
        token: Optional authentication token
    """
    app_state = get_app_state()
    if not app_state.event_manager:
        await websocket.close(code=1011, reason="Service not ready")
        return

    await websocket.accept()

    try:
        # Register connection
        await app_state.event_manager.register(websocket, token=token)

        # Send heartbeat and listen for client messages
        while True:
            try:
                # Wait for message or timeout for heartbeat
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=app_state.event_manager.heartbeat_interval,
                )

                # Handle heartbeat pings from client
                if message == "ping":
                    await app_state.event_manager.heartbeat(websocket)
                    await websocket.send_text("pong")

            except asyncio.TimeoutError:
                # Send heartbeat ping to client
                await websocket.send_text("ping")

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        get_current_logger().error("websocket_error", error=str(exc), error_type=type(exc).__name__)
    finally:
        # Unregister on disconnect
        if app_state.event_manager:
            await app_state.event_manager.unregister(websocket)


# ============================================================
# Control Tower Observability Endpoints (Phase 3)
# ============================================================


class RequestStatusResponse(BaseModel):
    """Response for request status query."""

    pid: str
    state: str
    priority: str
    current_stage: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    resource_usage: Optional[Dict[str, Any]] = None
    quota: Optional[Dict[str, Any]] = None
    pending_interrupt: Optional[str] = None


class SystemMetricsResponse(BaseModel):
    """Response for system metrics."""

    total_processes: int = 0
    active_processes: int = 0
    system_llm_calls: int = 0
    system_tool_calls: int = 0
    system_tokens_in: int = 0
    system_tokens_out: int = 0
    processes_by_state: Dict[str, int] = {}


@app.get("/api/v1/requests/{pid}/status", response_model=RequestStatusResponse)
async def get_request_status(pid: str) -> RequestStatusResponse:
    """Get the status of a request via Control Tower.

    Uses Control Tower's process lifecycle and resource tracking
    to provide detailed request status.

    Args:
        pid: Process/envelope ID

    Returns:
        RequestStatusResponse with current status

    Raises:
        404: If request not found
        503: If Control Tower not ready
    """
    app_state = get_app_state()
    if not app_state.control_tower:
        raise HTTPException(status_code=503, detail="Control Tower not ready")

    # Get process from lifecycle manager
    pcb = app_state.control_tower.lifecycle.get_process(pid)
    if not pcb:
        raise HTTPException(status_code=404, detail=f"Request not found: {pid}")

    # Get resource usage and quota
    usage = app_state.control_tower.resources.get_usage(pid)
    quota = app_state.control_tower.resources.get_quota(pid)

    return RequestStatusResponse(
        pid=pcb.pid,
        state=pcb.state.value,
        priority=pcb.priority.value,
        current_stage=pcb.current_stage,
        created_at=pcb.created_at.isoformat() if pcb.created_at else None,
        started_at=pcb.started_at.isoformat() if pcb.started_at else None,
        completed_at=pcb.completed_at.isoformat() if pcb.completed_at else None,
        resource_usage={
            "llm_calls": usage.llm_calls,
            "tool_calls": usage.tool_calls,
            "agent_hops": usage.agent_hops,
            "tokens_in": usage.tokens_in,
            "tokens_out": usage.tokens_out,
            "elapsed_seconds": usage.elapsed_seconds,
        } if usage else None,
        quota={
            "max_llm_calls": quota.max_llm_calls,
            "max_tool_calls": quota.max_tool_calls,
            "max_agent_hops": quota.max_agent_hops,
            "timeout_seconds": quota.timeout_seconds,
        } if quota else None,
        pending_interrupt=pcb.pending_interrupt.value if pcb.pending_interrupt else None,
    )


@app.get("/api/v1/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics() -> SystemMetricsResponse:
    """Get system-wide metrics from Control Tower.

    Provides aggregated metrics across all processes:
    - Process counts (total, active)
    - Resource consumption (LLM calls, tokens)
    - Process state distribution

    Returns:
        SystemMetricsResponse with system metrics

    Raises:
        503: If Control Tower not ready
    """
    app_state = get_app_state()
    if not app_state.control_tower:
        raise HTTPException(status_code=503, detail="Control Tower not ready")

    # Get resource tracker system usage
    system_usage = app_state.control_tower.resources.get_system_usage()

    # Get process state counts from lifecycle manager
    from control_tower.types import ProcessState

    processes_by_state: Dict[str, int] = {}
    for state in ProcessState:
        processes = app_state.control_tower.lifecycle.list_processes(state=state)
        if processes:
            processes_by_state[state.value] = len(processes)

    return SystemMetricsResponse(
        total_processes=system_usage.get("total_processes", 0),
        active_processes=system_usage.get("active_processes", 0),
        system_llm_calls=system_usage.get("system_llm_calls", 0),
        system_tool_calls=system_usage.get("system_tool_calls", 0),
        system_tokens_in=system_usage.get("system_tokens_in", 0),
        system_tokens_out=system_usage.get("system_tokens_out", 0),
        processes_by_state=processes_by_state,
    )


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "service": PLATFORM_NAME,
        "version": PLATFORM_VERSION,
        "description": PLATFORM_DESCRIPTION,
        "health": "/health",
        "ready": "/ready",
        "api": {
            "requests": "/api/v1/requests",
            "request_status": "/api/v1/requests/{pid}/status",
            "metrics": "/api/v1/metrics",
        },
        "websocket": "/ws",
        "ui": {
            "chat": "/chat",
            "governance": "/governance",
        },
        "api_docs": "/docs",
        "governance": "/api/v1/governance/dashboard",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )
