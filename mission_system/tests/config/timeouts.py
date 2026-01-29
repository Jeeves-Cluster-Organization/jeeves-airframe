"""Test Timeout Configuration.

Per Engineering Improvement Plan v4.2 - Phase C1: Test Config Centralization.

This module centralizes all timeout and delay values used in tests.
Instead of hardcoding values like `timeout=30` or `asyncio.sleep(0.5)` throughout
test files, import from here.

Usage:
    from mission_system.tests.config.timeouts import TEST_SERVER_STARTUP_TIMEOUT, TEST_ASYNC_SLEEP_SHORT

Constitutional Compliance:
- Amendment I: Repo Hygiene - Single source of truth for timeouts
- P6: Testable - Consistent timing across all tests
"""

# =============================================================================
# Server/Service Startup Timeouts (seconds)
# =============================================================================

# Time to wait for API server to start
TEST_SERVER_STARTUP_TIMEOUT = 30

# Time to wait for PostgreSQL container to be ready
TEST_POSTGRES_STARTUP_TIMEOUT = 30

# Time to wait for llama-server to respond
TEST_LLAMASERVER_STARTUP_TIMEOUT = 10


# =============================================================================
# HTTP Request Timeouts (seconds)
# =============================================================================

# General HTTP request timeout
TEST_HTTP_REQUEST_TIMEOUT = 5.0

# Health check endpoint timeout
TEST_HEALTH_CHECK_TIMEOUT = 2.0

# llama-server connectivity check timeout
TEST_LLAMASERVER_CONNECTIVITY_TIMEOUT = 2.0

# LLM generation request timeout (longer for model inference)
# Note: 7B models may need 60-120s for JSON generation with large prompts
TEST_LLM_REQUEST_TIMEOUT = 120.0


# =============================================================================
# Circuit Breaker Timeouts (seconds)
# =============================================================================

# Call timeout for circuit breaker tests
TEST_CIRCUIT_BREAKER_CALL_TIMEOUT = 1.0

# Reset timeout for circuit breaker tests
TEST_CIRCUIT_BREAKER_RESET_TIMEOUT = 2.0


# =============================================================================
# Async Sleep Durations (seconds)
# =============================================================================

# Very short sleep (for tight loops, immediate retries)
TEST_ASYNC_SLEEP_TINY = 0.05

# Short sleep (for quick state transitions)
TEST_ASYNC_SLEEP_SHORT = 0.1

# Medium sleep (for typical async operations)
TEST_ASYNC_SLEEP_MEDIUM = 0.5

# Long sleep (for waiting on slow operations)
TEST_ASYNC_SLEEP_LONG = 1.0

# Extended sleep (for timeout tests)
TEST_ASYNC_SLEEP_EXTENDED = 2.0


# =============================================================================
# Rate Limiter Timeouts
# =============================================================================

# Window duration for rate limiter tests
TEST_RATE_LIMITER_WINDOW = 1.0

# Sleep to exceed rate limit window
TEST_RATE_LIMITER_WAIT = 1.1


# =============================================================================
# WebSocket Timeouts
# =============================================================================

# WebSocket connection timeout
TEST_WEBSOCKET_CONNECT_TIMEOUT = 5.0

# WebSocket idle timeout for tests
TEST_WEBSOCKET_IDLE_TIMEOUT = 1.0


# =============================================================================
# Database Timeouts
# =============================================================================

# Database query timeout
TEST_DB_QUERY_TIMEOUT = 10.0

# Database connection timeout
TEST_DB_CONNECT_TIMEOUT = 5.0


# =============================================================================
# Test Execution Limits
# =============================================================================

# Maximum test execution time (for slow test detection)
TEST_MAX_EXECUTION_TIME = 300  # 5 minutes

# Retry delay for flaky operations
TEST_RETRY_DELAY = 0.5

# Maximum retry attempts
TEST_MAX_RETRIES = 3
