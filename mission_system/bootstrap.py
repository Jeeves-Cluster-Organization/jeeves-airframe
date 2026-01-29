"""Composition Root - Build AppContext and inject dependencies.

ADR-001 Decision 3: Singleton Elimination via AppContext
This module is the COMPOSITION ROOT for the Jeeves application.
It is the ONLY place where concrete implementations are instantiated
and wired together.

All configuration is passed via AppContext - no global state.

Usage:
    from mission_system.bootstrap import create_app_context

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
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from contextvars import ContextVar

from jeeves_infra.context import AppContext, SystemClock
from jeeves_infra.logging import configure_logging
from jeeves_infra.settings import Settings, get_settings
from jeeves_infra.feature_flags import FeatureFlags, get_feature_flags
from jeeves_infra.protocols import ExecutionConfig, ContextBounds, OrchestrationFlags
from jeeves_infra.protocols import get_capability_resource_registry

# KernelClient for Go kernel integration
from jeeves_infra.kernel_client import KernelClient, QuotaCheckResult

# Type alias for LLMGateway (imported conditionally)
LLMGatewayType = Any

if TYPE_CHECKING:
    from jeeves_infra.protocols import (
        LanguageConfigProtocol,
        InferenceEndpointsProtocol,
        AgentToolAccessProtocol,
        ConfigRegistryProtocol,
    )


# =============================================================================
# Per-Request PID Context for Resource Tracking
# =============================================================================

# ContextVar to track the current request's Process ID (PID)
# Used by LLM gateway to associate resource usage with kernel processes
request_pid_context: ContextVar[Optional[str]] = ContextVar("request_pid", default=None)


def set_request_pid(pid: str) -> None:
    """Set the current request's Process ID.

    Args:
        pid: The kernel process ID for the current request
    """
    request_pid_context.set(pid)


def get_request_pid() -> Optional[str]:
    """Get the current request's Process ID.

    Returns:
        The PID if set, None otherwise
    """
    return request_pid_context.get()


def clear_request_pid() -> None:
    """Clear the current request's Process ID."""
    request_pid_context.set(None)


# =============================================================================
# Resource Configuration
# =============================================================================

@dataclass
class ResourceQuota:
    """Resource quota configuration for kernel processes."""
    max_input_tokens: int = 4096
    max_output_tokens: int = 2048
    max_context_tokens: int = 16384
    max_llm_calls: int = 10
    max_tool_calls: int = 50
    max_agent_hops: int = 21
    max_iterations: int = 3
    timeout_seconds: int = 300
    soft_timeout_seconds: int = 240


def _parse_bool(value: str, default: bool = True) -> bool:
    """Parse boolean from environment variable string."""
    return value.lower() == "true" if value else default


def _parse_optional_int(env_var: str) -> Optional[int]:
    """Parse an optional integer from environment variable."""
    val = os.getenv(env_var)
    return int(val) if val else None


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


def core_config_to_resource_quota(core_config: ExecutionConfig) -> ResourceQuota:
    """Convert ExecutionConfig to Control Tower ResourceQuota.

    Control Tower's ResourceQuota is the canonical source for resource limits.
    This adapter ensures consistency with legacy ExecutionConfig values.

    Args:
        core_config: ExecutionConfig from environment/config

    Returns:
        ResourceQuota for Control Tower
    """
    return ResourceQuota(
        max_input_tokens=core_config.context_bounds.max_input_tokens,
        max_output_tokens=core_config.context_bounds.max_output_tokens,
        max_context_tokens=core_config.context_bounds.max_context_tokens,
        max_llm_calls=core_config.max_llm_calls,
        max_tool_calls=50,  # Default, not in ExecutionConfig
        max_agent_hops=core_config.max_agent_hops,
        max_iterations=core_config.max_iterations,
        timeout_seconds=300,  # Default timeout
        soft_timeout_seconds=240,
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

    # Get default service from capability registry (layer extraction support, Infrastructure R4)
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

    # Build default resource quota from ExecutionConfig
    default_quota = core_config_to_resource_quota(core_config)

    root_logger.info(
        "app_context_created",
        default_service=default_service,
        max_llm_calls=default_quota.max_llm_calls,
        max_iterations=default_quota.max_iterations,
        max_agent_hops=default_quota.max_agent_hops,
    )

    # Note: kernel_client is None here - connect via connect_kernel_client() async
    return AppContext(
        settings=settings,
        feature_flags=feature_flags,
        logger=root_logger,
        clock=SystemClock(),
        config_registry=None,
        core_config=core_config,
        orchestration_flags=orchestration_flags,
        vertical_registry={},
        kernel_client=None,  # Set via connect_kernel_client() after event loop starts
    )


def create_infra_dependencies(
    app_context: AppContext,
    language_config: Optional["LanguageConfigProtocol"] = None,
    node_profiles: Optional["InferenceEndpointsProtocol"] = None,
    access_checker: Optional["AgentToolAccessProtocol"] = None,
):
    """Create and inject dependencies into infrastructure layer.

    This function sets up the dependency injection for infrastructure
    components that need capability-owned implementations.

    ADR-001 Decision 1: Layer Violation Resolution via Protocol Injection

    Args:
        app_context: The AppContext with core dependencies
        language_config: Optional LanguageConfigProtocol implementation
        node_profiles: Optional InferenceEndpointsProtocol implementation
        access_checker: Optional AgentToolAccessProtocol implementation

    Returns:
        Dict with created dependencies (for use by capability layer)
    """
    # LLM components moved to jeeves-infra
    try:
        from jeeves_infra.llm.factory import LLMFactory
    except ImportError:
        raise ImportError(
            "LLM factory requires jeeves-infra package. "
            "Install with: pip install jeeves-infra[llm]"
        )

    # Create LLM factory
    # Note: node_profiles are stored in deps for capability layer use but not
    # passed to LLMFactory directly (distributed routing handled at capability layer)
    llm_factory = LLMFactory(settings=app_context.settings)

    # Initialize LLM Gateway if feature flag is enabled
    llm_gateway = None
    if app_context.feature_flags.use_llm_gateway:
        from jeeves_infra.llm.gateway import LLMGateway
        from jeeves_infra.logging import create_logger

        gateway_logger = create_logger("llm_gateway")

        # Configure fallback providers based on primary provider
        fallback_providers = []
        primary_provider = app_context.settings.llm_provider
        if primary_provider == "llamaserver":
            fallback_providers = ["openai"]  # Fallback to cloud if local fails
        elif primary_provider == "openai":
            fallback_providers = ["anthropic"]  # Fallback between cloud providers

        llm_gateway = LLMGateway(
            settings=app_context.settings,
            fallback_providers=fallback_providers,
            logger=gateway_logger,
            kernel_client=app_context.kernel_client,
        )

        gateway_logger.info(
            "llm_gateway_initialized",
            primary_provider=primary_provider,
            fallback_providers=fallback_providers,
            resource_tracking_enabled=app_context.kernel_client is not None,
        )

    return {
        "llm_factory": llm_factory,
        "llm_gateway": llm_gateway,
        "language_config": language_config,
        "node_profiles": node_profiles,
        "access_checker": access_checker,
    }


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


def create_distributed_infrastructure(
    app_context: AppContext,
    redis_url: Optional[str] = None,
    postgres_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Create distributed infrastructure when enable_distributed_mode is true.

    Creates Redis client and RedisDistributedBus for horizontal scaling.
    Optionally wires checkpoint adapter when enable_checkpoints is true.

    Args:
        app_context: AppContext with feature flags and logger
        redis_url: Optional Redis URL (uses REDIS_URL env var if not provided)
        postgres_client: Optional PostgreSQLClient for checkpoint persistence

    Returns:
        Dict containing:
        - redis_client: AsyncRedis client instance
        - distributed_bus: RedisDistributedBus instance
        - worker_coordinator: WorkerCoordinator instance
        - checkpoint_adapter: PostgresCheckpointAdapter (if checkpoints enabled)

    Raises:
        RuntimeError: If distributed mode is enabled but Redis unavailable
    """
    from jeeves_infra.logging import create_logger

    result: Dict[str, Any] = {
        "redis_client": None,
        "distributed_bus": None,
        "worker_coordinator": None,
        "checkpoint_adapter": None,
    }

    # Only create if distributed mode is enabled
    if not app_context.feature_flags.enable_distributed_mode:
        return result

    # Verify Redis state flag is also enabled (required dependency)
    if not app_context.feature_flags.use_redis_state:
        app_context.logger.warning(
            "distributed_mode_requires_redis",
            message="enable_distributed_mode requires use_redis_state=true",
        )
        return result

    # Get Redis URL from param or environment
    import os
    actual_redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")

    try:
        # Import Redis async client
        import redis.asyncio as redis_async
        from jeeves_infra.distributed import RedisDistributedBus
        from mission_system.services.worker_coordinator import WorkerCoordinator

        # Create async Redis client wrapper
        # Note: The actual client is created as a coroutine factory
        # since async operations can't be awaited at module import time
        class AsyncRedisWrapper:
            """Wrapper for async Redis client to match RedisDistributedBus interface."""

            def __init__(self, url: str):
                self._url = url
                self._client = None

            @property
            def redis(self):
                """Get the underlying Redis client, creating if needed."""
                if self._client is None:
                    self._client = redis_async.from_url(
                        self._url,
                        decode_responses=True,
                    )
                return self._client

            async def close(self):
                """Close the Redis connection."""
                if self._client:
                    await self._client.close()
                    self._client = None

        redis_client = AsyncRedisWrapper(actual_redis_url)
        result["redis_client"] = redis_client

        # Create distributed bus
        bus_logger = create_logger("distributed_bus")
        distributed_bus = RedisDistributedBus(
            redis_client=redis_client,
            logger=bus_logger,
        )
        result["distributed_bus"] = distributed_bus

        # Create checkpoint adapter if checkpoints enabled and postgres available
        checkpoint_adapter = None
        if app_context.feature_flags.enable_checkpoints:
            if postgres_client is not None:
                from jeeves_infra.postgres.checkpoint import PostgresCheckpointAdapter

                checkpoint_logger = create_logger("checkpoint_adapter")
                checkpoint_adapter = PostgresCheckpointAdapter(
                    postgres_client=postgres_client,
                    logger=checkpoint_logger,
                )
                result["checkpoint_adapter"] = checkpoint_adapter

                app_context.logger.info(
                    "checkpoint_adapter_created",
                    message="PostgresCheckpointAdapter wired for distributed checkpointing",
                )
            else:
                app_context.logger.warning(
                    "checkpoint_adapter_skipped",
                    message="enable_checkpoints=true but no postgres_client provided",
                )

        # Create worker coordinator with kernel and resource tracking
        coordinator_logger = create_logger("worker_coordinator")

        # Create ResourceTracker for quota management
        resource_tracker = None
        if app_context.kernel_client:
            from jeeves_infra.resource_tracker import ResourceTracker
            from jeeves_infra.config import ResourceConfig
            resource_tracker = ResourceTracker(
                kernel_client=app_context.kernel_client,
                config=ResourceConfig.from_env(),
            )

        worker_coordinator = WorkerCoordinator(
            distributed_bus=distributed_bus,
            checkpoint_adapter=checkpoint_adapter,
            runtime=None,  # Runtime provided separately per worker
            logger=coordinator_logger,
            kernel_client=app_context.kernel_client,
            resource_tracker=resource_tracker,
        )
        result["worker_coordinator"] = worker_coordinator

        app_context.logger.info(
            "distributed_infrastructure_created",
            redis_url=actual_redis_url.split("@")[-1],  # Redact credentials
            has_kernel_client=app_context.kernel_client is not None,
            has_checkpoint_adapter=checkpoint_adapter is not None,
        )

    except ImportError as e:
        app_context.logger.error(
            "distributed_import_error",
            error=str(e),
            message="Install redis package: pip install redis",
        )
        raise RuntimeError(
            f"Failed to import distributed dependencies: {e}. "
            "Install with: pip install redis"
        ) from e
    except Exception as e:
        app_context.logger.error(
            "distributed_init_error",
            error=str(e),
            redis_url=actual_redis_url.split("@")[-1],
        )
        raise RuntimeError(f"Failed to create distributed infrastructure: {e}") from e

    return result


async def create_memory_manager(
    app_context: AppContext,
    postgres_client: Optional[Any] = None,
    vector_adapter: Optional[Any] = None,
) -> Optional[Any]:
    """Create MemoryManager facade for unified memory operations.

    Wires the MemoryManager with SQL adapter, vector adapter, and cross-ref manager.
    This is the unified memory interface per Memory Module Constitution.

    Args:
        app_context: AppContext with logger and settings
        postgres_client: PostgreSQL client for SQL operations
        vector_adapter: Vector storage adapter (pgvector) for semantic search

    Returns:
        MemoryManager instance, or None if dependencies unavailable
    """
    if postgres_client is None:
        app_context.logger.warning(
            "memory_manager_skipped",
            message="No postgres_client provided - MemoryManager requires database",
        )
        return None

    try:
        from jeeves_infra.memory.manager import MemoryManager
        from jeeves_infra.memory.sql_adapter import SQLAdapter
        from jeeves_infra.memory.services.xref_manager import CrossRefManager
        from jeeves_infra.logging import create_logger

        memory_logger = create_logger("memory_manager")

        # Create SQL adapter wrapping the postgres client
        sql_adapter = SQLAdapter(db_client=postgres_client, logger=memory_logger)

        # Create cross-reference manager
        xref_manager = CrossRefManager(db_client=postgres_client, logger=memory_logger)

        # Create MemoryManager facade
        memory_manager = MemoryManager(
            sql_adapter=sql_adapter,
            vector_adapter=vector_adapter,
            xref_manager=xref_manager,
            logger=memory_logger,
        )

        app_context.logger.info(
            "memory_manager_created",
            has_vector_adapter=vector_adapter is not None,
        )

        return memory_manager

    except ImportError as e:
        app_context.logger.error(
            "memory_manager_import_error",
            error=str(e),
        )
        return None
    except Exception as e:
        app_context.logger.error(
            "memory_manager_init_error",
            error=str(e),
        )
        return None


__all__ = [
    "create_app_context",
    "create_infra_dependencies",
    "create_tool_executor_with_access",
    "create_core_config_from_env",
    "create_orchestration_flags_from_env",
    "core_config_to_resource_quota",
    # Distributed infrastructure
    "create_distributed_infrastructure",
    # Memory management
    "create_memory_manager",
    # Per-request PID context for resource tracking
    "set_request_pid",
    "clear_request_pid",
    "get_request_pid",
    "request_pid_context",
]
