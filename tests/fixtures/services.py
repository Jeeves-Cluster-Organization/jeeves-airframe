"""Memory Service Fixtures for Tests.

Per Engineering Improvement Plan v4.2 - Configuration Centralization.

This module provides fixtures for memory infrastructure services:
- SessionStateService (L4 working memory)
- ToolHealthService (L7 tool metrics)
- ToolRegistry (tool registration)

All fixtures use real PostgreSQL database (no SQLite).

NOTE: This is a code analysis fork - only read-only code analysis tools.

Constitution v3.0 Compliance:
  REMOVED: OpenLoopService fixture (deleted feature)

Constitutional Import Boundary Note:
- Mission system layer IS the wiring layer between app and avionics
- Direct avionics imports are acceptable here for service fixtures
- App layer tests must use mission_system.adapters instead
"""

import pytest


@pytest.fixture
async def session_service(pg_test_db):
    """SessionStateService fixture.

    Provides L4 working memory functionality for tests.
    """
    from jeeves_infra.memory.services.session_state_service import SessionStateService

    service = SessionStateService(pg_test_db)
    await service.ensure_initialized()
    return service


@pytest.fixture
async def tool_health_service(pg_test_db):
    """ToolHealthService fixture.

    Provides L7 tool health metrics functionality for tests.
    """
    from jeeves_infra.memory.services.tool_health_service import ToolHealthService

    service = ToolHealthService(pg_test_db)
    await service.ensure_initialized()
    return service


@pytest.fixture
def tool_registry(pg_test_db):
    """Mock tool registry implementing ToolRegistryProtocol.

    Constitutional compliance: Mission system tests must not import from
    capability layer. This mock implements ToolRegistryProtocol for testing.

    For integration tests that need real tools, import from capability layer
    using sys.path like api/server.py does.
    """
    from jeeves_infra.protocols import ToolRegistryProtocol
    from typing import Any, Dict, List

    class MockToolRegistry:
        """Mock implementing ToolRegistryProtocol for mission system tests."""

        def __init__(self):
            self._tools = {
                "read_file": {"name": "read_file", "description": "Read a file"},
                "locate": {"name": "locate", "description": "Locate code"},
            }

        def list_tools(self) -> List[Dict[str, Any]]:
            return list(self._tools.values())

        def has_tool(self, name: str) -> bool:
            return name in self._tools

        def get_tool(self, name: str) -> Any:
            return self._tools.get(name)

        def get_tools_for_llm(self) -> str:
            return "mock tools"

        def get_read_only_tools(self) -> List[str]:
            return list(self._tools.keys())

    return MockToolRegistry()
