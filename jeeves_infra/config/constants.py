"""
Configuration constants for Jeeves Infrastructure.

Centralizes operational constants. Product identity is capability-specific
and should be queried from CapabilityResourceRegistry (Constitution R4).

NOTE: LLM parameters and agent thresholds have been moved to:
- jeeves_infra/config/agent_profiles.py (AgentProfile, AgentLLMConfig, ThresholdProfile)
- jeeves_infra/thresholds.py (operational thresholds)
"""

# Import operational thresholds from canonical source (Constitution)
from jeeves_infra.thresholds import (
    MAX_RETRY_ATTEMPTS,
)

# ==============================================================================
# PLATFORM IDENTITY (generic - capabilities provide specific identity)
# ==============================================================================

PLATFORM_NAME = "Jeeves"
PLATFORM_VERSION = "4.0.0"
PLATFORM_DESCRIPTION = "AI-powered agent platform with centralized architecture"


# ==============================================================================
# FUZZY MATCHING
# ==============================================================================

FUZZY_MATCH_CONFIDENCE_THRESHOLD = 0.7
FUZZY_MATCH_SUBSTRING_WEIGHT = 1.0
FUZZY_MATCH_WORD_OVERLAP_WEIGHT = 0.9
FUZZY_MATCH_CHAR_SIMILARITY_WEIGHT = 0.7
FUZZY_MATCH_SECONDARY_WEIGHT = 0.8



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
