"""LLM Fixtures for Tests.

Per Engineering Improvement Plan v4.0 - Phase T2: Fixture Reorganization.

CRITICAL: LLAMASERVER_ALWAYS Policy
- No mock provider by default
- llama-server containers must be available
- Tests validate real semantic behavior

This module provides:
- llm_provider fixture (ALWAYS real llama-server)
- schema_path fixture

Constitutional Compliance:
- P1: Natural Language Understanding - real LLM validates semantic behavior
- P6: Testable - tests catch real failures, not mock patterns

Constitutional Import Boundary Note:
- Mission system layer IS the wiring layer between app and jeeves_infra
- Direct jeeves_infra imports are acceptable here for LLM factory access
- App layer tests must use mission_system.adapters instead
"""

from pathlib import Path

import pytest

from mission_system.tests.config.llm_config import get_llm_provider_type


@pytest.fixture
def schema_path():
    """Get absolute path to schema file."""
    return str(Path(__file__).parent.parent.parent / "database" / "schema.sql")


@pytest.fixture
def llm_provider():
    """LLM provider - ALWAYS real llama-server.

    Per Testing Architecture v4.0 LLAMASERVER_ALWAYS Policy:
    - No mock provider by default
    - llama-server containers must be available
    - Tests validate real semantic behavior

    If llama-server is unavailable, the test will fail with a clear message.
    This is intentional - we want tests to fail fast if infrastructure
    is not set up correctly.

    Usage:
        def test_something(llm_provider):
            response = await llm_provider.generate(...)
            assert response is not None
    """
    from jeeves_infra.settings import get_settings
    from jeeves_infra.llm.factory import create_llm_provider

    provider_type = get_llm_provider_type()
    provider = create_llm_provider(provider_type, get_settings())

    if provider is None:
        pytest.fail(
            "LLM provider not available. "
            "Per LLAMASERVER_ALWAYS policy, ensure llama-server is running:\n"
            "  docker-compose up -d llama-server\n"
            "See docs/architecture/ENGINEERING_IMPROVEMENT_PLAN.md"
        )

    return provider
