"""Pytest configuration and fixtures for integration tests.

Session 25 Update:
- Gateway uses gRPC-based app.py which requires running orchestrator
- Tests that need full orchestrator are skipped until gRPC test infra exists

PostgreSQL-Only Testing (SQLite deprecated as of 2025-11-27):
- All integration tests use PostgreSQL via testcontainers
- Test isolation via function-scoped database fixtures
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

# Gateway uses gRPC-based app.py (requires running orchestrator for full functionality)
from mission_system.gateway.app import app

# CI detection constants
IS_CI = os.environ.get("CI", "").lower() in ("true", "1", "yes")
IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
SILENCE_LIBRARY_LOGS = True


def pytest_configure(config):
    """Configure logging for integration tests."""
    if SILENCE_LIBRARY_LOGS:
        logging.getLogger("asyncpg").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Configure UTF-8 encoding for Windows
    if sys.platform == "win32":
        import io
        if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, io.TextIOWrapper):
            try:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            except Exception:
                pass
        if hasattr(sys.stderr, 'buffer') and not isinstance(sys.stderr, io.TextIOWrapper):
            try:
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
            except Exception:
                pass


# ============================================================
# PostgreSQL Test Client Fixtures
# ============================================================

@pytest.fixture(scope="function")
def sync_client(pg_test_db):
    """Synchronous test client backed by PostgreSQL.

    Note: The gRPC-based gateway (app.py) requires orchestrator.
    Health endpoints work without it, but /api/v1/* endpoints need gRPC.

    Args:
        pg_test_db: PostgreSQL database fixture (used to get URL)

    Yields:
        TestClient: FastAPI test client
    """
    from jeeves_infra.settings import reload_settings, get_settings
    from jeeves_infra.database.factory import reset_factory

    db_env = parse_postgres_url(pg_test_db.database_url)

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

    reset_factory()

    os.environ["DATABASE_BACKEND"] = "postgres"
    os.environ["MOCK_MODE"] = "true"
    os.environ["LLM_PROVIDER"] = "mock"

    for key, value in db_env.items():
        os.environ[key] = value

    reload_settings()
    settings = get_settings()
    settings.llm_provider = "mock"
    settings.memory_enabled = False

    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True, scope="function")
def cleanup_after_test(request):
    """Ensure cleanup after each integration test."""
    try:
        test_path = str(request.fspath)
        if "integration" not in test_path:
            yield
            return
    except Exception:
        yield
        return

    yield

    # Cancel any pending async tasks
    try:
        loop = asyncio.get_running_loop()
        if not loop.is_running():
            pending = asyncio.all_tasks(loop)
            for task in pending:
                if not task.done():
                    task.cancel()
    except RuntimeError:
        pass
    except Exception:
        pass
