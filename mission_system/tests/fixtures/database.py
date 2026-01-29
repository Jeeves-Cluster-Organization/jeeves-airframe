"""Database Fixtures for Tests.

Per Engineering Improvement Plan v4.2 - Configuration Centralization.

This module provides:
- PostgreSQL container management (Docker Compose or testcontainers)
- Fresh database per test (pg_test_db)
- FK prerequisite helpers for test data setup

Constitutional Compliance:
- P2: Reliability - each test gets clean database state
- P6: Testable - predictable, deterministic test behavior
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from jeeves_infra.utils.testing import is_running_in_docker
from mission_system.tests.config.fixtures_data import TEST_USER_ID
from mission_system.tests.config.test_thresholds import TEST_HIGH_CONFIDENCE


# ============================================================
# PostgreSQL Container Classes
# ============================================================

class ComposePostgresContainer:
    """Container class for compose PostgreSQL service.

    Provides same interface as testcontainers PostgresContainer.
    """

    def __init__(self, host: str, port: int, user: str, password: str, dbname: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.dbname = dbname

    def get_connection_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbname}"


# ============================================================
# PostgreSQL Fixtures
# ============================================================

@pytest.fixture(scope="session")
def postgres_container():
    """PostgreSQL container for all tests.

    Uses compose service if running in Docker, otherwise testcontainers.
    Container is shared across all tests to minimize startup overhead.
    """
    if is_running_in_docker():
        # In Docker, use environment variables from docker-compose
        postgres_host = os.environ.get("POSTGRES_HOST", "postgres")
        postgres_port = int(os.environ.get("POSTGRES_PORT", "5432"))
        postgres_user = os.environ.get("POSTGRES_USER", "assistant")
        postgres_password = os.environ.get("POSTGRES_PASSWORD", "dev_password_change_in_production")
        postgres_db = os.environ.get("POSTGRES_DATABASE", "assistant")

        yield ComposePostgresContainer(
            host=postgres_host,
            port=postgres_port,
            user=postgres_user,
            password=postgres_password,
            dbname=postgres_db,
        )
        return

    # Outside Docker, use testcontainers
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="postgres",
        password="postgres",
        dbname="test",
    ) as postgres:
        # Wrap to provide asyncpg-compatible URL
        original_url = postgres.get_connection_url()
        # Convert psycopg2 URL to asyncpg URL
        asyncpg_url = original_url.replace("postgresql://", "postgresql+asyncpg://")
        # Replace psycopg2 with asyncpg if present
        asyncpg_url = asyncpg_url.replace("psycopg2", "asyncpg")

        # Create wrapper with asyncpg URL
        wrapper = ComposePostgresContainer(
            host=postgres.get_container_host_ip(),
            port=int(postgres.get_exposed_port(5432)),
            user="postgres",
            password="postgres",
            dbname="test",
        )
        yield wrapper


@pytest.fixture(scope="function")
async def pg_test_db(postgres_container):
    """Fresh PostgreSQL database for each test.

    Creates unique database per test for isolation.
    Applies consolidated PostgreSQL schema automatically.

    Per Constitution P2 (Reliability):
    - Each test gets clean database state
    - No cross-test contamination
    - Predictable, deterministic test behavior

    Constitutional Note:
    - Mission system layer IS the wiring layer between app and jeeves_infra
    - Direct jeeves_infra imports are acceptable here for infrastructure setup
    - App layer tests must use mission_system.adapters instead
    """
    # Mission system is the wiring layer - jeeves_infra imports acceptable
    from jeeves_infra.postgres.client import PostgreSQLClient
    from sqlalchemy import text

    db_name = f"test_{uuid.uuid4().hex[:8]}"
    admin_url = postgres_container.get_connection_url()

    admin_client = PostgreSQLClient(admin_url)
    await admin_client.connect()

    try:
        async with admin_client.engine.connect() as conn:
            conn_with_autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn_with_autocommit.execute(text(f"CREATE DATABASE {db_name}"))
    finally:
        await admin_client.disconnect()

    test_url = admin_url.rsplit("/", 1)[0] + f"/{db_name}"
    db = PostgreSQLClient(test_url)
    await db.connect()

    # Load core schema (infrastructure owns this)
    # Path is relative to jeeves_infra package
    infra_schemas_dir = Path(__file__).parent.parent.parent.parent / "jeeves_infra" / "database" / "schemas"
    await db.initialize_schema(str(infra_schemas_dir / "001_postgres_schema.sql"))

    # Load capability schemas from registry (constitutional pattern)
    # Infrastructure R3: No Domain Logic - registry lookup instead of hardcoded paths
    from jeeves_infra.protocols import get_capability_resource_registry
    registry = get_capability_resource_registry()
    for schema_path in registry.get_schemas():
        if Path(schema_path).exists():
            await db.initialize_schema(schema_path)

    yield db

    await db.disconnect()

    admin_client = PostgreSQLClient(admin_url)
    await admin_client.connect()
    try:
        async with admin_client.engine.connect() as conn:
            conn_with_autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn_with_autocommit.execute(
                text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}'")
            )
            await conn_with_autocommit.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
    finally:
        await admin_client.disconnect()


# ============================================================
# FK Prerequisites Helper Functions
# ============================================================

async def create_test_prerequisites(db, user_id: str = TEST_USER_ID) -> tuple:
    """Create prerequisite records (session -> request -> plan) for FK constraints.

    FK constraints require:
    - sessions row for requests.session_id
    - requests row for execution_plans.request_id
    - execution_plans row for tool_executions.plan_id

    Args:
        db: PostgreSQLClient instance
        user_id: User ID for the records (default: TEST_USER_ID from fixtures_data)

    Returns:
        tuple: (session_id, request_id, plan_id) as strings
    """
    session_id = str(uuid4())
    request_id = str(uuid4())
    plan_id = str(uuid4())
    now = datetime.now(timezone.utc)

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

    Use when you only need a session_id for FK constraints.

    Args:
        db: PostgreSQLClient instance
        user_id: User ID for the session (default: TEST_USER_ID from fixtures_data)

    Returns:
        str: The created session_id
    """
    session_id = str(uuid4())
    now = datetime.now(timezone.utc)

    await db.insert("sessions", {
        "session_id": session_id,
        "user_id": user_id,
        "created_at": now,
        "last_activity": now,
    })

    return session_id
