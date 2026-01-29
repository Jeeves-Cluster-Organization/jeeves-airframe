"""Feature flags for phased rollout of new capabilities.

This module provides runtime toggles for new features being developed
across the phased implementation roadmap. Feature flags allow us to:
- Deploy code without immediately enabling it
- Test new features in production with gradual rollout
- Quick rollback by toggling flags without code changes
- A/B testing and canary deployments
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from dataclasses import dataclass
from typing import Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from jeeves_infra.protocols import LoggerProtocol


# ============================================================
# Cyclic Orchestrator Configuration (v0.13)
# Per Amendment V: No modes. The cyclic flow is the only flow.
# ============================================================

@dataclass
class CyclicConfig:
    """Configuration for the cyclic orchestrator.

    Per CYCLIC_MIGRATION_PLAN.md v2.1:
    - max_llm_calls: Hard limit on LLM invocations per request
    - max_iterations: Hard limit on plan-execute-draft-critique cycles
    - critic_confidence_threshold: Minimum confidence for Critic to honor retry/clarify actions
    - max_validator_retries: Max Critic → Validator retries per request
    - max_planner_retries: Max Critic → Planner retries per request

    No mode enum. The cyclic flow is the only flow.
    """
    max_llm_calls: int = 10
    max_iterations: int = 3
    critic_confidence_threshold: float = 0.6

    # v0.14: Retry limits for micro-loop (moved from hardcoded values in CriticNode)
    max_validator_retries: int = 1
    max_planner_retries: int = 1


# Global cyclic config instance
cyclic_config = CyclicConfig()


# ============================================================
# Context Bounds Configuration
# ============================================================

@dataclass
class ContextBoundsConfig:
    """Configuration for context window bounds.

    These bounds prevent context explosion by limiting how much
    data from each memory layer can be included in LLM prompts.

    Designed for local models with ~4K-16K context windows.
    """
    # L1: Task Context
    max_task_context_chars: int = 2000

    # L3: Semantic Memory
    max_semantic_snippets: int = 5
    max_semantic_chars_per_snippet: int = 400  # ~100 tokens each
    max_semantic_chars_total: int = 1500

    # L4: Working Memory (conversation history)
    max_open_loops: int = 5
    max_conversation_turns: int = 10
    max_conversation_chars: int = 3000

    # L5: Graph Context
    max_graph_relationships: int = 4

    # Execution History
    max_prior_plans: int = 2
    max_prior_tool_results: int = 10

    # Total Budget
    max_total_context_chars: int = 10000  # ~2500 tokens


# Global context bounds instance
context_bounds = ContextBoundsConfig()


def get_context_bounds() -> ContextBoundsConfig:
    """Get the global context bounds configuration.

    Returns:
        Global ContextBoundsConfig instance
    """
    return context_bounds


class FeatureFlags(BaseSettings):
    """Runtime toggles for new features across implementation phases.

    All flags default to False (disabled) for safety. Enable via environment
    variables (FEATURE_USE_LLM_GATEWAY=true) or in .env file.

    Phase ownership:
    - Phase 1: use_llm_gateway, use_redis_state
    - Phase 2: use_graph_engine, enable_checkpoints
    - Phase 3: enable_distributed_mode, enable_node_discovery
    - Phase 4: enable_tracing, enable_metrics_export
    """

    # Phase 1: LLM Gateway + Redis State
    use_llm_gateway: bool = False
    """Enable unified LLM gateway with cost tracking and provider fallback.

    When enabled:
    - All LLM calls route through gateway.LLMGateway
    - Cost tracking per request (tokens, latency, cost_usd)
    - Automatic fallback between providers on failure

    Rollback: Set to False to use direct provider calls
    """

    use_redis_state: bool = False
    """Enable Redis for shared state (rate limiting, locks, cache).

    When enabled:
    - Rate limiter uses Redis (distributed-safe)
    - Embedding cache stored in Redis
    - Distributed locks available

    Requires: REDIS_URL environment variable
    Rollback: Set to False to use in-memory state
    """

    # Phase 2: Graph-Based Workflow Engine
    use_graph_engine: bool = False
    """Enable graph-based workflow execution instead of linear pipeline.

    When enabled:
    - Orchestrator uses WorkflowEngine with graph definition
    - Conditional routing based on confidence scores
    - Support for pause/resume workflows

    Rollback: Set to False to use linear pipeline
    """

    enable_checkpoints: bool = False
    """Enable workflow state persistence for pause/resume.

    When enabled:
    - State saved to execution_checkpoints table after each step
    - Can restart server and resume in-flight workflows
    - Human-in-the-loop support at any graph node

    Requires: use_graph_engine=True
    Rollback: Set to False to run workflows to completion
    """

    # Phase 3: LAN Deployment + Node Registry
    enable_distributed_mode: bool = False
    """Enable multi-node deployment across local network.

    When enabled:
    - LLM requests routed to GPU nodes based on model availability
    - Node registry tracks available hardware
    - Automatic failover on node failure

    Requires: REDIS_URL for node coordination
    Rollback: Set to False to use single-node mode
    """

    enable_node_discovery: bool = False
    """Enable automatic GPU node discovery and health monitoring.

    When enabled:
    - Node agents report capabilities via heartbeat
    - TTL-based health tracking (nodes expire after 60s)
    - Dynamic routing based on current load

    Requires: enable_distributed_mode=True
    Rollback: Set to False for static node configuration
    """

    # Phase 4: Observability + Production Hardening
    enable_tracing: bool = False
    """Enable OpenTelemetry distributed tracing.

    When enabled:
    - Full request traces with per-agent spans
    - Cost and latency metrics attached to spans
    - Export to Jaeger/OTLP endpoint

    Requires: OTEL_EXPORTER_JAEGER_ENDPOINT environment variable
    Rollback: Set to False for zero tracing overhead
    """

    enable_metrics_export: bool = False
    """Enable Prometheus metrics export.

    When enabled:
    - /metrics endpoint exposes Prometheus format
    - Request rate, latency, cost counters/histograms
    - Per-agent and per-provider breakdowns

    Rollback: Set to False to disable metrics collection
    """

    # Development/Testing flags
    enable_debug_logging: bool = False
    """Enable verbose debug logging for development.

    When enabled:
    - Log level set to DEBUG for all components
    - Additional diagnostic information in logs
    - Performance impact: ~10% latency increase
    """

    # Phase 2.3: Agent reasoning observability (config-gated)
    emit_agent_reasoning: bool = False
    """Enable emission of agent reasoning/CoT events.

    When enabled:
    - Agent reasoning text is emitted as observable events
    - Truncated to max 500 chars for streaming efficiency
    - Lives entirely in mission/avionics layer (no core changes)

    Constitutional compliance: P2 (Code Context Priority)
    - Provides visibility into agent decision-making
    - Does not affect core data structures

    Rollback: Set to False to disable reasoning emission
    """

    # ============================================================
    # V2 Memory Infrastructure Feature Flags
    # v1.0 Hardening: All memory layers enabled by default
    # ============================================================
    # Phase M1: Event Sourcing & Agent Tracing (L2)
    memory_event_sourcing_mode: Literal["disabled", "log_only", "log_and_project"] = "log_and_project"
    """Enable event sourcing for state changes.

    Modes:
    - disabled: No event emission
    - log_only: Emit events but don't use for projections
    - log_and_project: Full event sourcing with replay capability (v1.0 default)

    Rollback: Set to 'disabled' to stop event emission
    """

    memory_agent_tracing: bool = True
    """Enable agent decision tracing.

    When enabled:
    - All agent decisions recorded in agent_traces table
    - Full input/output capture for debugging
    - Latency and token metrics per agent

    v1.0 default: True (essential for observability)
    Rollback: Set to False to disable trace recording
    """

    memory_trace_retention_days: int = 30
    """Number of days to retain agent traces before archival."""

    # Phase M2: Semantic Memory (L3)
    memory_semantic_mode: Literal["disabled", "log_only", "log_and_use"] = "log_and_use"
    """Enable semantic chunk management.

    Modes:
    - disabled: Use legacy embedding approach
    - log_only: Create chunks but don't use in search
    - log_and_use: Full semantic search with source binding (v1.0 default)

    Rollback: Set to 'disabled' for legacy SQL keyword search
    """

    memory_embedding_model: str = "all-MiniLM-L6-v2"
    """Sentence-transformers model for embeddings."""

    # Phase M2: Working Memory (L4)
    memory_working_memory: bool = True
    """Enable working memory with session summarization.

    When enabled:
    - Sessions are summarized based on triggers
    - Open loops are tracked and surfaced
    - Context is bounded and compressed

    v1.0 default: True (essential for context management)
    Rollback: Set to False for unbounded context
    """

    memory_summarization_threshold_turns: int = 8
    """Number of turns before triggering summarization."""

    memory_summarization_threshold_tokens: int = 6000
    """Estimated token count before triggering summarization."""

    # Phase M3: State Graph (L5)
    memory_graph_mode: Literal["disabled", "enabled"] = "enabled"
    """Enable graph-based relationship tracking.

    When enabled:
    - Entities are tracked as graph nodes
    - Relationships captured as typed edges
    - Graph queries available for related items

    v1.0 default: enabled
    Rollback: Set to 'disabled' to use legacy memory_cross_refs
    """

    memory_auto_edge_extraction: bool = True
    """Enable automatic edge extraction from content.

    When enabled:
    - LLM extracts relationships from text
    - Edges created automatically with provenance

    v1.0 default: True
    Requires: memory_graph_mode='enabled'
    """

    # Phase M4: Meta-Governance (L7)
    memory_governance_mode: Literal["disabled", "log_only", "log_and_enforce"] = "log_only"
    """Enable meta-governance for tool and prompt management.

    Modes:
    - disabled: No governance tracking
    - log_only: Track metrics but don't enforce policies (v1.0 default)
    - log_and_enforce: Full governance with auto-quarantine

    Rollback: Set to 'disabled' to stop governance
    """

    memory_tool_quarantine: bool = False
    """Enable automatic tool quarantine on high error rates.

    v1.0 default: False (monitor first, enforce later)
    Requires: memory_governance_mode in ['log_only', 'log_and_enforce']
    """

    memory_prompt_versioning: bool = True
    """Enable prompt version tracking.

    When enabled:
    - All prompt changes are versioned
    - Domain events emitted on prompt updates

    v1.0 default: True
    """

    model_config = SettingsConfigDict(
        env_prefix="FEATURE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    def log_status(self, logger: "LoggerProtocol") -> None:
        """Log current feature flag status using structured logging.

        Args:
            logger: Logger instance for structured output
        """
        logger.info(
            "feature_flags_status",
            # Phase 1 - LLM Gateway + Redis
            use_llm_gateway=self.use_llm_gateway,
            use_redis_state=self.use_redis_state,
            # Phase 2 - Graph Workflow
            use_graph_engine=self.use_graph_engine,
            enable_checkpoints=self.enable_checkpoints,
            # Phase 3 - Distributed Mode
            enable_distributed_mode=self.enable_distributed_mode,
            enable_node_discovery=self.enable_node_discovery,
            # Phase 4 - Observability
            enable_tracing=self.enable_tracing,
            enable_metrics_export=self.enable_metrics_export,
            # V2 Memory Infrastructure
            memory_event_sourcing=self.memory_event_sourcing_mode,
            memory_agent_tracing=self.memory_agent_tracing,
            memory_semantic_mode=self.memory_semantic_mode,
            memory_working_memory=self.memory_working_memory,
            memory_graph_mode=self.memory_graph_mode,
            memory_governance_mode=self.memory_governance_mode,
            # Development
            enable_debug_logging=self.enable_debug_logging,
        )

    def validate_dependencies(self) -> list[str]:
        """Validate that dependent features are properly enabled.

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        if self.enable_checkpoints and not self.use_graph_engine:
            errors.append(
                "enable_checkpoints requires use_graph_engine=True"
            )

        if self.enable_node_discovery and not self.enable_distributed_mode:
            errors.append(
                "enable_node_discovery requires enable_distributed_mode=True"
            )

        if self.enable_distributed_mode and not self.use_redis_state:
            errors.append(
                "enable_distributed_mode requires use_redis_state=True "
                "(Redis needed for node coordination)"
            )

        # V2 Memory Infrastructure dependencies
        if self.memory_auto_edge_extraction and self.memory_graph_mode == "disabled":
            errors.append(
                "memory_auto_edge_extraction requires memory_graph_mode='enabled'"
            )

        if self.memory_tool_quarantine and self.memory_governance_mode == "disabled":
            errors.append(
                "memory_tool_quarantine requires memory_governance_mode in "
                "['log_only', 'log_and_enforce']"
            )

        return errors


# Lazy initialization - no module-level instantiation (ADR-001 compliance)
_feature_flags: Optional[FeatureFlags] = None


def get_feature_flags() -> FeatureFlags:
    """Get the global feature flags instance.

    Creates a new FeatureFlags instance lazily if none exists.
    Prefer dependency injection over this global getter for testability.

    Returns:
        Global FeatureFlags instance
    """
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags()
    return _feature_flags


def set_feature_flags(flags: FeatureFlags) -> None:
    """Set the global feature flags instance.

    Use at bootstrap time to inject pre-configured flags.
    Primarily for testing purposes.

    Args:
        flags: FeatureFlags instance to use as global
    """
    global _feature_flags
    _feature_flags = flags


def reset_feature_flags() -> None:
    """Reset the global feature flags instance.

    Forces re-creation on next get_feature_flags() call.
    Primarily for testing purposes.
    """
    global _feature_flags
    _feature_flags = None
