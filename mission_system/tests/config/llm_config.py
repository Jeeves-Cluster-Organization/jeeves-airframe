"""LLM Configuration for Tests - ALWAYS REAL.

Per Engineering Improvement Plan v4.0 - Testing Architecture Overhaul.

CRITICAL POLICY: LLAMASERVER_ALWAYS
- No mock provider by default
- llama-server containers must be available for development
- Tests validate real semantic behavior
- MockProvider only allowed as CI fallback (when llama-server unavailable)

The MockProvider is a 430-line pattern-matching monster that:
- Returns deterministic responses based on prompt patterns
- Provides false confidence (tests pass but don't validate real behavior)
- Requires constant updates as prompts change
- Hides semantic understanding failures

This configuration enforces real LLM testing to catch actual issues.

Constitutional Compliance:
- P1: Natural Language Understanding - real LLM validates semantic behavior
- P6: Testable - tests catch real failures, not mock patterns
"""

import os
from typing import Literal

from mission_system.tests.config.environment import IS_CI

# ============================================================
# CRITICAL: LLAMASERVER_ALWAYS Policy
# ============================================================

# Default to llamaserver, not mock
# Per Testing Architecture v4.0: No mock provider by default
DEFAULT_LLM_PROVIDER: Literal["llamaserver", "mock"] = "llamaserver"

# Mock is ONLY allowed in CI where llama-server may be unavailable
MOCK_ALLOWED_ONLY_IN_CI = True


def get_llm_provider_type() -> Literal["llamaserver", "mock"]:
    """Get LLM provider type for tests.

    Per LLAMASERVER_ALWAYS policy:
    - Default: llamaserver (real LLM)
    - Override: LLM_PROVIDER env var
    - CI fallback: mock only if llama-server unavailable AND in CI

    Returns:
        "llamaserver" for real LLM testing (default)
        "mock" only in CI when llama-server unavailable
    """
    # Explicit override via environment
    env_provider = os.environ.get("LLM_PROVIDER")
    if env_provider:
        if env_provider == "mock":
            # Only allow mock in CI
            if not IS_CI and MOCK_ALLOWED_ONLY_IN_CI:
                import warnings
                warnings.warn(
                    "LLM_PROVIDER=mock is deprecated for local development. "
                    "Use real llama-server. See docs/architecture/ENGINEERING_IMPROVEMENT_PLAN.md",
                    DeprecationWarning,
                    stacklevel=2
                )
            return "mock"
        elif env_provider == "llamaserver":
            return "llamaserver"
        else:
            # Unknown provider, default to llamaserver
            return "llamaserver"

    # Default: real llama-server
    return DEFAULT_LLM_PROVIDER


# ============================================================
# llama-server Connection Configuration
# ============================================================

# These are read dynamically by functions to handle late env var setting
DEFAULT_LLAMASERVER_HOST = "http://localhost:8080"
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "qwen2.5-3b-instruct-q4_k_m")


def _get_llamaserver_host() -> str:
    """Read LLAMASERVER_HOST env var dynamically."""
    return os.getenv("LLAMASERVER_HOST", DEFAULT_LLAMASERVER_HOST)


# Constant for use in conftest.py and other modules
LLAMASERVER_HOST = _get_llamaserver_host()


def is_llamaserver_available() -> bool:
    """Check if llama-server is available for testing.

    Performs actual connectivity check to LLAMASERVER_HOST.
    No environment magic - just checks if the server responds.

    Returns True if llama-server is available, False otherwise.
    """
    return _check_llamaserver_connectivity()


def _check_llamaserver_connectivity() -> bool:
    """Perform live connectivity check to llama-server.

    This is a synchronous check for use in configuration.
    Reads LLAMASERVER_HOST dynamically at call time.
    """
    import urllib.request
    import urllib.error

    # Read host dynamically to use current env value
    host = _get_llamaserver_host()

    try:
        # Quick health check - llama-server /health endpoint
        req = urllib.request.Request(
            f"{host}/health",
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


# ============================================================
# Azure SDK Availability (for Azure OpenAI provider)
# ============================================================

try:
    from openai import AzureOpenAI  # noqa: F401
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False


# ============================================================
# LLM Test Requirements
# ============================================================

# Components that MUST use real LLM in tests
# (Pattern-matching tests provide false confidence)
# Generic agent types - capability-agnostic naming
LLM_DEPENDENT_COMPONENTS = [
    "IntentAgent",          # Intent classification requires LLM
    "PlannerAgent",         # Plan generation requires LLM
    "SynthesizerAgent",     # Synthesis requires LLM
    "CriticAgent",          # Validation requires LLM
    "IntegrationAgent",     # Response building requires LLM
]

# Components that are deterministic (no LLM, mocking OK)
# Generic agent types - capability-agnostic naming
DETERMINISTIC_COMPONENTS = [
    "PerceptionAgent",      # Input normalization, context loading
    "TraverserAgent",       # Tool execution (resilient ops)
    "ExecutorAgent",        # Tool execution
    "ToolRegistry",
    "CircuitBreaker",
    "RateLimiter",
]
