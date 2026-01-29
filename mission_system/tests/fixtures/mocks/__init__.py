"""Mock implementations for testing mission_system.

Centralized Architecture (v4.0):
- MockEnvelope replaces MockCoreEnvelope
- No MockAgent (agents are config-driven)

This package provides mocks for jeeves_core_engine and jeeves_infra
dependencies, allowing mission system tests to run in isolation.

Usage:
    from mission_system.tests.fixtures.mocks import MockLLMAdapter, MockDatabaseClient
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
