"""Composition Root - Build AppContext and inject dependencies.

ADR-001 Decision 3: Singleton Elimination via AppContext
This module is the COMPOSITION ROOT for the Jeeves application.
It is the ONLY place where concrete implementations are instantiated
and wired together.

All configuration is passed via AppContext - no global state.

Usage:
    from jeeves_infra.bootstrap import create_app_context

    # At application startup
    app_context = create_app_context()

    # Use in API server
    app.state.context = app_context

    # Pass to components
    service = MyService(context=app_context)

    # Access configuration via context
    bounds = app_context.core_config.context_bounds
"""

import os
from contextvars import ContextVar
from typing import Optional, TYPE_CHECKING

from jeeves_infra.context import AppContext, SystemClock
from jeeves_infra.logging import configure_logging
from jeeves_infra.settings import Settings, get_settings
from jeeves_infra.feature_flags import FeatureFlags, get_feature_flags
from jeeves_infra.protocols import ExecutionConfig, ContextBounds, OrchestrationFlags
from jeeves_infra.protocols import get_capability_resource_registry
from jeeves_infra.config.registry import ConfigRegistry

# KernelClient for Rust kernel integration
from jeeves_infra.kernel_client import KernelClient, DEFAULT_KERNEL_ADDRESS

if TYPE_CHECKING:
    from jeeves_infra.protocols import AgentToolAccessProtocol


# =============================================================================
# Request PID Context (per-request process tracking)
# =============================================================================

_request_pid: ContextVar[Optional[str]] = ContextVar("request_pid", default=None)


def set_request_pid(pid: str) -> None:
    """Set the current request's process ID."""
    _request_pid.set(pid)


def get_request_pid() -> Optional[str]:
    """Get the current request's process ID."""
    return _request_pid.get()


def clear_request_pid() -> None:
    """Clear the current request's process ID."""
    _request_pid.set(None)


def request_pid_context(pid: str):
    """Context manager for request PID."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        token = _request_pid.set(pid)
        try:
            yield pid
        finally:
            _request_pid.reset(token)

    return _ctx()


def _parse_bool(value: str, default: bool = True) -> bool:
    """Parse boolean from environment variable string."""
    return value.lower() == "true" if value else default



def create_core_config_from_env() -> ExecutionConfig:
    """Create ExecutionConfig from environment variables.

    Environment Variables:
        CORE_MAX_ITERATIONS: Max pipeline iterations
        CORE_MAX_LLM_CALLS: Max LLM calls per request
        CORE_MAX_AGENT_HOPS: Max agent transitions
        CORE_ENABLE_TELEMETRY: Enable telemetry
        CORE_ENABLE_CHECKPOINTS: Enable checkpointing
        CORE_DEBUG_MODE: Enable debug mode
        CORE_MAX_INPUT_TOKENS: Max input tokens
        CORE_MAX_OUTPUT_TOKENS: Max output tokens
        CORE_MAX_CONTEXT_TOKENS: Max context window tokens
        CORE_RESERVED_TOKENS: Reserved tokens for system

    Returns:
        ExecutionConfig with environment-parsed values
    """
    return ExecutionConfig(
        max_iterations=int(os.getenv("CORE_MAX_ITERATIONS", "3")),
        max_llm_calls=int(os.getenv("CORE_MAX_LLM_CALLS", "10")),
        max_agent_hops=int(os.getenv("CORE_MAX_AGENT_HOPS", "21")),
        enable_telemetry=_parse_bool(os.getenv("CORE_ENABLE_TELEMETRY", "true")),
        enable_checkpoints=_parse_bool(os.getenv("CORE_ENABLE_CHECKPOINTS", "false"), default=False),
        debug_mode=_parse_bool(os.getenv("CORE_DEBUG_MODE", "false"), default=False),
        context_bounds=ContextBounds(
            max_input_tokens=int(os.getenv("CORE_MAX_INPUT_TOKENS", "4096")),
            max_output_tokens=int(os.getenv("CORE_MAX_OUTPUT_TOKENS", "2048")),
            max_context_tokens=int(os.getenv("CORE_MAX_CONTEXT_TOKENS", "16384")),
            reserved_tokens=int(os.getenv("CORE_RESERVED_TOKENS", "512")),
        ),
    )


def create_orchestration_flags_from_env() -> OrchestrationFlags:
    """Create OrchestrationFlags from environment variables.

    Environment Variables:
        ORCH_ENABLE_PARALLEL_AGENTS: Enable parallel agent execution
        ORCH_ENABLE_CHECKPOINTS: Enable checkpoint creation
        ORCH_ENABLE_DISTRIBUTED: Enable distributed mode
        ORCH_ENABLE_TELEMETRY: Enable telemetry
        ORCH_MAX_CONCURRENT_AGENTS: Max concurrent agents
        ORCH_CHECKPOINT_INTERVAL: Checkpoint interval in seconds

    Returns:
        OrchestrationFlags with environment-parsed values
    """
    return OrchestrationFlags(
        enable_parallel_agents=_parse_bool(os.getenv("ORCH_ENABLE_PARALLEL_AGENTS", "false"), default=False),
        enable_checkpoints=_parse_bool(os.getenv("ORCH_ENABLE_CHECKPOINTS", "false"), default=False),
        enable_distributed=_parse_bool(os.getenv("ORCH_ENABLE_DISTRIBUTED", "false"), default=False),
        enable_telemetry=_parse_bool(os.getenv("ORCH_ENABLE_TELEMETRY", "true")),
        max_concurrent_agents=int(os.getenv("ORCH_MAX_CONCURRENT_AGENTS", "4")),
        checkpoint_interval_seconds=int(os.getenv("ORCH_CHECKPOINT_INTERVAL", "30")),
    )


def create_app_context(
    settings: Optional[Settings] = None,
    feature_flags: Optional[FeatureFlags] = None,
    core_config: Optional[ExecutionConfig] = None,
    orchestration_flags: Optional[OrchestrationFlags] = None,
) -> AppContext:
    """Create AppContext once per process.

    COMPOSITION ROOT: This is the ONLY place where concrete
    implementations are instantiated and wired together.

    Args:
        settings: Optional pre-configured settings. Uses get_settings() if None.
        feature_flags: Optional pre-configured flags. Uses get_feature_flags() if None.
        core_config: Optional ExecutionConfig. Parses from env if None.
        orchestration_flags: Optional OrchestrationFlags. Parses from env if None.

    Returns:
        AppContext with all dependencies wired.

    Usage:
        # At application startup
        app_context = create_app_context()

        # Or with custom config
        app_context = create_app_context(
            core_config=ExecutionConfig(max_iterations=5),
        )
    """
    # Build settings (from env/files)
    if settings is None:
        settings = get_settings()

    # Build feature flags
    if feature_flags is None:
        feature_flags = get_feature_flags()

    # Build core config from environment
    if core_config is None:
        core_config = create_core_config_from_env()

    # Build orchestration flags from environment
    if orchestration_flags is None:
        orchestration_flags = create_orchestration_flags_from_env()

    # Configure logging based on settings
    configure_logging(
        level=settings.log_level,
        json_output=True,
        enable_otel=feature_flags.enable_tracing,
    )

    # Build root logger (jeeves_infra provides structlog wrapper)
    from jeeves_infra.logging import create_logger
    root_logger = create_logger("jeeves")

    # Get default service from capability registry (layer extraction support, Constitution R4)
    capability_registry = get_capability_resource_registry()
    default_service = capability_registry.get_default_service() or "jeeves"

    # Initialize OpenTelemetry if tracing is enabled
    otel_adapter = None
    if feature_flags.enable_tracing:
        from jeeves_infra.observability.otel_adapter import (
            init_global_otel,
            get_global_otel_adapter,
        )
        # Initialize global OTEL adapter with service name from registry
        # Note: For production, configure exporter via OTEL_EXPORTER_JAEGER_ENDPOINT
        init_global_otel(
            service_name=default_service,
            service_version="1.0.0",
            exporter=None,  # Uses ConsoleSpanExporter by default
        )
        otel_adapter = get_global_otel_adapter()
        root_logger.info(
            "otel_initialized",
            service_name=default_service,
            enabled=otel_adapter is not None and otel_adapter.enabled,
        )

    # Eagerly provision config registry
    config_registry = ConfigRegistry()

    # Eagerly provision LLM provider factory (required — fail loud)
    from jeeves_infra.llm.factory import create_llm_provider_factory as _create_llm_factory
    llm_provider_factory = _create_llm_factory(settings)
    root_logger.info("llm_provider_factory_provisioned", adapter=settings.jeeves_llm_adapter)

    # Eagerly provision kernel client (required — fail loud)
    from jeeves_infra.ipc import IpcTransport
    kernel_address = os.getenv("JEEVES_KERNEL_ADDRESS", DEFAULT_KERNEL_ADDRESS)
    host, _, port_str = kernel_address.rpartition(":")
    transport = IpcTransport(host=host or "127.0.0.1", port=int(port_str or 50051))
    kernel_client = KernelClient(transport)
    root_logger.info("kernel_client_provisioned", address=kernel_address)

    # Wire state backend (sync constructors — async init deferred to gateway lifespan)
    state_backend = None
    distributed_bus = None

    if feature_flags.use_redis_state:
        from jeeves_infra.redis.connection_manager import ConnectionManager
        state_backend = ConnectionManager(settings, logger=root_logger)
        root_logger.info("state_backend_provisioned", backend="redis_connection_manager")

        if feature_flags.enable_distributed_mode:
            from jeeves_infra.redis.client import get_redis_client
            from jeeves_infra.distributed.redis_bus import RedisDistributedBus
            redis_client = get_redis_client(settings.redis_url)
            distributed_bus = RedisDistributedBus(redis_client, logger=root_logger)
            root_logger.info("distributed_bus_provisioned", backend="redis")
    else:
        from jeeves_infra.redis.connection_manager import InMemoryStateBackend
        state_backend = InMemoryStateBackend(logger=root_logger)
        root_logger.info("state_backend_provisioned", backend="in_memory")

    root_logger.info(
        "app_context_created",
        default_service=default_service,
        max_llm_calls=core_config.max_llm_calls,
        max_iterations=core_config.max_iterations,
        max_agent_hops=core_config.max_agent_hops,
    )

    return AppContext(
        settings=settings,
        feature_flags=feature_flags,
        logger=root_logger,
        clock=SystemClock(),
        config_registry=config_registry,
        llm_provider_factory=llm_provider_factory,
        core_config=core_config,
        orchestration_flags=orchestration_flags,
        kernel_client=kernel_client,
        state_backend=state_backend,
        distributed_bus=distributed_bus,
    )



def create_tool_executor_with_access(
    tool_registry,
    app_context: AppContext,
    access_checker: Optional["AgentToolAccessProtocol"] = None,
):
    """Create ToolExecutor with access control.

    Args:
        tool_registry: ToolRegistryProtocol implementation
        app_context: AppContext for logger
        access_checker: Optional AgentToolAccessProtocol for access control

    Returns:
        ToolExecutor configured with access control
    """
    from jeeves_infra.wiring import ToolExecutor

    return ToolExecutor(
        registry=tool_registry,
        logger=app_context.get_bound_logger("tool_executor"),
        access_checker=access_checker,
    )



async def sync_quota_defaults_to_kernel(app_context: AppContext) -> None:
    """Push env-parsed quota defaults to the kernel (single source of truth).

    Call this once at startup after the kernel is running and the
    transport is connected. The kernel merges non-zero fields, so only
    the values present in create_core_config_from_env() are overwritten.

    Args:
        app_context: AppContext with connected kernel_client.
    """
    cfg = app_context.core_config
    try:
        await app_context.kernel_client.set_quota_defaults(
            max_llm_calls=cfg.max_llm_calls,
            max_iterations=cfg.context_bounds.max_input_tokens,
            max_input_tokens=cfg.context_bounds.max_input_tokens,
            max_output_tokens=cfg.context_bounds.max_output_tokens,
            max_context_tokens=cfg.context_bounds.max_context_tokens,
            max_agent_hops=cfg.max_agent_hops,
        )
        app_context.logger.info("quota_defaults_synced_to_kernel")
    except Exception as e:
        app_context.logger.warning(
            "quota_defaults_sync_failed",
            error=str(e),
            detail="Kernel will use its built-in defaults",
        )


__all__ = [
    "create_app_context",
    "create_tool_executor_with_access",
    "create_core_config_from_env",
    "create_orchestration_flags_from_env",
    "sync_quota_defaults_to_kernel",
    # Per-request PID context for resource tracking
    "set_request_pid",
    "clear_request_pid",
    "get_request_pid",
    "request_pid_context",
]
