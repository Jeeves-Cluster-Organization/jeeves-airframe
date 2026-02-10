"""Capability Wiring - Register capabilities with CapabilityResourceRegistry.

This module is the capability registration entry point. External capability
packages call register functions here to wire themselves into the infrastructure.

The infrastructure queries the registry at runtime to:
- Get service configuration (is_readonly, requires_confirmation, etc.)
- Create orchestrators via registered factories
- Initialize tools via registered initializers
- Load prompts and agents

Usage:
    # External capability package registers itself:
    from jeeves_infra.capability_wiring import register_capability

    register_capability(
        capability_id="my_capability",
        service_config=DomainServiceConfig(...),
        orchestrator_factory=my_factory,
        tools_initializer=my_tools_init,
    )

    # Or use environment-based auto-discovery:
    wire_capabilities()  # Discovers and registers capabilities

Constitutional Alignment:
- Constitution R4: Capabilities register their own resources
- No hardcoded capability knowledge in infrastructure
"""

import os
from typing import Any, Callable, Dict, List, Optional

from jeeves_infra.protocols import (
    get_capability_resource_registry,
    DomainServiceConfig,
    CapabilityOrchestratorConfig,
    CapabilityToolsConfig,
)


def register_capability(
    capability_id: str,
    service_config: DomainServiceConfig,
    orchestrator_factory: Optional[Callable[..., Any]] = None,
    tools_initializer: Optional[Callable[..., Dict[str, Any]]] = None,
) -> None:
    """Register a capability with all required configuration.

    This is the main entry point for capability registration. External
    capability packages call this to wire themselves into the infrastructure.

    Args:
        capability_id: Unique identifier for the capability
        service_config: Service configuration with behavior metadata
        orchestrator_factory: Optional factory to create orchestrator
        tools_initializer: Optional initializer for tools
    """
    registry = get_capability_resource_registry()

    # Register service configuration
    registry.register_service(
        capability_id=capability_id,
        service_config=service_config,
    )

    # Register orchestrator factory if provided
    if orchestrator_factory:
        registry.register_orchestrator(
            capability_id=capability_id,
            config=CapabilityOrchestratorConfig(
                factory=orchestrator_factory,
                result_type=None,
            ),
        )

    # Register tools initializer if provided
    if tools_initializer:
        registry.register_tools(
            capability_id=capability_id,
            config=CapabilityToolsConfig(
                initializer=tools_initializer,
            ),
        )


def _discover_capabilities() -> List[str]:
    """Discover capabilities from environment or entry points.

    Returns list of capability module paths to import.
    """
    # Check environment for explicit capability list
    capabilities_env = os.getenv("JEEVES_CAPABILITIES", "")
    if capabilities_env:
        return [c.strip() for c in capabilities_env.split(",") if c.strip()]

    # No hardcoded fallbacks — env-only discovery.
    # Set JEEVES_CAPABILITIES to register capabilities.
    return []


def _try_import_capability(module_path: str) -> bool:
    """Try to import and register a capability module.

    The module should call register_capability() when imported.

    Returns:
        True if successfully imported, False otherwise.
    """
    try:
        __import__(module_path)
        return True
    except ImportError:
        return False


def wire_capabilities() -> None:
    """Discover and wire all capabilities with the CapabilityResourceRegistry.

    Call this during application startup before the API server
    queries the registry.

    Discovery: JEEVES_CAPABILITIES environment variable (comma-separated module paths).
    Fails loud if no capabilities are discovered.
    """
    discovered = _discover_capabilities()
    registered = []

    for module_path in discovered:
        if _try_import_capability(module_path):
            registered.append(module_path)

    if not registered:
        raise RuntimeError(
            "No capabilities registered. Set JEEVES_CAPABILITIES env var "
            "to a comma-separated list of capability wiring module paths."
        )

    # Log registration
    registry = get_capability_resource_registry()
    capabilities = registry.list_capabilities()

    try:
        from jeeves_infra.logging import create_logger
        logger = create_logger("capability_wiring")
        logger.info(
            "capabilities_wired",
            discovered=discovered,
            registered=registered,
            capabilities=capabilities,
            default_service=registry.get_default_service(),
        )
    except ImportError:
        pass


def wire_infra_routers() -> None:
    """Register infrastructure API routers (governance, etc.).

    These are infrastructure concerns (P6 observability) not owned by any capability.
    They use the same registry mechanism as capability routers.
    """
    from jeeves_infra.gateway.routers.governance import router as gov_router, get_tool_health_service

    registry = get_capability_resource_registry()

    def _create_governance_deps(db, event_manager, orchestrator, **kwargs):
        from jeeves_infra.gateway.app_server import get_app_state
        return {get_tool_health_service: lambda: get_app_state().tool_health_service}

    registry.register_api_router(
        "_infra_governance",
        gov_router,
        deps_factory=_create_governance_deps,
        feature_flag=None,
    )


__all__ = [
    "register_capability",
    "wire_capabilities",
    "wire_infra_routers",
]
