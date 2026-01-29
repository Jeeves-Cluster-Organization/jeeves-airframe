"""
Mission System Contracts - Static Type Definitions for App Integration.

Centralized Architecture (v4.0):
This module re-exports unified agent types from protocols:
- AgentConfig, PipelineConfig: Declarative agent definitions
- Agent: Single agent class driven by configuration
- Envelope: Dynamic output slots
- ToolAccess: Agent tool access levels

All types come from protocols (Python bridge to Go core).
"""

# =============================================================================
# CANONICAL PROTOCOLS (from protocols)
# =============================================================================
from jeeves_infra.protocols import (
    # App context protocols
    SettingsProtocol,
    FeatureFlagsProtocol,
    AppContextProtocol,
    LoggerProtocol,
    ClockProtocol,
    # Infrastructure protocols
    PersistenceProtocol,
    LLMProviderProtocol,
    ToolRegistryProtocol,
    IntentParsingProtocol,
    ClaimVerificationProtocol,
    # Risk level
    RiskLevel,
)

# =============================================================================
# CENTRALIZED AGENT ARCHITECTURE
# =============================================================================
from jeeves_infra.protocols import (
    # Agent configuration
    AgentConfig,
    PipelineConfig,
    RoutingRule,
    ToolAccess,
    # Unified agent
    Agent,
    # Generic envelope
    Envelope,
    ProcessingRecord,
    create_envelope,
    # Enums
    TerminalReason,
    LoopVerdict,
    RiskApproval,
)

# Unified runtime
from jeeves_infra.protocols import (
    PipelineRunner,
    create_pipeline_runner,
)

# Core protocols from core_engine
from jeeves_infra.protocols import (
    ToolProtocol,
    EventBusProtocol,
    MemoryServiceProtocol,
    IdGeneratorProtocol,
    ToolExecutorProtocol,
    ConfigRegistryProtocol,
)

# Working memory base class
from jeeves_infra.protocols import WorkingMemory, Finding

# Configuration types (ContextBounds only - access bounds via AppContext.get_context_bounds())
from jeeves_infra.protocols import ContextBounds

# JSON utilities
from jeeves_infra.protocols import (
    JSONRepairKit,
    normalize_string_list,
)

# NOTE: AgentPipelineRunner removed in v4.0 - use PipelineRunner + Agent
# Agent handles all agent-level services (logging, events, persistence)

# Config registry
from mission_system.config.registry import (
    ConfigRegistry,
    ConfigKeys,
    get_config_registry,
    set_config_registry,
    reset_config_registry,
)

# Agent profiles (generic types - capability-specific profiles in capability layer)
# See: jeeves-capability-code-analyser/config/llm_config.py
from mission_system.config.agent_profiles import (
    LLMProfile,
    ThresholdProfile,
    AgentProfile,
    get_agent_profile,
    get_llm_profile,
    get_thresholds,
    get_latency_budget,
)

# NOTE: Tool catalog types (ToolId, ToolCatalog, etc.) are OWNED BY CAPABILITIES
# NOT re-exported here. Capability layers should import from their own tools/catalog.py.
# See: jeeves-capability-code-analyser/tools/catalog.py for code_analysis capability.
# ToolCategory and RiskLevel come from jeeves_core.types (Go kernel).
from jeeves_infra.protocols import ToolCategory

# NOTE: AgentContext removed in v4.0 - context flows through Envelope

__all__ = [
    # ─── Centralized Agent Architecture ───
    # Agent configuration
    "AgentConfig",
    "PipelineConfig",
    "RoutingRule",
    "ToolAccess",
    # Unified agent
    "Agent",
    # Generic envelope
    "Envelope",
    "ProcessingRecord",
    "create_envelope",
    # Unified runtime
    "PipelineRunner",
    "create_pipeline_runner",
    # Enums
    "TerminalReason",
    "LoopVerdict",
    "RiskApproval",

    # ─── Working memory ───
    "WorkingMemory",
    "Finding",

    # ─── Canonical Protocols (from jeeves_commbus) ───
    "SettingsProtocol",
    "FeatureFlagsProtocol",
    "AppContextProtocol",
    "LoggerProtocol",
    "ClockProtocol",
    "PersistenceProtocol",
    "LLMProviderProtocol",
    "ToolRegistryProtocol",
    "IntentParsingProtocol",
    "ClaimVerificationProtocol",
    "RiskLevel",

    # ─── Core protocols (from core_engine) ───
    "ToolProtocol",
    "EventBusProtocol",
    "MemoryServiceProtocol",
    "IdGeneratorProtocol",
    "ToolExecutorProtocol",
    "ConfigRegistryProtocol",

    # ─── Configuration (access bounds via AppContext.get_context_bounds()) ───
    "ContextBounds",

    # ─── JSON utilities ───
    "JSONRepairKit",
    "normalize_string_list",

    # ─── Config Registry ───
    "ConfigRegistry",
    "ConfigKeys",
    "get_config_registry",
    "set_config_registry",
    "reset_config_registry",

    # ─── Agent Profiles (generic types) ───
    # Capability-specific profiles in: jeeves-capability-code-analyser/config/llm_config.py
    "LLMProfile",
    "ThresholdProfile",
    "AgentProfile",
    "get_agent_profile",
    "get_llm_profile",
    "get_thresholds",
    "get_latency_budget",

    # ─── Tool Types (from protocols) ───
    # NOTE: ToolId, ToolCatalog, etc. are CAPABILITY-OWNED (not re-exported here)
    # Capabilities import from their own tools/catalog.py
    "ToolCategory",  # From protocols

]
