"""Database fixtures for tests.

Uses in-memory SQLite for fast, isolated tests with no external dependencies.
Each test gets a fresh database — no containers, no cleanup.
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from config.fixtures_data import TEST_USER_ID
from config.test_thresholds import TEST_HIGH_CONFIDENCE
from fixtures.sqlite_client import SQLiteClient

_SCHEMA = Path(__file__).parent / "test_schema.sql"


@pytest.fixture(scope="function")
async def test_db():
    """Fresh in-memory database for each test.

    Per Constitution P2 (Reliability):
    - Each test gets clean database state
    - No cross-test contamination
    - Predictable, deterministic test behavior
    """
    db = SQLiteClient()
    await db.connect()
    await db.initialize_schema(str(_SCHEMA))
    yield db
    await db.disconnect()


# ============================================================
# FK Prerequisites Helper Functions
# ============================================================

async def create_test_prerequisites(db, user_id: str = TEST_USER_ID) -> tuple:
    """Create prerequisite records (session -> request -> plan) for FK constraints.

    Args:
        db: DatabaseClientProtocol instance
        user_id: User ID for the records

    Returns:
        tuple: (session_id, request_id, plan_id) as strings
    """
    session_id = str(uuid4())
    request_id = str(uuid4())
    plan_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.insert("sessions", {
        "session_id": session_id,
        "user_id": user_id,
        "created_at": now,
        "last_activity": now,
    })

    await db.insert("requests", {
        "request_id": request_id,
        "user_id": user_id,
        "session_id": session_id,
        "user_message": "Test request",
        "received_at": now,
        "status": "processing",
    })

    await db.insert("execution_plans", {
        "plan_id": plan_id,
        "request_id": request_id,
        "intent": "test",
        "confidence": TEST_HIGH_CONFIDENCE,
        "plan_json": "{}",
        "created_at": now,
    })

    return session_id, request_id, plan_id


async def create_session_only(db, user_id: str = TEST_USER_ID) -> str:
    """Create a session record only.

    Args:
        db: DatabaseClientProtocol instance
        user_id: User ID for the session

    Returns:
        str: The created session_id
    """
    session_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.insert("sessions", {
        "session_id": session_id,
        "user_id": user_id,
        "created_at": now,
        "last_activity": now,
    })

    return session_id
