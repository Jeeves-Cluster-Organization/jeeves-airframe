"""
Mission System Adapters - Infrastructure Service Wrappers.

This module provides convenience wrappers for infrastructure services.
Apps/verticals should use these instead of importing jeeves_infra directly.

Architecture enforcement:
    apps/verticals → mission_system (adapters) → jeeves_infra

Purpose: Single access point for infrastructure services.

Constitutional Compliance:
- Apps MUST use these adapters for infrastructure access
- Apps MUST NOT import from jeeves_infra directly
- All infrastructure dependencies are injected, not imported as globals
"""

from typing import Any, Optional, Callable
# Phase 1.5: Import canonical protocols directly from jeeves_infra
from jeeves_infra.protocols import (
    PersistenceProtocol,
    LLMProviderProtocol,
    ToolRegistryProtocol,
    SettingsProtocol,
)
from mission_system.contracts import ContextBounds


class MissionSystemAdapters:
    """
    Collection of infrastructure adapters for apps/verticals.

    Provides unified access to:
    - Database/persistence services
    - LLM provider factory
    - Memory services (L1-L4)
    - Tool registry
    - Settings (configuration)
    - Context bounds

    Example:
        adapters = MissionSystemAdapters(
            db=database_client,
            llm_factory=lambda role: create_llm_provider(role),
            settings=get_settings(),
        )

        # In agent - all deps via adapters
        llm = adapters.get_llm_provider("planner")
        # Model config is owned by capabilities via DomainLLMRegistry
        bounds = adapters.context_bounds
    """

    def __init__(
        self,
        db: PersistenceProtocol,
        llm_factory: Optional[Callable[[str], LLMProviderProtocol]] = None,
        tool_registry: Optional[ToolRegistryProtocol] = None,
        settings: Optional[SettingsProtocol] = None,
        context_bounds: Optional[ContextBounds] = None,
    ):
        """
        Initialize adapters.

        Args:
            db: Database client (persistence protocol)
            llm_factory: Factory function to create LLM providers per agent role
            tool_registry: Tool registry (raises RuntimeError if None on access)
            settings: Settings instance (raises RuntimeError if None on access)
            context_bounds: Context bounds (raises RuntimeError if None on access)
        """
        self.db = db
        self._llm_factory = llm_factory
        self._tool_registry = tool_registry
        self._settings = settings
        self._context_bounds = context_bounds
        self._memory_service: Optional[Any] = None

    def get_llm_provider(self, agent_role: str) -> LLMProviderProtocol:
        """
        Get LLM provider for an agent role.

        Args:
            agent_role: Agent role identifier (e.g., "planner", "critic")

        Returns:
            LLM provider instance configured for that role

        Raises:
            ValueError: If no LLM factory configured
        """
        if not self._llm_factory:
            raise ValueError(
                "No LLM factory configured. "
                "Pass llm_factory to MissionSystemAdapters constructor."
            )
        return self._llm_factory(agent_role)

    @property
    def memory(self) -> Any:
        """
        Get memory service (L1-L4 layers).

        Lazy-loads the memory service on first access.

        Returns:
            MemoryService instance
        """
        if not self._memory_service:
            raise NotImplementedError(
                "Memory service must be injected by capability. "
                "Pass memory_service to MissionSystemAdapters constructor."
            )
        return self._memory_service

    @property
    def tool_registry(self) -> ToolRegistryProtocol:
        """
        Get tool registry.

        Constitution R5: Tool registry must be explicitly injected, no soft None return.

        Returns:
            Tool registry instance

        Raises:
            RuntimeError: If tool_registry not injected
        """
        if self._tool_registry is not None:
            return self._tool_registry
        # Constitution R5: No soft None return - explicit injection required
        raise RuntimeError(
            "ToolRegistry not injected. Pass tool_registry to MissionSystemAdapters constructor. "
            "Returning None would cause downstream AttributeError or hallucination. "
            "Use: MissionSystemAdapters(db=db, tool_registry=registry)"
        )

    @property
    def settings(self) -> SettingsProtocol:
        """
        Get settings.

        Constitution R5: Settings must be explicitly injected, no global fallbacks.

        Returns:
            Settings instance

        Raises:
            RuntimeError: If settings not injected
        """
        if self._settings is not None:
            return self._settings
        # Constitution R5: No global fallback - explicit injection required
        raise RuntimeError(
            "Settings not injected. Pass settings to MissionSystemAdapters constructor. "
            "Global fallbacks violate Constitution R5 (Dependency Injection). "
            "Use: MissionSystemAdapters(db=db, settings=get_settings())"
        )

    @property
    def context_bounds(self) -> ContextBounds:
        """
        Get context bounds configuration.

        Constitution R5: Context bounds must be explicitly injected, no global fallbacks.

        Returns:
            ContextBounds instance

        Raises:
            RuntimeError: If context_bounds not injected
        """
        if self._context_bounds is not None:
            return self._context_bounds
        # Constitution R5: No global fallback - explicit injection required
        raise RuntimeError(
            "ContextBounds not injected. Pass context_bounds to MissionSystemAdapters constructor. "
            "Global fallbacks violate Constitution R5 (Dependency Injection). "
            "Use: MissionSystemAdapters(db=db, context_bounds=app_context.get_context_bounds())"
        )


# =============================================================================
# Logging Facade - Constitutional compliance for app logging
# =============================================================================

def get_logger():
    """
    Get logger instance for apps.

    Apps should use this instead of importing from jeeves_infra.logging directly.

    Returns:
        Logger instance (Logger)

    Constitutional compliance:
        Apps access infrastructure via adapters, not direct jeeves_infra imports.

    Example:
        from mission_system.adapters import get_logger
        logger = get_logger()
        logger.info("agent_started", agent="critic")
    """
    from jeeves_infra.logging import get_current_logger
    return get_current_logger()


# =============================================================================
# Factory Functions - Access points for infrastructure services
# =============================================================================

def create_database_client(
    settings: Optional[SettingsProtocol] = None,
) -> PersistenceProtocol:
    """
    Create a database client.

    Apps should use this instead of importing from jeeves_infra directly.

    Args:
        settings: Optional settings (uses global if None)

    Returns:
        Database client implementing PersistenceProtocol

    Constitutional compliance:
        Apps access infrastructure via adapters, not direct jeeves_infra imports.
    """
    from jeeves_infra.database.factory import create_database_client as _create_db
    if settings is None:
        from jeeves_infra.settings import get_settings
        settings = get_settings()
    return _create_db(settings)


def get_settings() -> SettingsProtocol:
    """
    Get application settings.

    Apps should use this instead of importing from jeeves_infra directly.

    Returns:
        Settings instance implementing SettingsProtocol

    Constitutional compliance:
        Apps access infrastructure via adapters, not direct jeeves_infra imports.
    """
    from jeeves_infra.settings import get_settings as _get_settings
    return _get_settings()


def get_feature_flags() -> Any:
    """
    Get feature flags.

    Apps should use this instead of importing from jeeves_infra directly.

    Returns:
        FeatureFlags instance

    Constitutional compliance:
        Apps access infrastructure via adapters, not direct jeeves_infra imports.
    """
    from jeeves_infra.feature_flags import get_feature_flags as _get_flags
    return _get_flags()


# =============================================================================
# Memory Layer Factories - L2-L5 services
# =============================================================================

def create_event_emitter(persistence: PersistenceProtocol) -> Any:
    """
    Create L2 event emitter for domain events.

    Delegates to capability-registered factory via CapabilityResourceRegistry.

    Args:
        persistence: Database client

    Returns:
        EventEmitter instance
    """
    from jeeves_infra.protocols import get_capability_resource_registry
    factory = get_capability_resource_registry().get_memory_service_factory("event_emitter")
    if factory:
        return factory(persistence)
    raise RuntimeError("No event_emitter registered by any capability")


def create_graph_storage(persistence: PersistenceProtocol) -> Any:
    """
    Create graph storage for entity relationships.

    Delegates to capability-registered factory via CapabilityResourceRegistry.

    Args:
        persistence: Database client

    Returns:
        GraphStorageProtocol implementation
    """
    from jeeves_infra.protocols import get_capability_resource_registry
    factory = get_capability_resource_registry().get_memory_service_factory("graph_storage")
    if factory:
        return factory(persistence)
    raise RuntimeError("No graph_storage registered by any capability")


def create_tool_health_service(persistence: PersistenceProtocol) -> Any:
    """
    Create tool health monitoring service.

    Args:
        persistence: Database client

    Returns:
        ToolHealthService instance
    """
    from mission_system.memory.services.tool_health_service import ToolHealthService
    return ToolHealthService(persistence)


def create_tool_executor(registry: Optional[ToolRegistryProtocol] = None) -> Any:
    """
    Create tool executor with access control.

    Wrapper for jeeves_infra.wiring.create_tool_executor.
    Apps should use this instead of importing from jeeves_infra directly.

    Args:
        registry: Optional tool registry (uses global if None)

    Returns:
        ToolExecutor instance implementing ToolExecutorProtocol

    Constitutional compliance:
        Apps access infrastructure via adapters, not direct jeeves_infra imports.
        Layer boundary: Capability → Mission System (adapters) → jeeves_infra
    """
    from jeeves_infra.wiring import create_tool_executor as _create_executor
    return _create_executor(registry)


def create_llm_provider_factory(settings: Optional[SettingsProtocol] = None) -> Callable:
    """
    Create LLM provider factory.

    Wrapper for jeeves_infra.wiring.create_llm_provider_factory.
    Apps should use this instead of importing from jeeves_infra directly.

    Args:
        settings: Optional settings (uses global if None)

    Returns:
        Factory function that creates LLM providers

    Constitutional compliance:
        Apps access infrastructure via adapters, not direct jeeves_infra imports.
        Layer boundary: Capability → Mission System (adapters) → jeeves_infra
    """
    from jeeves_infra.wiring import create_llm_provider_factory as _create_factory
    return _create_factory(settings)


__all__ = [
    "SettingsProtocol",
    "MissionSystemAdapters",
    # Logging facade
    "get_logger",
    # Core factories
    "create_database_client",
    "get_settings",
    "get_feature_flags",
    # Tool and LLM factories (wrappers for jeeves_infra)
    "create_tool_executor",
    "create_llm_provider_factory",
    # Memory layer factories
    "create_event_emitter",
    "create_graph_storage",
    "create_tool_health_service",
]
