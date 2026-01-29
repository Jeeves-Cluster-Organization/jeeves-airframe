"""Capability Registration Protocols.

Constitutional Reference:
- Avionics R3: No Domain Logic - infrastructure provides transport, not business logic
- Avionics R4: Swappable Implementations - capabilities register their own resources
- Mission System Constitution: Domain configs OWNED by capabilities

This module defines protocols for capabilities to register their resources
(schemas, modes, services, etc.) with infrastructure without infrastructure having
hardcoded knowledge of specific capabilities.

Usage:
    # In capability startup (jeeves-capability-my-capability)
    from protocols.capability import get_capability_resource_registry

    registry = get_capability_resource_registry()
    registry.register_schema("my_capability", "database/schemas/my_schema.sql")
    registry.register_mode("my_capability", DomainModeConfig(...))
    registry.register_service("my_capability", DomainServiceConfig(...))

    # In infrastructure (avionics/mission_system)
    from protocols.capability import get_capability_resource_registry

    registry = get_capability_resource_registry()
    schemas = registry.get_schemas()  # Returns all registered schema paths
    services = registry.get_services()  # Returns all registered services
    default = registry.get_default_service()  # Returns primary service name
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable, Any, Callable, TypeVar
from dataclasses import dataclass, field
from enum import Enum

T = TypeVar('T')


# =============================================================================
# CAPABILITY TOOL CATALOG - Scoped tool registry per capability
# =============================================================================

@dataclass(frozen=True)
class ToolCatalogEntry:
    """Immutable tool metadata for capability tools.
    
    Frozen dataclass ensures entries cannot be modified after creation.
    """
    id: str
    description: str
    parameters: Dict[str, str]
    category: str  # ToolCategory value as string
    risk_level: str = "low"  # RiskLevel value as string


@dataclass
class ToolDefinition:
    """Tool definition returned by catalog lookups."""
    name: str
    function: Callable
    parameters: Dict[str, str]
    description: str = ""


class CapabilityToolCatalog:
    """Tool catalog scoped to a single capability.
    
    Each capability owns its own catalog instance. Infrastructure queries via
    CapabilityResourceRegistry.get_tools(capability_id) to get the catalog.
    
    This design ensures:
    - Avionics R3: No Domain Logic in core (capabilities define their own tools)
    - Full isolation between capabilities
    - No global ToolId enum needed for capability-specific tools
    
    Usage:
        # In capability layer
        catalog = CapabilityToolCatalog("assistant")
        catalog.register(
            tool_id="add_task",
            func=add_task,
            description="Create a new task",
            parameters={"title": "string", "priority": "integer?"},
            category="standalone",
            risk_level="write",
        )
        
        # Infrastructure queries
        registry = get_capability_resource_registry()
        tools_config = registry.get_tools("assistant")
        catalog = tools_config.catalog
        tool = catalog.get_tool("add_task")
    """
    
    def __init__(self, capability_id: str):
        """Initialize a catalog for a specific capability.
        
        Args:
            capability_id: Unique identifier for the capability (e.g., "assistant")
        """
        self.capability_id = capability_id
        self._entries: Dict[str, ToolCatalogEntry] = {}
        self._functions: Dict[str, Callable] = {}
    
    def register(
        self,
        tool_id: str,
        func: Callable,
        description: str,
        parameters: Dict[str, str],
        category: str,
        risk_level: str = "low",
    ) -> None:
        """Register a tool in this capability's catalog.
        
        Args:
            tool_id: Tool identifier (e.g., "add_task") - unique within this capability
            func: The async function that implements the tool
            description: Human-readable description for LLM prompts
            parameters: Dict of parameter_name -> type_description
            category: Tool category (e.g., "standalone", "composite")
            risk_level: Risk level (e.g., "read_only", "write", "destructive")
        """
        entry = ToolCatalogEntry(
            id=tool_id,
            description=description,
            parameters=parameters,
            category=category,
            risk_level=risk_level,
        )
        self._entries[tool_id] = entry
        self._functions[tool_id] = func
    
    def get_tool(self, tool_id: str) -> Optional[ToolDefinition]:
        """Get a tool definition by ID.
        
        Args:
            tool_id: Tool identifier
            
        Returns:
            ToolDefinition if found, None otherwise
        """
        entry = self._entries.get(tool_id)
        func = self._functions.get(tool_id)
        if entry is None or func is None:
            return None
        return ToolDefinition(
            name=tool_id,
            function=func,
            parameters=entry.parameters,
            description=entry.description,
        )
    
    def get_function(self, tool_id: str) -> Optional[Callable]:
        """Get tool function by ID.
        
        Args:
            tool_id: Tool identifier
            
        Returns:
            Function if found, None otherwise
        """
        return self._functions.get(tool_id)
    
    def has_tool(self, tool_id: str) -> bool:
        """Check if tool is registered.
        
        Args:
            tool_id: Tool identifier
            
        Returns:
            True if tool exists in this catalog
        """
        return tool_id in self._functions
    
    def list_tools(self) -> List[str]:
        """List all registered tool IDs.
        
        Returns:
            List of tool identifiers
        """
        return list(self._entries.keys())
    
    def get_entries(self) -> List[ToolCatalogEntry]:
        """Get all tool entries.
        
        Returns:
            List of all ToolCatalogEntry objects
        """
        return list(self._entries.values())
    
    def generate_prompt_section(self) -> str:
        """Generate tool descriptions for LLM prompts.
        
        Returns:
            Formatted multi-line string with tool descriptions
        """
        lines = [f"Tools for {self.capability_id}:\n"]
        for entry in sorted(self._entries.values(), key=lambda e: e.id):
            param_parts = []
            for name, ptype in entry.parameters.items():
                if ptype.endswith("?") or "optional" in ptype.lower():
                    param_parts.append(f"{name}?")
                else:
                    param_parts.append(name)
            params = ", ".join(param_parts)
            lines.append(f"- {entry.id}({params}): {entry.description}")
        return "\n".join(lines)
    
    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._entries)
    
    def __contains__(self, tool_id: str) -> bool:
        """Check if tool_id is in catalog."""
        return tool_id in self._entries


# =============================================================================
# CAPABILITY CONFIGURATION DATACLASSES
# =============================================================================

@dataclass
class DomainAgentConfig:
    """Configuration for an agent registered by a capability.

    Used by governance service to discover agents dynamically.
    """
    name: str
    description: str
    layer: str  # "perception", "planning", "execution", "synthesis", "validation", "integration"
    tools: List[str] = field(default_factory=list)


@dataclass
class CapabilityPromptConfig:
    """Configuration for a prompt registered by a capability."""
    prompt_id: str
    version: str
    description: str
    prompt_factory: Callable[[], str]  # Function that returns the prompt template


@dataclass
class CapabilityToolsConfig:
    """Configuration for tools registered by a capability.
    
    Supports two patterns:
    1. Lazy initialization: Provide `initializer` function that creates catalog on demand
    2. Eager initialization: Provide `catalog` instance directly
    
    The capability owns its CapabilityToolCatalog instance, ensuring full isolation
    from other capabilities and no coupling to infrastructure.
    """
    tool_ids: List[str] = field(default_factory=list)  # List of tool IDs provided
    catalog: Optional["CapabilityToolCatalog"] = None  # The capability's tool catalog
    initializer: Optional[Callable[..., "CapabilityToolCatalog"]] = None  # Lazy: (db) -> catalog
    
    def get_catalog(self, **kwargs) -> Optional["CapabilityToolCatalog"]:
        """Get or initialize the tool catalog.
        
        Args:
            **kwargs: Arguments passed to initializer (e.g., db=connection)
            
        Returns:
            CapabilityToolCatalog instance or None
        """
        if self.catalog is not None:
            return self.catalog
        if self.initializer is not None:
            self.catalog = self.initializer(**kwargs)
            return self.catalog
        return None


@dataclass
class CapabilityOrchestratorConfig:
    """Configuration for orchestrator service registered by a capability."""
    factory: Callable[..., Any]  # Function: (llm_factory, tool_executor, logger, persistence, control_tower) -> service
    result_type: Optional[type] = None  # The result type class (e.g., CapabilityResult)


@dataclass
class CapabilityContractsConfig:
    """Configuration for tool result contracts registered by a capability."""
    schemas: Dict[str, type] = field(default_factory=dict)  # tool_name -> schema type
    validators: Dict[str, Callable[..., Any]] = field(default_factory=dict)  # tool_name -> validator
    module: Optional[Any] = None  # The contracts module for import access


@dataclass
class DomainServiceConfig:
    """Configuration for a capability service (Control Tower registration).

    Services define how capabilities are registered with the Control Tower
    for request dispatch and resource management.

    The additional metadata fields (is_readonly, requires_confirmation, etc.)
    enable the mission system to adapt its behavior based on capability
    characteristics without hardcoding assumptions about specific capabilities.
    """
    service_id: str
    service_type: str = "flow"  # "flow", "tool", "query"
    capabilities: List[str] = field(default_factory=list)
    max_concurrent: int = 10
    is_default: bool = False  # If True, this is the default service for the Control Tower

    # Capability behavior metadata (enables generic mission system behavior)
    is_readonly: bool = True  # Whether this capability only reads (no modifications)
    requires_confirmation: bool = False  # Whether actions need user confirmation
    default_session_title: str = "Session"  # Default title for new sessions
    pipeline_stages: List[str] = field(default_factory=list)  # Agent pipeline stages if any


@dataclass
class DomainModeConfig:
    """Configuration for a capability mode.

    Modes define how the gateway should handle requests for a specific capability.
    """
    mode_id: str
    # Fields to include in response when this mode is active
    response_fields: List[str] = field(default_factory=list)
    # Whether this mode requires repo_path
    requires_repo_path: bool = False


@runtime_checkable
class CapabilityResourceRegistryProtocol(Protocol):
    """Protocol for capability resource registration.

    Capabilities register their resources (schemas, modes, handlers) at startup.
    Infrastructure queries the registry instead of having hardcoded knowledge.
    """

    def register_schema(self, capability_id: str, schema_path: str) -> None:
        """Register a database schema for a capability.

        Args:
            capability_id: Unique capability identifier (e.g., "code_analysis")
            schema_path: Relative path to the schema SQL file
        """
        ...

    def register_mode(self, capability_id: str, mode_config: DomainModeConfig) -> None:
        """Register a gateway mode for a capability.

        Args:
            capability_id: Unique capability identifier
            mode_config: Mode configuration
        """
        ...

    def get_schemas(self, capability_id: Optional[str] = None) -> List[str]:
        """Get registered schema paths.

        Args:
            capability_id: If provided, only schemas for this capability.
                          If None, returns all registered schemas.

        Returns:
            List of schema file paths
        """
        ...

    def get_mode_config(self, mode_id: str) -> Optional[DomainModeConfig]:
        """Get mode configuration by mode ID.

        Args:
            mode_id: Mode identifier (e.g., "code_analysis")

        Returns:
            DomainModeConfig if registered, None otherwise
        """
        ...

    def is_mode_registered(self, mode_id: str) -> bool:
        """Check if a mode is registered.

        Args:
            mode_id: Mode identifier

        Returns:
            True if mode is registered
        """
        ...

    def list_modes(self) -> List[str]:
        """List all registered mode IDs.

        Returns:
            List of mode identifiers
        """
        ...

    def register_service(self, capability_id: str, service_config: "DomainServiceConfig") -> None:
        """Register a service for a capability.

        Args:
            capability_id: Unique capability identifier
            service_config: Service configuration
        """
        ...

    def get_services(self, capability_id: Optional[str] = None) -> List["DomainServiceConfig"]:
        """Get registered service configurations.

        Args:
            capability_id: If provided, only services for this capability.
                          If None, returns all registered services.

        Returns:
            List of service configurations
        """
        ...

    def get_default_service(self) -> Optional[str]:
        """Get the default service name.

        Returns the service marked as default, or the first registered service,
        or None if no services are registered.

        Returns:
            Service name or None
        """
        ...

    def list_capabilities(self) -> List[str]:
        """List all registered capability IDs.

        Returns:
            List of capability identifiers
        """
        ...


class CapabilityResourceRegistry:
    """Default implementation of CapabilityResourceRegistryProtocol.

    Thread-safe registry for capability resources.

    Extended to support:
    - Orchestrator registration (factory for creating orchestrator services)
    - Tools registration (factory for initializing tools)
    - Prompts registration (prompt templates)
    - Agents registration (agent definitions for governance)
    - Contracts registration (tool result contracts)
    """

    def __init__(self):
        self._schemas: Dict[str, List[str]] = {}
        self._modes: Dict[str, DomainModeConfig] = {}
        self._capability_modes: Dict[str, List[str]] = {}
        self._services: Dict[str, DomainServiceConfig] = {}
        self._capability_services: Dict[str, List[str]] = {}
        self._capabilities: List[str] = []
        # Extended registrations
        self._orchestrators: Dict[str, CapabilityOrchestratorConfig] = {}
        self._tools: Dict[str, CapabilityToolsConfig] = {}
        self._prompts: Dict[str, List[CapabilityPromptConfig]] = {}
        self._agents: Dict[str, List[DomainAgentConfig]] = {}
        self._contracts: Dict[str, CapabilityContractsConfig] = {}

    def _track_capability(self, capability_id: str) -> None:
        """Track a capability ID if not already tracked."""
        if capability_id not in self._capabilities:
            self._capabilities.append(capability_id)

    def register_schema(self, capability_id: str, schema_path: str) -> None:
        """Register a database schema for a capability."""
        self._track_capability(capability_id)
        if capability_id not in self._schemas:
            self._schemas[capability_id] = []
        if schema_path not in self._schemas[capability_id]:
            self._schemas[capability_id].append(schema_path)

    def register_mode(self, capability_id: str, mode_config: DomainModeConfig) -> None:
        """Register a gateway mode for a capability."""
        self._track_capability(capability_id)
        self._modes[mode_config.mode_id] = mode_config
        if capability_id not in self._capability_modes:
            self._capability_modes[capability_id] = []
        if mode_config.mode_id not in self._capability_modes[capability_id]:
            self._capability_modes[capability_id].append(mode_config.mode_id)

    def get_schemas(self, capability_id: Optional[str] = None) -> List[str]:
        """Get registered schema paths."""
        if capability_id:
            return self._schemas.get(capability_id, [])
        # Return all schemas flattened
        all_schemas = []
        for schemas in self._schemas.values():
            all_schemas.extend(schemas)
        return all_schemas

    def get_mode_config(self, mode_id: str) -> Optional[DomainModeConfig]:
        """Get mode configuration by mode ID."""
        return self._modes.get(mode_id)

    def is_mode_registered(self, mode_id: str) -> bool:
        """Check if a mode is registered."""
        return mode_id in self._modes

    def list_modes(self) -> List[str]:
        """List all registered mode IDs."""
        return list(self._modes.keys())

    def register_service(self, capability_id: str, service_config: DomainServiceConfig) -> None:
        """Register a service for a capability."""
        self._track_capability(capability_id)
        self._services[service_config.service_id] = service_config
        if capability_id not in self._capability_services:
            self._capability_services[capability_id] = []
        if service_config.service_id not in self._capability_services[capability_id]:
            self._capability_services[capability_id].append(service_config.service_id)

    def get_services(self, capability_id: Optional[str] = None) -> List[DomainServiceConfig]:
        """Get registered service configurations."""
        if capability_id:
            service_ids = self._capability_services.get(capability_id, [])
            return [self._services[sid] for sid in service_ids if sid in self._services]
        return list(self._services.values())

    def get_service_config(self, service_id: str) -> Optional[DomainServiceConfig]:
        """Get service configuration by service ID."""
        return self._services.get(service_id)

    def get_default_service(self) -> Optional[str]:
        """Get the default service name.

        Returns the service marked as default, or the first registered service,
        or None if no services are registered.
        """
        # First, look for explicitly marked default
        for service in self._services.values():
            if service.is_default:
                return service.service_id
        # Otherwise, return first registered service
        if self._services:
            return next(iter(self._services.keys()))
        return None

    def list_capabilities(self) -> List[str]:
        """List all registered capability IDs."""
        return list(self._capabilities)

    # =========================================================================
    # Extended Registration Methods (Layer Extraction Support)
    # =========================================================================

    def register_orchestrator(
        self,
        capability_id: str,
        config: CapabilityOrchestratorConfig,
    ) -> None:
        """Register an orchestrator factory for a capability.

        The orchestrator factory creates the service that handles requests.
        Infrastructure calls this factory instead of importing directly.

        Args:
            capability_id: Unique capability identifier
            config: Orchestrator configuration with factory function
        """
        self._track_capability(capability_id)
        self._orchestrators[capability_id] = config

    def get_orchestrator(
        self,
        capability_id: Optional[str] = None,
    ) -> Optional[CapabilityOrchestratorConfig]:
        """Get orchestrator configuration.

        Args:
            capability_id: If provided, get for this capability.
                          If None, returns the first registered (default).

        Returns:
            CapabilityOrchestratorConfig or None
        """
        if capability_id:
            return self._orchestrators.get(capability_id)
        # Return first registered orchestrator as default
        if self._orchestrators:
            return next(iter(self._orchestrators.values()))
        return None

    def register_tools(
        self,
        capability_id: str,
        config: CapabilityToolsConfig,
    ) -> None:
        """Register a tools initializer for a capability.

        The tools initializer creates the tool catalog.
        Infrastructure calls this instead of importing directly.

        Args:
            capability_id: Unique capability identifier
            config: Tools configuration with initializer function
        """
        self._track_capability(capability_id)
        self._tools[capability_id] = config

    def get_tools(
        self,
        capability_id: Optional[str] = None,
    ) -> Optional[CapabilityToolsConfig]:
        """Get tools configuration.

        Args:
            capability_id: If provided, get for this capability.
                          If None, returns the first registered (default).

        Returns:
            CapabilityToolsConfig or None
        """
        if capability_id:
            return self._tools.get(capability_id)
        # Return first registered tools as default
        if self._tools:
            return next(iter(self._tools.values()))
        return None

    def register_prompts(
        self,
        capability_id: str,
        prompts: List[CapabilityPromptConfig],
    ) -> None:
        """Register prompts for a capability.

        Args:
            capability_id: Unique capability identifier
            prompts: List of prompt configurations
        """
        self._track_capability(capability_id)
        if capability_id not in self._prompts:
            self._prompts[capability_id] = []
        self._prompts[capability_id].extend(prompts)

    def get_prompts(
        self,
        capability_id: Optional[str] = None,
    ) -> List[CapabilityPromptConfig]:
        """Get registered prompts.

        Args:
            capability_id: If provided, only prompts for this capability.
                          If None, returns all registered prompts.

        Returns:
            List of prompt configurations
        """
        if capability_id:
            return self._prompts.get(capability_id, [])
        # Return all prompts flattened
        all_prompts = []
        for prompts in self._prompts.values():
            all_prompts.extend(prompts)
        return all_prompts

    def register_agents(
        self,
        capability_id: str,
        agents: List[DomainAgentConfig],
    ) -> None:
        """Register agent definitions for a capability.

        Used by governance service to discover agents dynamically.

        Args:
            capability_id: Unique capability identifier
            agents: List of agent configurations
        """
        self._track_capability(capability_id)
        if capability_id not in self._agents:
            self._agents[capability_id] = []
        self._agents[capability_id].extend(agents)

    def get_agents(
        self,
        capability_id: Optional[str] = None,
    ) -> List[DomainAgentConfig]:
        """Get registered agents.

        Args:
            capability_id: If provided, only agents for this capability.
                          If None, returns all registered agents.

        Returns:
            List of agent configurations
        """
        if capability_id:
            return self._agents.get(capability_id, [])
        # Return all agents flattened
        all_agents = []
        for agents in self._agents.values():
            all_agents.extend(agents)
        return all_agents

    def register_contracts(
        self,
        capability_id: str,
        config: CapabilityContractsConfig,
    ) -> None:
        """Register tool result contracts for a capability.

        Args:
            capability_id: Unique capability identifier
            config: Contracts configuration
        """
        self._track_capability(capability_id)
        self._contracts[capability_id] = config

    def get_contracts(
        self,
        capability_id: Optional[str] = None,
    ) -> Optional[CapabilityContractsConfig]:
        """Get contracts configuration.

        Args:
            capability_id: If provided, get for this capability.
                          If None, returns the first registered (default).

        Returns:
            CapabilityContractsConfig or None
        """
        if capability_id:
            return self._contracts.get(capability_id)
        # Return first registered contracts as default
        if self._contracts:
            return next(iter(self._contracts.values()))
        return None

    def clear(self) -> None:
        """Clear all registrations. Primarily for testing."""
        self._schemas.clear()
        self._modes.clear()
        self._capability_modes.clear()
        self._services.clear()
        self._capability_services.clear()
        self._capabilities.clear()
        # Clear extended registrations
        self._orchestrators.clear()
        self._tools.clear()
        self._prompts.clear()
        self._agents.clear()
        self._contracts.clear()


# =============================================================================
# GLOBAL REGISTRY (Lazy Initialization)
# =============================================================================

_resource_registry: Optional[CapabilityResourceRegistry] = None


def get_capability_resource_registry() -> CapabilityResourceRegistry:
    """Get the global capability resource registry instance.

    Creates a new instance lazily if none exists.

    Returns:
        Global CapabilityResourceRegistry instance
    """
    global _resource_registry
    if _resource_registry is None:
        _resource_registry = CapabilityResourceRegistry()
    return _resource_registry


def reset_capability_resource_registry() -> None:
    """Reset the global registry instance. Primarily for testing."""
    global _resource_registry
    _resource_registry = None


__all__ = [
    # Tool catalog (capability-scoped)
    "ToolCatalogEntry",
    "ToolDefinition",
    "CapabilityToolCatalog",
    # Config types
    "DomainServiceConfig",
    "DomainModeConfig",
    "DomainAgentConfig",
    "CapabilityPromptConfig",
    "CapabilityToolsConfig",
    "CapabilityOrchestratorConfig",
    "CapabilityContractsConfig",
    # Registry protocol and implementation
    "CapabilityResourceRegistryProtocol",
    "CapabilityResourceRegistry",
    "get_capability_resource_registry",
    "reset_capability_resource_registry",
]
