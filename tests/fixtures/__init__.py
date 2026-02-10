"""Test Fixtures Package.

Provides centralized fixtures for jeeves-infra tests:
- database.py: SQLite fixtures and FK helpers
- sqlite_client.py: In-memory SQLite client (DatabaseClientProtocol)
- llm.py: LLM provider fixtures
- services.py: Service fixtures
- agents.py: Envelope fixtures for pipeline testing
- mocks/: Mock implementations for isolated testing

Fixtures are imported directly by conftest.py — no re-exports here.
This avoids circular imports between fixture modules.
"""
