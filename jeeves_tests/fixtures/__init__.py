"""Test Fixtures Package.

Centralized Architecture (v4.0):
- Uses Envelope (not CoreEnvelope)
- Pre-populated envelope fixtures for each pipeline stage
- No concrete agent fixtures (agents are config-driven)

This package provides centralized, well-documented fixtures:
- database.py: PostgreSQL fixtures and FK helpers
- llm.py: LLM provider fixture (LLAMASERVER_ALWAYS policy)
- services.py: Memory service fixtures
- agents.py: Envelope fixtures for pipeline testing

All fixtures follow the LLAMASERVER_ALWAYS policy - no mock LLM by default.
"""

from mission_system.tests.fixtures.database import (
    postgres_container,
    pg_test_db,
    create_test_prerequisites,
    create_session_only,
    ComposePostgresContainer,
)

from mission_system.tests.fixtures.llm import (
    llm_provider,
    schema_path,
)

from mission_system.tests.fixtures.services import (
    session_service,
    tool_health_service,
    tool_registry,
)

# Mock implementations for isolated testing
from mission_system.tests.fixtures.mocks import (
    MockLLMAdapter,
    MockDatabaseClient,
    MockMemoryService,
    MockEventBus,
)

# Envelope and agent fixtures (v4.0 centralized architecture)
from mission_system.tests.fixtures.agents import (
    # Factory fixtures
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
    # Special state fixtures
    envelope_with_clarification,
    envelope_with_loop_back,
)

__all__ = [
    # Database
    "postgres_container",
    "pg_test_db",
    "create_test_prerequisites",
    "create_session_only",
    "ComposePostgresContainer",
    # LLM
    "llm_provider",
    "schema_path",
    # Services
    "session_service",
    "tool_health_service",
    "tool_registry",
    # Mocks for isolated testing
    "MockLLMAdapter",
    "MockDatabaseClient",
    "MockMemoryService",
    "MockEventBus",
    # Envelope fixtures (v4.0)
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
    "envelope_with_clarification",
    "envelope_with_loop_back",
]
