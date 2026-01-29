"""Pytest configuration for jeeves_infra tests.

This conftest.py provides fixtures and configuration for the jeeves_infra
test suite. Tests may use database containers but should mock
core engine protocols when testing in isolation.

Key Principles:
- Use testcontainers for PostgreSQL
- Mock jeeves_core_engine protocols when needed
- Each test gets a fresh database
"""

import sys
from pathlib import Path

import pytest

# Add paths for imports
# 1. jeeves-infra root (for jeeves_infra package)
jeeves_infra_root = Path(__file__).parent.parent
if str(jeeves_infra_root) not in sys.path:
    sys.path.insert(0, str(jeeves_infra_root))

# 2. tests directory (for tests.fixtures)
tests_root = Path(__file__).parent
if str(tests_root) not in sys.path:
    sys.path.insert(0, str(tests_root))


# =============================================================================
# IMPORT FIXTURES FROM FIXTURES PACKAGE
# =============================================================================
# Note: Some fixtures have complex dependencies (mission_system, shared).
# Import failures are handled gracefully to allow unit tests to run.

try:
    from fixtures.database import (
        postgres_container,
        pg_test_db,
        create_test_prerequisites,
        create_session_only,
    )
except ImportError:
    # Database fixtures have external dependencies
    pass

try:
    from fixtures.llm import (
        mock_llm_provider,
        mock_llm_provider_factory,
        MockLLMProvider,
    )
except ImportError:
    # LLM fixtures have external dependencies
    pass

try:
    from fixtures.mocks.core_mocks import (
        MockEnvelope,
        mock_envelope_factory,
        mock_envelope,
    )
except ImportError:
    # Core mocks may have external dependencies
    pass

# Kernel mocks are self-contained - no external dependencies
try:
    from fixtures.mocks.kernel_mocks import (
        mock_grpc_channel,
        mock_kernel_stub,
        mock_engine_stub,
        mock_kernel_client,
    )
except ImportError:
    pass


# =============================================================================
# PYTEST MARKERS
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (may use mocks)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring database"
    )
    config.addinivalue_line(
        "markers", "slow: Slow-running tests"
    )


# Note: anyio_backend fixture is centralized in root conftest.py
