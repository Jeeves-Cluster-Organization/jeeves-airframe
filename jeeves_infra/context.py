"""AppContext - Unified application context for dependency injection.

ADR-001 Decision 3: Singleton Elimination via AppContext
This module provides the AppContext dataclass that contains all
injected dependencies. Built by the composition root (mission_system),
passed to all components.

Design Mantra: One composition root builds one AppContext;
everything gets dependencies from there, not from globals.

Usage:
    from avionics.context import AppContext

    # In composition root (bootstrap.py)
    app_context = create_app_context()

    # Pass to components
    service = MyService(context=app_context)
    # Access config via context
    bounds = app_context.core_config.context_bounds
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from jeeves_infra.protocols import (
    AppContextProtocol,
    ClockProtocol,
    ConfigRegistryProtocol,
    FeatureFlagsProtocol,
    LoggerProtocol,
    SettingsProtocol,
)
from jeeves_infra.protocols import ExecutionConfig, ContextBounds, OrchestrationFlags

if TYPE_CHECKING:
    from jeeves_infra.settings import Settings
    from jeeves_infra.feature_flags import FeatureFlags
    from jeeves_infra.kernel_client import KernelClient


class SystemClock:
    """Default system clock implementation.

    Implements ClockProtocol for real wall-clock time.
    Can be replaced with a mock for testing.
    """

    def now(self) -> datetime:
        """Get current local datetime."""
        return datetime.now()

    def utcnow(self) -> datetime:
        """Get current UTC datetime with timezone info."""
        return datetime.now(timezone.utc)


@dataclass
class AppContext:
    """Concrete application context for dependency injection.

    Contains all the dependencies that components need. Built once
    by the composition root (mission_system/bootstrap.py) and passed
    to all components.

    ADR-001 Decision 3: This replaces scattered global singletons with
    a single, explicit dependency container.

    Attributes:
        settings: Application settings (implements SettingsProtocol)
        feature_flags: Feature flags (implements FeatureFlagsProtocol)
        logger: Root logger (implements LoggerProtocol)
        clock: Time provider (implements ClockProtocol)
        config_registry: Configuration registry (implements ConfigRegistryProtocol)
        core_config: Core runtime configuration (bounds, timeouts, etc.)
        orchestration_flags: Orchestration feature flags
        vertical_registry: Registry of registered capability verticals

    Usage:
        # In composition root
        app_context = AppContext(
            settings=settings,
            feature_flags=feature_flags,
            logger=logger,
            core_config=ExecutionConfig(),
            orchestration_flags=OrchestrationFlags(),
        )

        # In components
        class MyService:
            def __init__(self, context: AppContext):
                self._settings = context.settings
                self._bounds = context.core_config.context_bounds
    """

    settings: SettingsProtocol
    feature_flags: FeatureFlagsProtocol
    logger: LoggerProtocol
    clock: ClockProtocol = field(default_factory=SystemClock)
    config_registry: Optional[ConfigRegistryProtocol] = None

    # Core configuration (previously global state in protocols)
    core_config: ExecutionConfig = field(default_factory=ExecutionConfig)
    orchestration_flags: OrchestrationFlags = field(default_factory=OrchestrationFlags)
    vertical_registry: Dict[str, bool] = field(default_factory=dict)

    # Kernel Client - gRPC client to Go kernel for orchestration
    # Uses string annotation for TYPE_CHECKING-only import (layer extraction support)
    kernel_client: Optional["KernelClient"] = None

    # Deprecated: control_tower is replaced by kernel_client
    # Keeping for backward compatibility during migration
    control_tower: Optional[Any] = None

    # Optional request-scoped context
    request_id: Optional[str] = None
    envelope_id: Optional[str] = None
    user_id: Optional[str] = None

    def with_request(
        self,
        request_id: str,
        envelope_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> "AppContext":
        """Create a copy with request-scoped fields set.

        Args:
            request_id: Request ID for this scope
            envelope_id: Optional envelope ID
            user_id: Optional user ID

        Returns:
            New AppContext with request fields populated
        """
        return AppContext(
            settings=self.settings,
            feature_flags=self.feature_flags,
            logger=self.logger.bind(
                request_id=request_id,
                envelope_id=envelope_id,
                user_id=user_id,
            ),
            clock=self.clock,
            config_registry=self.config_registry,
            core_config=self.core_config,
            orchestration_flags=self.orchestration_flags,
            vertical_registry=self.vertical_registry,
            kernel_client=self.kernel_client,
            control_tower=self.control_tower,  # Deprecated, kept for migration
            request_id=request_id,
            envelope_id=envelope_id,
            user_id=user_id,
        )

    # ─── Vertical Registry Operations ───

    def register_vertical(self, vertical_id: str) -> None:
        """Register a vertical as available."""
        self.vertical_registry[vertical_id] = True

    def unregister_vertical(self, vertical_id: str) -> None:
        """Unregister a vertical."""
        self.vertical_registry.pop(vertical_id, None)

    def is_vertical_registered(self, vertical_id: str) -> bool:
        """Check if a vertical is registered."""
        return self.vertical_registry.get(vertical_id, False)

    def list_registered_verticals(self) -> List[str]:
        """List all registered verticals."""
        return list(self.vertical_registry.keys())

    # ─── Config Accessors ───

    def get_context_bounds(self) -> ContextBounds:
        """Get context bounds from core config."""
        return self.core_config.context_bounds

    def get_bound_logger(self, component: str, **extra: Any) -> LoggerProtocol:
        """Get a logger bound to this context and component.

        Args:
            component: Component name for the logger
            **extra: Additional context to bind

        Returns:
            LoggerProtocol bound to context
        """
        bindings = {"component": component}
        if self.request_id:
            bindings["request_id"] = self.request_id
        if self.envelope_id:
            bindings["envelope_id"] = self.envelope_id
        if self.user_id:
            bindings["user_id"] = self.user_id
        bindings.update(extra)
        return self.logger.bind(**bindings)


# Type alias for protocol compliance check
def _check_protocol_compliance() -> None:
    """Verify AppContext implements AppContextProtocol."""
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        _ctx: AppContextProtocol = AppContext(
            settings=None,  # type: ignore
            feature_flags=None,  # type: ignore
            logger=None,  # type: ignore
        )


__all__ = [
    "AppContext",
    "SystemClock",
]
