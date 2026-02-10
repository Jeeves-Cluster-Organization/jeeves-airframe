"""Mock implementations for testing jeeves_infra.

Centralized Architecture (v4.0):
- MockEnvelope replaces MockCoreEnvelope
- No MockAgent (agents are config-driven)

This package provides mocks for jeeves_core_engine and jeeves_infra
dependencies, allowing tests to run in isolation.

Usage:
    from tests.fixtures.mocks import MockLLMAdapter, MockDatabaseClient
"""

from .infra_mocks import (
    MockLLMAdapter,
    MockDatabaseClient,
    MockMemoryService,
    MockEventBus,
)

__all__ = [
    # Infrastructure mocks
    "MockLLMAdapter",
    "MockDatabaseClient",
    "MockMemoryService",
    "MockEventBus",
]
