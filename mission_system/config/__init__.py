"""Configuration package for the mission system.

Generic configuration types are defined here.
Capability-specific agent profiles have been moved to capability layer.

Constitutional Reference:
    - Mission System: Provides generic config mechanisms
    - Capability Constitution R6: Domain Config Ownership
    - Agent profiles moved to: jeeves-capability-code-analyser/config/llm_config.py
"""

from mission_system.config.constants import (
    # Platform Identity
    PLATFORM_NAME,
    PLATFORM_VERSION,
    PLATFORM_DESCRIPTION,
    AGENT_ARCHITECTURE,
    AGENT_COUNT,
    # Fuzzy Matching
    FUZZY_MATCH_THRESHOLD,
    FUZZY_MATCH_CONFIDENCE_THRESHOLD,
    FUZZY_MATCH_SUBSTRING_WEIGHT,
    FUZZY_MATCH_WORD_OVERLAP_WEIGHT,
    FUZZY_MATCH_CHAR_SIMILARITY_WEIGHT,
    FUZZY_MATCH_SECONDARY_WEIGHT,
    # Task Management
    TASK_PRIORITY_LOW,
    TASK_PRIORITY_MEDIUM,
    TASK_PRIORITY_HIGH,
    TASK_DEFAULT_PRIORITY,
    TASK_DEFAULT_STATUS,
    TASK_CANDIDATE_LIMIT,
    TASK_QUERY_LIMIT,
    # Database Query Limits
    DB_DEFAULT_LIMIT,
    DB_RECENT_TASKS_LIMIT,
    DB_CONVERSATION_HISTORY_LIMIT,
    # Timeout Values
    LLM_REQUEST_TIMEOUT,
    DB_QUERY_TIMEOUT,
    TOOL_EXECUTION_TIMEOUT,
    # Error Handling
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_INITIAL_DELAY,
    # Response Limits
    VALIDATOR_RESPONSE_WORD_LIMIT,
)

from mission_system.config.agent_profiles import (
    LLMProfile,
    ThresholdProfile,
    AgentProfile,
    get_agent_profile,
    get_llm_profile,
    get_thresholds,
    get_latency_budget,
)

from mission_system.config.registry import (
    ConfigRegistry,
    ConfigKeys,
    get_config_registry,
    set_config_registry,
    reset_config_registry,
)

__all__ = [
    # Platform Identity
    "PLATFORM_NAME",
    "PLATFORM_VERSION",
    "PLATFORM_DESCRIPTION",
    "AGENT_ARCHITECTURE",
    "AGENT_COUNT",
    # Fuzzy Matching
    "FUZZY_MATCH_THRESHOLD",
    "FUZZY_MATCH_CONFIDENCE_THRESHOLD",
    "FUZZY_MATCH_SUBSTRING_WEIGHT",
    "FUZZY_MATCH_WORD_OVERLAP_WEIGHT",
    "FUZZY_MATCH_CHAR_SIMILARITY_WEIGHT",
    "FUZZY_MATCH_SECONDARY_WEIGHT",
    # Task Management
    "TASK_PRIORITY_LOW",
    "TASK_PRIORITY_MEDIUM",
    "TASK_PRIORITY_HIGH",
    "TASK_DEFAULT_PRIORITY",
    "TASK_DEFAULT_STATUS",
    "TASK_CANDIDATE_LIMIT",
    "TASK_QUERY_LIMIT",
    # Database Query Limits
    "DB_DEFAULT_LIMIT",
    "DB_RECENT_TASKS_LIMIT",
    "DB_CONVERSATION_HISTORY_LIMIT",
    # Timeout Values
    "LLM_REQUEST_TIMEOUT",
    "DB_QUERY_TIMEOUT",
    "TOOL_EXECUTION_TIMEOUT",
    # Error Handling
    "MAX_RETRY_ATTEMPTS",
    "RETRY_BACKOFF_MULTIPLIER",
    "RETRY_INITIAL_DELAY",
    # Response Limits
    "VALIDATOR_RESPONSE_WORD_LIMIT",
    # Agent Profile Types (generic)
    "LLMProfile",
    "ThresholdProfile",
    "AgentProfile",
    "get_agent_profile",
    "get_llm_profile",
    "get_thresholds",
    "get_latency_budget",
    # Config Registry
    "ConfigRegistry",
    "ConfigKeys",
    "get_config_registry",
    "set_config_registry",
    "reset_config_registry",
]
