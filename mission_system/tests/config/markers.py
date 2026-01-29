"""Pytest Marker Configuration.

Per Engineering Improvement Plan v4.3 - Unified Test Infrastructure.

This module provides:
- Marker registration for pytest
- Skip logic based on environment and service availability
- E2E test auto-skip when real LLM unavailable
- Service-aware test execution

Constitutional Compliance:
- M4: Observability - all test categories observable via markers
- P6: Testable - clear test categorization and skip logic
- P2: Reliability - fail loudly when services unavailable

Marker Reference:
- @pytest.mark.e2e - End-to-end tests requiring real LLM
- @pytest.mark.requires_llamaserver - Tests requiring llama-server
- @pytest.mark.requires_azure - Tests requiring Azure OpenAI SDK
- @pytest.mark.requires_services - Tests requiring full Docker stack
- @pytest.mark.requires_postgres - Tests requiring PostgreSQL only
- @pytest.mark.requires_full_app - Tests using TestClient with lifespan
- @pytest.mark.requires_llm_quality - Tests requiring capable LLM (7B+) for nuanced NLP
- @pytest.mark.websocket - WebSocket tests (skip if services unavailable)
- @pytest.mark.slow - Slow-running tests
- @pytest.mark.prod - Production tests (requires PROD_TESTS_ENABLED=1)
- @pytest.mark.uses_llm - Tests that call LLM
"""

import os
import pytest

from mission_system.tests.config.environment import (
    IS_CI,
    PROD_TESTS_ENABLED,
)
from mission_system.tests.config.llm_config import (
    AZURE_AVAILABLE,
    is_llamaserver_available,
    get_llm_provider_type,
)
from mission_system.tests.config.services import (
    is_postgres_available,
    is_llama_server_available,
    are_all_services_available,
    get_cached_service_status,
    clear_service_cache,
)


def is_capable_llm_model() -> bool:
    """Check if the configured LLM model is capable enough for nuanced NLP tasks.

    Small models (3B and under) struggle with:
    - Distinguishing simple "no" vs "yes" in context
    - Understanding synonyms like "sure", "abort", "proceed"
    - Extracting parameters from complex requests
    - Following JSON output format reliably

    This function returns True if the model is likely capable (7B+).
    Returns False for 3B and smaller models.

    Model capability is determined by model name patterns.
    """
    model_name = os.environ.get("DEFAULT_MODEL", "").lower()

    # Small model patterns (3B and under)
    small_model_patterns = [
        "3b",        # Llama-3.2-3B, phi-3B, etc.
        "2b",        # Gemma-2B, etc.
        "1b",        # TinyLlama-1.1B, etc.
        "0.5b",      # Qwen-0.5B, etc.
        "1.5b",      # Qwen-1.5B, etc.
        "tiny",      # TinyLlama variants
        "mini",      # MiniCPM, etc.
    ]

    for pattern in small_model_patterns:
        if pattern in model_name:
            return False

    # Assume capable if no small model pattern found
    # (7B, 8B, 13B, 70B models pass through)
    return True


def configure_markers(config) -> None:
    """Register custom markers for centralized test management.

    Called from pytest_configure hook.

    Constitutional M4 Compliance: All test categories observable.
    """
    # E2E and LLM markers
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests requiring real LLM"
    )
    config.addinivalue_line(
        "markers", "requires_llamaserver: Tests requiring llama-server (real LLM testing)"
    )
    config.addinivalue_line(
        "markers", "requires_azure: Tests requiring Azure OpenAI SDK"
    )
    config.addinivalue_line(
        "markers", "uses_llm: Tests that use LLM (requires real llama-server)"
    )
    config.addinivalue_line(
        "markers", "requires_llm_quality: Tests requiring capable LLM (7B+) for nuanced NLP tasks"
    )

    # Service/Infrastructure markers
    config.addinivalue_line(
        "markers", "requires_services: Tests requiring full Docker stack (postgres + llama-server)"
    )
    config.addinivalue_line(
        "markers", "requires_postgres: Tests requiring PostgreSQL database"
    )
    config.addinivalue_line(
        "markers", "requires_full_app: Tests using TestClient with full app lifespan"
    )
    config.addinivalue_line(
        "markers", "websocket: WebSocket tests (requires services to be available)"
    )
    config.addinivalue_line(
        "markers", "slow: Slow-running tests"
    )

    # V2 Memory markers
    config.addinivalue_line(
        "markers", "v2_memory: V2 memory infrastructure tests"
    )
    config.addinivalue_line(
        "markers", "v2_open_loops: V2 open loops specific tests"
    )

    # Production markers
    config.addinivalue_line(
        "markers", "prod: Production tests (requires API keys, set PROD_TESTS_ENABLED=1)"
    )

    # Contract validation markers
    config.addinivalue_line(
        "markers", "contract: Constitution/Memory Contract validation tests"
    )

    # Heavy dependency markers
    config.addinivalue_line(
        "markers", "heavy: Tests with heavy dependencies (ML models, large downloads)"
    )
    config.addinivalue_line(
        "markers", "requires_ml: Tests requiring ML models (sentence-transformers, etc.)"
    )
    config.addinivalue_line(
        "markers", "requires_docker: Tests requiring Docker/testcontainers"
    )
    config.addinivalue_line(
        "markers", "requires_openai: Tests requiring OpenAI package and API key"
    )
    config.addinivalue_line(
        "markers", "requires_anthropic: Tests requiring Anthropic package and API key"
    )


def apply_skip_markers(config, items) -> None:
    """Apply skip markers based on environment and service availability.

    Called from pytest_collection_modifyitems hook.

    Centralized skip logic per Constitution M4.
    All test skip decisions are made here - NO hardcoded @pytest.mark.skip decorators.

    Service checks are cached for performance.
    """
    # Clear cache at start of collection
    clear_service_cache()

    # Get cached service status (expensive checks done once)
    service_status = get_cached_service_status()
    postgres_available = service_status["postgres"]
    llama_available = service_status["llama_server"]
    all_services = service_status["all_services"]

    # Skip reasons - descriptive messages for each scenario
    skip_postgres_unavailable = pytest.mark.skip(
        reason="PostgreSQL not available - run: docker compose up -d postgres"
    )
    skip_llamaserver_unavailable = pytest.mark.skip(
        reason="llama-server not available - run: docker compose up -d llama-server"
    )
    skip_services_unavailable = pytest.mark.skip(
        reason="Docker services not available - run: docker compose up -d"
    )
    skip_full_app = pytest.mark.skip(
        reason="Requires full app startup with services - run: docker compose up -d"
    )
    skip_azure = pytest.mark.skip(
        reason="Azure OpenAI SDK not installed"
    )
    skip_prod = pytest.mark.skip(
        reason="Production tests disabled (set PROD_TESTS_ENABLED=1 to enable)"
    )
    skip_websocket = pytest.mark.skip(
        reason="WebSocket tests require services - run: docker compose up -d"
    )
    skip_llm_quality = pytest.mark.skip(
        reason="Test requires capable LLM (7B+) - current model is too small for nuanced NLP tasks"
    )

    # Check LLM model capability (expensive check, done once)
    llm_capable = is_capable_llm_model()

    for item in items:
        # Skip @pytest.mark.requires_postgres if PostgreSQL not available
        if item.get_closest_marker("requires_postgres"):
            if not postgres_available:
                item.add_marker(skip_postgres_unavailable)

        # Skip @pytest.mark.requires_llamaserver if llama-server not available
        if item.get_closest_marker("requires_llamaserver"):
            if not llama_available:
                item.add_marker(skip_llamaserver_unavailable)

        # Skip @pytest.mark.requires_services if full stack not available
        if item.get_closest_marker("requires_services"):
            if not all_services:
                item.add_marker(skip_services_unavailable)

        # Skip @pytest.mark.requires_full_app if services not available
        # These tests use TestClient which triggers full app lifespan
        if item.get_closest_marker("requires_full_app"):
            if not all_services:
                item.add_marker(skip_full_app)

        # Skip @pytest.mark.websocket if services not available
        if item.get_closest_marker("websocket"):
            if not all_services:
                item.add_marker(skip_websocket)

        # Skip @pytest.mark.requires_azure if SDK not installed
        if item.get_closest_marker("requires_azure") and not AZURE_AVAILABLE:
            item.add_marker(skip_azure)

        # Skip @pytest.mark.requires_llm_quality if model too small
        if item.get_closest_marker("requires_llm_quality"):
            if not llm_capable:
                item.add_marker(skip_llm_quality)

        # Skip @pytest.mark.prod unless explicitly enabled
        if item.get_closest_marker("prod") and not PROD_TESTS_ENABLED:
            item.add_marker(skip_prod)

        # Skip @pytest.mark.uses_llm if no LLM available
        # Per LLAMASERVER_ALWAYS policy: LLM tests require real LLM
        if item.get_closest_marker("uses_llm"):
            if not llama_available:
                item.add_marker(skip_llamaserver_unavailable)


def setup_e2e_skip(item) -> None:
    """Auto-skip E2E tests if real LLM not available.

    Called from pytest_runtest_setup hook.

    Per LLAMASERVER_ALWAYS Policy:
    - E2E tests REQUIRE real LLM
    - No mock fallback for E2E
    - Skip with clear message if llama-server unavailable
    """
    e2e_marker = item.get_closest_marker("e2e")

    if e2e_marker:
        # Check if llama-server is available
        llamaserver_available = is_llamaserver_available()
        provider_type = get_llm_provider_type()

        # E2E tests run only with real LLM
        if provider_type == "mock" or not llamaserver_available:
            pytest.skip(
                "E2E test requires real LLM provider (LLAMASERVER_ALWAYS policy). "
                f"[provider={provider_type}, llamaserver={llamaserver_available}] "
                "Ensure llama-server is running: docker-compose up -d llama-server\n"
                "See docs/architecture/ENGINEERING_IMPROVEMENT_PLAN.md Part A."
            )
