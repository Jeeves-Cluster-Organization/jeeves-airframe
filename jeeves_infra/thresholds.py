"""Infrastructure operational thresholds.

Agent-specific thresholds (PLAN_*, CRITIC_*, META_VALIDATOR_*, SESSION_*)
have been moved to capability config. This module retains only infrastructure
concerns used by ToolHealthService and generic middleware.

Constitutional Alignment:
- P6: Testable/Observable - centralized config enables consistent testing
"""

# =============================================================================
# L7 GOVERNANCE / TOOL HEALTH THRESHOLDS
# =============================================================================

# Error rate that triggers 'degraded' status (15%)
TOOL_DEGRADED_ERROR_RATE = 0.15

# Error rate that triggers quarantine (35%)
TOOL_QUARANTINE_ERROR_RATE = 0.35

# Minimum invocations before stats are meaningful
TOOL_MIN_INVOCATIONS_FOR_STATS = 20

# Quarantine duration (hours)
TOOL_QUARANTINE_DURATION_HOURS = 24


# =============================================================================
# OPERATIONAL LIMITS
# =============================================================================

# Maximum retry attempts for transient failures
MAX_RETRY_ATTEMPTS = 3

# Default timeout for pending confirmations (seconds)
CONFIRMATION_TIMEOUT_SECONDS = 300

# Total request budget (sum of stage budgets x iteration allowance)
MAX_REQUEST_LATENCY_MS = 300000  # 5 minutes total
