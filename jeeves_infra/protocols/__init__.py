# Jeeves Protocol Types
#
# Code is the contract. Python dataclasses define the schema.
# No proto dependency.

# =============================================================================
# PYTHON DATACLASS TYPES (with methods - use these in application code)
# =============================================================================

from jeeves_infra.protocols.types import (
    # Enums (string-based)
    TerminalReason,
    InterruptKind,
    InterruptStatus,
    RiskLevel,
    ToolCategory,
    ToolAccess,
    HealthStatus,
    LoopVerdict,
    RiskApproval,
    OperationStatus,
    RunMode,
    JoinStrategy,
    AgentOutputMode,
    TokenStreamMode,
    AgentCapability,
    # Dataclass types with methods
    OperationResult,
    InterruptResponse,
    FlowInterrupt,
    RateLimitConfig,
    RateLimitResult,
    ProcessingRecord,
    PipelineEvent,
    RoutingRule,
    EdgeLimit,
    GenerationParams,
    AgentConfig,
    PipelineConfig,
    ContextBounds,
    ExecutionConfig,
    OrchestrationFlags,
    Envelope,
    # Protocols
    InterruptServiceProtocol,
)

# =============================================================================
# PYTHON PROTOCOL INTERFACES
# =============================================================================

from jeeves_infra.protocols.interfaces import (
    RequestContext,
    LoggerProtocol,
    DatabaseClientProtocol,
    LLMProviderProtocol,
    ToolProtocol,
    ToolDefinitionProtocol,
    ToolRegistryProtocol,
    SettingsProtocol,
    FeatureFlagsProtocol,
    ClockProtocol,
    AppContextProtocol,
    SearchResult,
    SemanticSearchProtocol,
    SessionStateProtocol,
    DistributedTask,
    QueueStats,
    DistributedBusProtocol,
    EventBusProtocol,
    ToolExecutorProtocol,
    ConfigRegistryProtocol,
    AgentLLMConfig,
    AgentToolAccessProtocol,
    WebSocketManagerProtocol,
    EventBridgeProtocol,
    SessionStateServiceProtocol,
)

# =============================================================================
# CAPABILITY REGISTRATION (moved from jeeves-core/protocols)
# =============================================================================

from jeeves_infra.protocols.capability import (
    get_capability_resource_registry,
    reset_capability_resource_registry,
    CapabilityResourceRegistry,
    CapabilityResourceRegistryProtocol,
    CapabilityToolCatalog,
    ToolCatalogEntry,
    ToolDefinition,
    DomainAgentConfig,
    CapabilityPromptConfig,
    CapabilityToolsConfig,
    CapabilityOrchestratorConfig,
    CapabilityContractsConfig,
    DomainServiceConfig,
    DomainModeConfig,
)

# =============================================================================
# RUNTIME COMPONENTS (Agent, PipelineRunner, etc.)
# =============================================================================

from jeeves_infra.runtime.agents import (
    Agent,
    Persistence,
    PipelineRunner,
    create_pipeline_runner,
    create_envelope,
    OptionalCheckpoint,
)
from jeeves_infra.runtime.persistence import DatabasePersistence

# =============================================================================
# UTILITIES
# =============================================================================

from jeeves_infra.utils.json_repair import JSONRepairKit
from jeeves_infra.utils.strings import normalize_string_list

__all__ = [
    # Enums
    "TerminalReason",
    "InterruptKind",
    "InterruptStatus",
    "RiskLevel",
    "ToolCategory",
    "ToolAccess",
    "HealthStatus",
    "LoopVerdict",
    "RiskApproval",
    "OperationStatus",
    "RunMode",
    "JoinStrategy",
    "AgentOutputMode",
    "TokenStreamMode",
    "AgentCapability",
    # Dataclass types
    "OperationResult",
    "InterruptResponse",
    "FlowInterrupt",
    "RateLimitConfig",
    "RateLimitResult",
    "ProcessingRecord",
    "PipelineEvent",
    "RoutingRule",
    "EdgeLimit",
    "GenerationParams",
    "AgentConfig",
    "PipelineConfig",
    "ContextBounds",
    "ExecutionConfig",
    "OrchestrationFlags",
    "Envelope",
    # Protocol interfaces
    "RequestContext",
    "LoggerProtocol",
    "DatabaseClientProtocol",
    "LLMProviderProtocol",
    "ToolProtocol",
    "ToolDefinitionProtocol",
    "ToolRegistryProtocol",
    "SettingsProtocol",
    "FeatureFlagsProtocol",
    "ClockProtocol",
    "AppContextProtocol",
    "SearchResult",
    "SemanticSearchProtocol",
    "SessionStateProtocol",
    "DistributedTask",
    "QueueStats",
    "DistributedBusProtocol",
    "EventBusProtocol",
    "ToolExecutorProtocol",
    "ConfigRegistryProtocol",
    "AgentLLMConfig",
    "AgentToolAccessProtocol",
    "WebSocketManagerProtocol",
    "EventBridgeProtocol",
    "SessionStateServiceProtocol",
    "InterruptServiceProtocol",
    # Capability registration
    "get_capability_resource_registry",
    "reset_capability_resource_registry",
    "CapabilityResourceRegistry",
    "CapabilityResourceRegistryProtocol",
    "CapabilityToolCatalog",
    "ToolCatalogEntry",
    "ToolDefinition",
    "DomainAgentConfig",
    "CapabilityPromptConfig",
    "CapabilityToolsConfig",
    "CapabilityOrchestratorConfig",
    "CapabilityContractsConfig",
    "DomainServiceConfig",
    "DomainModeConfig",
    # Runtime components
    "Agent",
    "Persistence",
    "DatabasePersistence",
    "PipelineRunner",
    "create_pipeline_runner",
    "create_envelope",
    "OptionalCheckpoint",
    # Utilities
    "JSONRepairKit",
    "normalize_string_list",
]
