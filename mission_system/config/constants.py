"""
Configuration constants for Jeeves Mission System.

Centralizes operational constants. Product identity is capability-specific
and should be queried from CapabilityResourceRegistry.

NOTE: LLM parameters and agent thresholds have been moved to:
- mission_system/config/agent_profiles.py (AgentProfile, LLMProfile, ThresholdProfile)
- jeeves_infra/thresholds.py (operational thresholds)
"""

# Import operational thresholds from canonical source (jeeves_infra Constitution)
from jeeves_infra.thresholds import (
    MAX_RETRY_ATTEMPTS,
    FUZZY_MATCH_MIN_SCORE,
)

# Re-export for backwards compatibility
FUZZY_MATCH_THRESHOLD = FUZZY_MATCH_MIN_SCORE  # Alias for compatibility

# ==============================================================================
# PLATFORM IDENTITY (generic - capabilities provide specific identity)
# ==============================================================================

PLATFORM_NAME = "Jeeves"
PLATFORM_VERSION = "4.0.0"
PLATFORM_DESCRIPTION = "AI-powered agent platform with centralized architecture"

# Agent architecture description
AGENT_ARCHITECTURE = "7-agent pipeline (Agent)"
AGENT_COUNT = 7


# ==============================================================================
# FUZZY MATCHING
# ==============================================================================

# FUZZY_MATCH_THRESHOLD imported from thresholds.py (re-exported above as alias)
FUZZY_MATCH_CONFIDENCE_THRESHOLD = 0.7
FUZZY_MATCH_SUBSTRING_WEIGHT = 1.0
FUZZY_MATCH_WORD_OVERLAP_WEIGHT = 0.9
FUZZY_MATCH_CHAR_SIMILARITY_WEIGHT = 0.7
FUZZY_MATCH_SECONDARY_WEIGHT = 0.8


# ==============================================================================
# TASK MANAGEMENT
# ==============================================================================

TASK_PRIORITY_HIGH = 0
TASK_PRIORITY_MEDIUM = 1
TASK_PRIORITY_LOW = 2
TASK_DEFAULT_PRIORITY = TASK_PRIORITY_MEDIUM
TASK_DEFAULT_STATUS = "pending"
TASK_CANDIDATE_LIMIT = 5
TASK_QUERY_LIMIT = 100


# ==============================================================================
# JSON PARSING
# ==============================================================================

ERROR_SNIPPET_MAX_LENGTH = 200
JSON_CLEANUP_PASSES = 3


# ==============================================================================
# DATABASE QUERY LIMITS
# ==============================================================================

DB_DEFAULT_LIMIT = 100
DB_RECENT_TASKS_LIMIT = 5
DB_CONVERSATION_HISTORY_LIMIT = 10


# ==============================================================================
# TIMEOUT VALUES (seconds)
# ==============================================================================

LLM_REQUEST_TIMEOUT = 30
DB_QUERY_TIMEOUT = 10
TOOL_EXECUTION_TIMEOUT = 60


# ==============================================================================
# LOGGING AND MONITORING
# ==============================================================================

LOG_MESSAGE_MAX_LENGTH = 500
METRICS_RETENTION_DAYS = 30


# ==============================================================================
# ERROR HANDLING
# ==============================================================================

# MAX_RETRY_ATTEMPTS imported from jeeves_infra/thresholds.py (canonical source)
RETRY_BACKOFF_MULTIPLIER = 2.0
RETRY_INITIAL_DELAY = 1.0


# ==============================================================================
# RESPONSE LIMITS
# ==============================================================================

VALIDATOR_RESPONSE_WORD_LIMIT = 150
