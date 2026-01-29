"""Shared pytest fixtures for all tests.

Per Engineering Improvement Plan v4.0 - Testing Architecture Overhaul.

LLAMASERVER_ALWAYS Policy:
- ALL tests use real llama-server (no mock provider default)
- Tests validate real semantic behavior
- MockProvider only as CI fallback

Test Configuration:
- Centralized in tests/config/ package
- Fixtures in tests/fixtures/ package
- PostgreSQL-only testing

Constitutional Compliance:
- Constitution R7: register_capability() called at test setup for integration tests
- App-specific agent fixtures are in the app layer's own test fixtures
- See: jeeves-capability-code-analyser/tests/fixtures/agents.py

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

# Project root setup
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# App layer setup (for mission system code that imports from app layer)
# NOTE: This is needed because mission system code imports from app layer
# (e.g., prompts.registry). Ideally this dependency should be inverted.
# IMPORTANT: Append (not insert) so mission_system paths take precedence
app_dir = project_root.parent / "jeeves-capability-code-analyser"
if app_dir.exists() and str(app_dir) not in sys.path:
    sys.path.append(str(app_dir))

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
# Capability Registration Fixture (Constitution R7)
# ============================================================

@pytest.fixture(autouse=True, scope="session")
def setup_capability_registration():
    """Register capability resources per Constitution R7.

    This ensures the CapabilityResourceRegistry is populated with
    capability resources for tests that exercise the full stack.
    """
    from jeeves_infra.protocols import reset_capability_resource_registry

    # Start with clean registry
    reset_capability_resource_registry()

    # Register capability (Constitution R7)
    try:
        from jeeves_capability_code_analyser import register_capability
        register_capability()
    except ImportError:
        # Capability not available, skip registration
        # Unit tests that don't need capability will pass
        pass

    yield

    # Clean up for test isolation
    reset_capability_resource_registry()


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
    postgres_container,
    pg_test_db,
    create_test_prerequisites,
    create_session_only,
)

# LLM fixtures
from mission_system.tests.fixtures.llm import (
    llm_provider,
    schema_path,
)

# Service fixtures
from mission_system.tests.fixtures.services import (
    session_service,
    tool_health_service,
    tool_registry,
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
    "postgres_container",
    "pg_test_db",
    "create_test_prerequisites",
    "create_session_only",
    # LLM
    "llm_provider",
    "schema_path",
    # Services
    "session_service",
    "tool_health_service",
    "tool_registry",
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
