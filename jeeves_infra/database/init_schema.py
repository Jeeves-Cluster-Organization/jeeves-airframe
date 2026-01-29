"""
Database Schema Initialization

PostgreSQL-only schema init for fresh deployments.
Constitutional Alignment: Amendment I (No bloat), M1 (Ground truth)

Per PostgreSQL-only migration (2025-11-27):
- Uses consolidated postgres_schema.sql with all tables (L1-L7)
- No SQLite support
- No migrations needed - DROP/CREATE approach

NOTE: This module accepts a DatabaseClientProtocol via DI.
The kernel does not import infrastructure implementations.
"""

import asyncio
from pathlib import Path
from typing import Optional
import os

from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


async def init_schema(
    db: DatabaseClientProtocol,
    logger: Optional[LoggerProtocol] = None
) -> None:
    """Initialize complete database schema (L1-L7).

    Uses consolidated postgres_schema.sql which includes:
    - L1: Core tables (sessions, requests, tasks, etc.)
    - L2: Domain events and agent traces
    - L3: Semantic chunks
    - L4: Working memory (session_state, open_loops)
    - L5: Graph tables
    - L7: Governance tables

    Args:
        db: Connected DatabaseClientProtocol instance (injected)
        logger: Logger for DI (uses context logger if not provided)
    """
    _logger = logger or get_current_logger()
    _logger.info("initializing_database_schema")

    schemas_dir = Path(__file__).parent / "schemas"

    # Load schema files in order (001_ first, then 002_, etc.)
    schema_files = sorted(schemas_dir.glob("*.sql"))

    if not schema_files:
        raise FileNotFoundError(f"No schema files found in: {schemas_dir}")

    # Use DatabaseClientProtocol's initialize_schema which handles complex SQL
    for schema_path in schema_files:
        _logger.info("loading_schema_file", path=str(schema_path.name))
        await db.initialize_schema(str(schema_path))

    _logger.info("schema_initialized")


async def main():
    """Standalone schema init (requires PostgreSQL environment variables).

    NOTE: This main() function imports from jeeves-infra for convenience.
    For pure kernel usage, inject the database client via init_schema().
    """
    _logger = get_current_logger()

    # Import infrastructure at runtime for standalone script usage
    try:
        from jeeves_infra.postgres.client import PostgreSQLClient
    except ImportError:
        _logger.error(
            "jeeves_infra_required",
            message="Standalone init requires jeeves-infra package"
        )
        raise ImportError(
            "jeeves-infra package required for standalone usage. "
            "Install with: pip install jeeves-infra[postgres]"
        )

    # Check for explicit URL first
    url = os.environ.get("POSTGRES_URL")

    if not url:
        # Build connection URL from environment
        postgres_host = os.environ.get("POSTGRES_HOST", "localhost")
        postgres_port = os.environ.get("POSTGRES_PORT", "5432")
        postgres_user = os.environ.get("POSTGRES_USER", "assistant")
        postgres_password = os.environ.get("POSTGRES_PASSWORD")
        postgres_db = os.environ.get("POSTGRES_DATABASE", "assistant")

        if not postgres_password:
            _logger.error(
                "postgres_password_required",
                message="POSTGRES_PASSWORD environment variable is required"
            )
            raise ValueError(
                "POSTGRES_PASSWORD environment variable is required. "
                "Set it or provide POSTGRES_URL."
            )

        url = f"postgresql+asyncpg://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"

    db = PostgreSQLClient(url, logger=_logger)
    await db.connect()

    try:
        await init_schema(db, logger=_logger)
        _logger.info("database_schema_initialized", backend="postgresql")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
