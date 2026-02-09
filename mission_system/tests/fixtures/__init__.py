"""Test Fixtures Package.

Centralized Architecture (v4.0):
- Uses Envelope (not CoreEnvelope)
- Pre-populated envelope fixtures for each pipeline stage
- No concrete agent fixtures (agents are config-driven)

This package provides centralized, well-documented fixtures:
- database.py: SQLite fixtures and FK helpers
- llm.py: LLM provider fixture (LLAMASERVER_ALWAYS policy)
- services.py: Memory service fixtures
- agents.py: Envelope fixtures for pipeline testing

Fixtures are imported directly by conftest.py — no re-exports here.
This avoids circular imports between tests/fixtures/ and mission_system/tests/fixtures/.
"""
