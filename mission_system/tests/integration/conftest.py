"""Pytest configuration and fixtures for integration tests.

PostgreSQL-Only Testing (SQLite deprecated as of 2025-11-27):
- All integration tests use PostgreSQL via testcontainers
- Test isolation via function-scoped database fixtures
- Proper cleanup for CI environments

Database Lifecycle:
- Async tests (AsyncClient): Can inject pg_test_db directly into app_state.db
- Sync tests (TestClient): Set database URL in environment, let lifespan create connection
  This avoids event loop mismatch issues with TestClient's separate thread.

GitHub Actions has limitations:
- No llama-server/LLM available
- Limited resources
- Strict timeouts
- Background tasks must be cleaned up properly
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path for tests.config import
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from fastapi.testclient import TestClient

from jeeves_infra.utils.testing import parse_postgres_url
from jeeves_infra.gateway.server import app, app_state

# CI detection constants
IS_CI = os.environ.get("CI", "").lower() in ("true", "1", "yes")
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
SILENCE_LIBRARY_LOGS = True


# NOTE: Markers are registered in tests/conftest.py (root conftest)
# Skip logic is also centralized there. This file only has integration-specific fixtures.

def pytest_configure(config):
    """Configure logging for integration tests.

    NOTE: Marker registration moved to tests/conftest.py for centralization.
    """
    # Configure logging to reduce noise in test output
    if SILENCE_LIBRARY_LOGS:
        # Silence noisy library loggers that pollute test output
        logging.getLogger("asyncpg").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Configure UTF-8 encoding for Windows BEFORE pytest starts
    # This runs once at session start, before any tests or fixtures
    import sys
    if sys.platform == "win32":
        import io
        # Only wrap if not already wrapped to avoid double-wrapping
        if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, io.TextIOWrapper):
            try:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            except Exception:
                pass  # If wrapping fails, continue with default encoding
        if hasattr(sys.stderr, 'buffer') and not isinstance(sys.stderr, io.TextIOWrapper):
            try:
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
            except Exception:
                pass  # If wrapping fails, continue with default encoding


# ============================================================
# PostgreSQL Test Client Fixtures
# ============================================================

@pytest.fixture(scope="function")
def sync_client(pg_test_db):
    """Synchronous test client backed by PostgreSQL.

    For sync tests (TestClient), we set the database URL in environment
    and let the lifespan create its own connection in the correct event loop.

    This avoids event loop mismatch issues that occur when trying to share
    an async database connection across different event loops.

    Args:
        pg_test_db: PostgreSQL database fixture (used to get URL)

    Yields:
        TestClient: FastAPI test client with PostgreSQL backend
    """
    # NOTE: Mission system integration tests access jeeves_infra directly for test utilities.
    # This is acceptable because mission_system IS the wiring layer, and these are
    # test-only utilities (reload_settings, reset_factory) not production code paths.
    from jeeves_infra.settings import reload_settings, get_settings
    from jeeves_infra.database.factory import reset_factory

    # Parse the test database URL into environment variables
    db_env = parse_postgres_url(pg_test_db.database_url)

    # Save original environment values for cleanup
    original_env = {
        "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
        "MOCK_MODE": os.environ.get("MOCK_MODE"),
        "LLM_PROVIDER": os.environ.get("LLM_PROVIDER"),
        "POSTGRES_HOST": os.environ.get("POSTGRES_HOST"),
        "POSTGRES_PORT": os.environ.get("POSTGRES_PORT"),
        "POSTGRES_DATABASE": os.environ.get("POSTGRES_DATABASE"),
        "POSTGRES_USER": os.environ.get("POSTGRES_USER"),
        "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
    }

    # Reset factory state
    reset_factory()

    # Configure environment for PostgreSQL testing
    os.environ["DATABASE_BACKEND"] = "postgres"
    os.environ["MOCK_MODE"] = "true"
    os.environ["LLM_PROVIDER"] = "mock"

    # Set database connection details from test database
    for key, value in db_env.items():
        os.environ[key] = value

    # Reload settings to pick up new environment
    reload_settings()
    settings = get_settings()
    settings.llm_provider = "mock"
    settings.memory_enabled = False

    # DO NOT inject app_state.db - let lifespan create its own connection
    # This avoids event loop mismatch with TestClient's separate thread

    try:
        with TestClient(app) as client:
            yield client
    finally:
        # Cleanup - restore original environment variables
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        app_state.shutdown_event.clear()
        app_state.db = None


# NOTE: pytest_collection_modifyitems moved to tests/conftest.py for centralization.
# All skip logic (CI, llama-server, websocket, etc.) is handled in root conftest.


@pytest.fixture(autouse=True, scope="function")
def cleanup_after_test(request):
    """Ensure cleanup after each integration test.

    This fixture only runs for integration tests to avoid interfering with
    unit tests and pytest's internal machinery. It properly handles asyncio
    cleanup without breaking pytest's capture mechanism.
    """
    # Only run cleanup for integration tests
    # Check both fspath and the test's own path to ensure we're in integration/
    try:
        test_path = str(request.fspath)
        if "integration" not in test_path:
            yield
            return
    except Exception:
        # If we can't determine path, skip cleanup to be safe
        yield
        return

    yield

    # Cleanup phase - only runs for integration tests
    try:
        # Clear any shutdown events
        if hasattr(app_state, 'shutdown_event'):
            app_state.shutdown_event.clear()
    except Exception:
        pass  # Ignore errors in cleanup

    # Cancel any pending tasks safely
    try:
        # Use get_running_loop to avoid creating new loops
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - this is fine, nothing to clean up
        return
    except Exception:
        # Any other error, skip cleanup
        return

    try:
        # Only cancel tasks if loop is not running (to avoid interfering with active operations)
        if not loop.is_running():
            pending = asyncio.all_tasks(loop)
            for task in pending:
                if not task.done():
                    task.cancel()
    except Exception as e:
        # Log but don't fail tests - cleanup is best effort
        try:
            import logging
            logging.getLogger(__name__).debug(f"Cleanup warning: {e}")
        except Exception:
            pass  # Ignore even logging errors
