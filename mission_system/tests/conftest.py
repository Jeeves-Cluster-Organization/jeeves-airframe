"""Shared pytest fixtures for all tests.

Per Engineering Improvement Plan v4.0 - Testing Architecture Overhaul.

LLAMASERVER_ALWAYS Policy:
- ALL tests use real llama-server (no mock provider default)
- Tests validate real semantic behavior
- MockProvider only as CI fallback

Test Configuration:
- Centralized in tests/config/ package
- Fixtures in tests/fixtures/ package
- In-memory SQLite for fast, isolated tests

Constitutional Compliance:
- Airframe tests are self-contained (no capability imports)
- Capability registration happens in the capability layer's own conftest

Usage:
    @pytest.mark.e2e           # Full production flow
    @pytest.mark.requires_llamaserver    # Skip if llama-server unavailable
    @pytest.mark.uses_llm      # Tests calling LLM (requires real llama-server)
    @pytest.mark.v2_memory     # V2 memory infrastructure test
    @pytest.mark.contract      # Constitution validation test
"""

import os
import sys
from pathlib import Path

import pytest

# Project root setup (jeeves-airframe/ — 3 levels up from mission_system/tests/conftest.py)
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import config for environment setup
from mission_system.tests.config.llm_config import LLAMASERVER_HOST, DEFAULT_MODEL
from mission_system.tests.config.markers import (
    configure_markers,
    apply_skip_markers,
    setup_e2e_skip,
)

# Set environment defaults
os.environ.setdefault("LLAMASERVER_HOST", LLAMASERVER_HOST)
os.environ.setdefault("DEFAULT_MODEL", DEFAULT_MODEL)
os.environ["DISABLE_TEMPERATURE"] = "false"


# ============================================================
# Pytest Configuration Hooks
# ============================================================

def pytest_configure(config):
    """Register custom markers."""
    configure_markers(config)


def pytest_collection_modifyitems(config, items):
    """Apply skip markers based on environment."""
    apply_skip_markers(config, items)


def pytest_runtest_setup(item):
    """Auto-skip E2E tests if real LLM unavailable."""
    setup_e2e_skip(item)


# ============================================================
# Import Fixtures from tests/fixtures/ package
# ============================================================

# Database fixtures
from mission_system.tests.fixtures.database import (
    test_db,
    create_test_prerequisites,
    create_session_only,
)

# LLM fixtures
from mission_system.tests.fixtures.llm import (
    llm_provider,
    schema_path,
)

# Envelope and mock fixtures (mission system level - no app imports)
from mission_system.tests.fixtures.agents import (
    # Envelope fixtures
    envelope_factory,
    sample_envelope,
    # Mock fixtures
    mock_db,
    mock_tool_executor,
    mock_llm_provider,
    # Pre-populated envelope fixtures
    envelope_with_perception,
    envelope_with_intent,
    envelope_with_plan,
    envelope_with_execution,
    envelope_with_synthesizer,
    envelope_with_critic,
)


# ============================================================
# Async Backend
# ============================================================

@pytest.fixture
def anyio_backend():
    """Use asyncio as the async backend."""
    return "asyncio"


# Re-export for pytest discovery
__all__ = [
    # Database
    "test_db",
    "create_test_prerequisites",
    "create_session_only",
    # LLM
    "llm_provider",
    "schema_path",
    # Envelope fixtures
    "envelope_factory",
    "sample_envelope",
    "mock_db",
    "mock_tool_executor",
    "mock_llm_provider",
    "envelope_with_perception",
    "envelope_with_intent",
    "envelope_with_plan",
    "envelope_with_execution",
    "envelope_with_synthesizer",
    "envelope_with_critic",
]
