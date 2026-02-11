"""Test Environment Configuration.

Provides test configuration with sensible defaults. Tests declare their
infrastructure requirements via pytest markers and fixtures handle
availability checking at runtime.

Configuration:
- CI environment detection (explicit env vars only)
- Database backend configuration
- Feature test flags
- Performance settings
- Logging configuration

Constitutional Compliance:
- P6: Testable - tests declare requirements, fixtures check availability
- P2: Reliability - fail at test runtime, not import time
"""

import os
from typing import Literal

# ============================================================
# CI Environment Detection (explicit env vars only)
# ============================================================

IS_CI = os.getenv("CI", "false").lower() == "true"
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "false").lower() == "true"


def is_running_in_ci() -> bool:
    """Check if tests are running in CI environment."""
    return IS_CI or IS_GITHUB_ACTIONS


# ============================================================
# Database Backend Configuration
# ============================================================

# Database backend
TEST_DATABASE_BACKEND: str = os.getenv("TEST_DATABASE_BACKEND", "sqlite")

# Database connection with sensible defaults
# Override via env vars: DB_HOST, DB_PORT, etc.
TEST_DB_HOST = os.getenv("DB_HOST") or os.getenv("TEST_DB_HOST", "localhost")
TEST_DB_PORT = int(os.getenv("DB_PORT") or os.getenv("TEST_DB_PORT", "5432"))
TEST_DB_USER = os.getenv("DB_USER") or os.getenv("TEST_DB_USER", "assistant")
TEST_DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("TEST_DB_PASSWORD", "dev_password_change_in_production")
TEST_DB_NAME = os.getenv("DB_NAME") or os.getenv("TEST_DB_NAME", "assistant")


def get_test_database_url(database: str | None = None) -> str:
    """Generate database connection URL for tests.

    Args:
        database: Database name (default: TEST_DB_NAME)

    Returns:
        Database connection URL
    """
    db = database or TEST_DB_NAME
    return (
        f"postgresql://{TEST_DB_USER}:{TEST_DB_PASSWORD}"
        f"@{TEST_DB_HOST}:{TEST_DB_PORT}/{db}"
    )


# ============================================================
# Feature Test Flags
# ============================================================

# Memory infrastructure tests (default enabled)
MEMORY_TESTS_ENABLED = os.getenv("MEMORY_TESTS_ENABLED", "1") == "1"

# Production tests requiring API keys and external services
PROD_TESTS_ENABLED = os.getenv("PROD_TESTS_ENABLED", "0") == "1"

# Constitution/Memory Contract validation tests
CONTRACT_TESTS_ENABLED = os.getenv("CONTRACT_TESTS_ENABLED", "1") == "1"


# ============================================================
# Test Performance Configuration
# ============================================================

# Maximum test execution time (seconds)
TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "300"))  # 5 minutes default

# Database container startup timeout (seconds)
DB_CONTAINER_TIMEOUT = int(os.getenv("DB_CONTAINER_TIMEOUT", "30"))

# Test isolation level
# - "function": Fresh database per test (slower, better isolation)
# - "session": Shared database for all tests (faster, requires manual cleanup)
TEST_DB_SCOPE: Literal["function", "session"] = os.getenv("TEST_DB_SCOPE", "function")  # type: ignore


def should_skip_slow_tests() -> bool:
    """Determine if slow tests should be skipped (typically in CI)."""
    return is_running_in_ci()


# ============================================================
# Logging Configuration for Tests
# ============================================================

# Set to "DEBUG" to see detailed logs during tests
TEST_LOG_LEVEL = os.getenv("TEST_LOG_LEVEL", "WARNING")

# Silence noisy library loggers
SILENCE_LIBRARY_LOGS = os.getenv("SILENCE_LIBRARY_LOGS", "1") == "1"
