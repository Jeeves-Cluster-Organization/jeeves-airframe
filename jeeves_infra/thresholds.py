"""
Centralized confidence and operational thresholds.

This module consolidates threshold constants used across the codebase,
enabling consistent tuning and easier maintenance.

Constitutional Alignment:
- P6: Testable/Observable - centralized config enables consistent testing
- M4: Observability - thresholds are documented and traceable
"""

# =============================================================================
# CONFIRMATION SYSTEM THRESHOLDS
# =============================================================================

# Minimum confidence required to route a message to confirmation handler
# Used in: services/confirmation_coordinator.py (is_confirmation_response)
CONFIRMATION_DETECTION_CONFIDENCE = 0.7

# Minimum confidence for interpreting confirmation responses
# Used in: confirmation_interpreter.py
CONFIRMATION_INTERPRETATION_CONFIDENCE = 0.7

# Default timeout for pending confirmations (seconds)
# Used in: orchestrator.py (confirmation_timeout_seconds)
CONFIRMATION_TIMEOUT_SECONDS = 300


# =============================================================================
# PLANNING & EXECUTION THRESHOLDS
# =============================================================================

# Below this confidence, planner should request clarification
# Used in: planner.py
# Tuned for Qwen 7B local LLM (smaller models produce lower confidence scores)
PLAN_MIN_CONFIDENCE = 0.70

# Above this confidence, skip optional validation steps
# Used in: planner.py, orchestrator.py
# Tuned for Qwen 7B local LLM
PLAN_HIGH_CONFIDENCE = 0.85

# Maximum retry attempts for transient failures
# Used in: orchestrator.py (_with_retries)
MAX_RETRY_ATTEMPTS = 3


# =============================================================================
# CRITIC & VALIDATION THRESHOLDS
# =============================================================================

# Threshold for critic to approve without changes
# Used in: critic.py (accept action, successful mock review)
# Tuned for Qwen 7B local LLM
CRITIC_APPROVAL_THRESHOLD = 0.80

# High confidence for retry decisions (hallucinated success, tool mismatch)
# Used in: critic.py (retry_validator action)
# Tuned for Qwen 7B local LLM
CRITIC_HIGH_CONFIDENCE = 0.85

# Medium confidence for retry decisions (task search too specific)
# Used in: critic.py (retry_planner action)
CRITIC_MEDIUM_CONFIDENCE = 0.75

# Low confidence for clarification decisions
# Used in: critic.py (clarify action, empty search acknowledgment)
CRITIC_LOW_CONFIDENCE = 0.6

# Default/fallback confidence when critic encounters errors
# Used in: critic.py (error fallback, LLM parse failure)
CRITIC_DEFAULT_CONFIDENCE = 0.5

# Threshold for meta-validator to pass response
# Used in: meta_validator.py
META_VALIDATOR_PASS_THRESHOLD = 0.9

# Meta-validator high confidence (approved by LLM)
# Used in: meta_validator.py
META_VALIDATOR_APPROVED_CONFIDENCE = 0.95

# Meta-validator low confidence (rejected by LLM)
# Used in: meta_validator.py
META_VALIDATOR_REJECTED_CONFIDENCE = 0.35

# User-confirmed action confidence
# Used in: orchestrator.py
USER_CONFIRMED_CONFIDENCE = 0.9


# =============================================================================
# SEARCH & MATCHING THRESHOLDS
# =============================================================================

# Minimum fuzzy match score to consider a candidate
# Used in: task_tools.py, fuzzy_matcher.py
FUZZY_MATCH_MIN_SCORE = 0.5

# Minimum semantic similarity score for search results
# Used in: task_tools.py, embedding_service.py
SEMANTIC_SEARCH_MIN_SIMILARITY = 0.5

# Weight for fuzzy vs semantic in hybrid search
# Used in: task_tools.py (search_tasks_hybrid)
HYBRID_SEARCH_FUZZY_WEIGHT = 0.4
HYBRID_SEARCH_SEMANTIC_WEIGHT = 0.6


# =============================================================================
# L7 GOVERNANCE / TOOL HEALTH THRESHOLDS
# =============================================================================

# Error rate that triggers 'degraded' status (15%)
# Used in: tool_health_service.py
TOOL_DEGRADED_ERROR_RATE = 0.15

# Error rate that triggers quarantine (35%)
# Used in: tool_health_service.py
TOOL_QUARANTINE_ERROR_RATE = 0.35

# Minimum invocations before stats are meaningful
# Used in: tool_health_service.py
TOOL_MIN_INVOCATIONS_FOR_STATS = 20

# Quarantine duration (hours)
# Used in: tool_health_service.py
TOOL_QUARANTINE_DURATION_HOURS = 24


# =============================================================================
# WORKING MEMORY THRESHOLDS (L4)
# =============================================================================

# Message count that triggers session summarization
# Used in: session_state_service.py
SESSION_SUMMARIZATION_TURN_THRESHOLD = 8

# Token budget that triggers immediate summarization
# Used in: session_state_service.py
SESSION_TOKEN_BUDGET_THRESHOLD = 6000

# Idle timeout before queuing summarization (minutes)
# Used in: session_state_service.py
SESSION_IDLE_TIMEOUT_MINUTES = 30

# Days before an open loop is considered stale
# Used in: open_loop_service.py
OPEN_LOOP_STALE_DAYS = 7


# =============================================================================
# LATENCY BUDGETS (per agent stage)
# =============================================================================
# NOTE: Per-agent latency budgets are owned by capabilities.
# See: jeeves-capability-*/config/llm_config.py for capability-specific AGENT_PROFILES

# Total request budget (sum of stage budgets × iteration allowance)
MAX_REQUEST_LATENCY_MS = 300000  # 5 minutes total
