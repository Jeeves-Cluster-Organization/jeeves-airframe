"""
Database Schema Initialization

Schema init for fresh deployments using the backend registry.
Constitutional Alignment: Amendment I (No bloat), M1 (Ground truth)

Schemas are registered by capabilities via CapabilityResourceRegistry.
The factory loads all registered schemas during client creation.

NOTE: This module accepts a DatabaseClientProtocol via DI.
The kernel does not import infrastructure implementations.
"""

import asyncio
from typing import Optional
import os

from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


async def init_schema(
    db: DatabaseClientProtocol,
    logger: Optional[LoggerProtocol] = None
) -> None:
    """Initialize database schema from registered capability schemas.

    Loads all schemas registered via CapabilityResourceRegistry.

    Args:
        db: Connected DatabaseClientProtocol instance (injected)
        logger: Logger for DI (uses context logger if not provided)
    """
    _logger = logger or get_current_logger()
    _logger.info("initializing_database_schema")

    from jeeves_infra.protocols import get_capability_resource_registry
    registry = get_capability_resource_registry()
    schema_paths = registry.get_schemas()

    if not schema_paths:
        _logger.warning("no_schemas_registered", message="No schemas found in capability registry")
        return

    for schema_path in schema_paths:
        _logger.info("loading_schema_file", path=schema_path)
        await db.initialize_schema(schema_path)

    _logger.info("schema_initialized")


async def main():
    """Standalone schema init using registry and factory.

    Requires a registered database backend (via capability wiring)
    and POSTGRES_URL or POSTGRES_* environment variables.
    """
    _logger = get_current_logger()

    from jeeves_infra.database.factory import create_database_client
    from jeeves_infra.settings import get_settings

    settings = get_settings()
    db = await create_database_client(settings, auto_init_schema=True)

    try:
        _logger.info("database_schema_initialized", backend=db.backend)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
