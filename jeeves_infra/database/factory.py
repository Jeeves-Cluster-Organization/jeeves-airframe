"""Database factory using registry pattern.

Constitutional Reference:
- Avionics R4: Swappable Implementations
- Avionics R6: Database Backend Registry
- Avionics R2: Configuration Over Code
- PostgreSQL Decoupling Audit (Option B)

Ownership Model:
- Production: Server lifespan owns database lifecycle
- Tests: Fixtures may inject pre-created database via app_state.db
- Factory creates clients on demand - no global caching

This ensures clean separation and no event loop issues.
"""

from pathlib import Path
from typing import Optional, TYPE_CHECKING
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol
from jeeves_infra.database.registry import create_database_client as _create_client

# Core infrastructure schema path - resolved relative to this module
# This ensures portability regardless of working directory (R2: Configuration Over Code)
_CORE_SCHEMAS_DIR = Path(__file__).parent / "schemas"

if TYPE_CHECKING:
    from jeeves_infra.settings import Settings


async def create_database_client(
    settings: 'Settings',
    logger: Optional[LoggerProtocol] = None,
    auto_init_schema: bool = True
) -> DatabaseClientProtocol:
    """Create and initialize a database client.

    Creates a new client instance using the registry. Caller owns the lifecycle.

    Args:
        settings: Application settings
        logger: Logger for DI (uses context logger if not provided)
        auto_init_schema: If True, initialize schema on first run

    Returns:
        DatabaseClientProtocol instance (connected, schema verified)
    """
    _logger = logger or get_current_logger()

    # Create client via registry
    client = await _create_client(settings, logger=_logger)

    # Connect
    await client.connect()

    # Auto-initialize schema if needed
    if auto_init_schema:
        await _maybe_init_schema(client, _logger)

    _logger.info("database_client_ready", backend=client.backend)
    return client


async def _maybe_init_schema(client: DatabaseClientProtocol, logger: LoggerProtocol) -> None:
    """Initialize database schema if needed (first-run setup).

    Constitutional Pattern:
    - Core schema (001_postgres_schema.sql) is always initialized by infrastructure
    - Capability schemas are registered via CapabilityResourceRegistry
    - Infrastructure queries the registry, avoiding hardcoded capability knowledge

    Reference: Avionics R3 (No Domain Logic), R4 (Swappable Implementations)
    """
    # Only PostgreSQL has schema initialization for now
    if client.backend != "postgres":
        return

    # Import registry to get capability schemas
    from jeeves_infra.protocols import get_capability_resource_registry

    try:
        result = await client.fetch_one(
            "SELECT COUNT(*) AS count FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = 'sessions'"
        )
        if result and result.get('count', 0) == 0:
            logger.info("initializing_database_schema")
            # Initialize core infrastructure schemas (sorted by filename for ordering)
            # Uses Path-relative resolution for portability (R2: Configuration Over Code)
            for schema_file in sorted(_CORE_SCHEMAS_DIR.glob("*.sql")):
                logger.info("initializing_core_schema", schema_path=schema_file.name)
                await client.initialize_schema(str(schema_file))

            # Initialize capability schemas from registry
            registry = get_capability_resource_registry()
            for schema_path in registry.get_schemas():
                logger.info("initializing_capability_schema", schema_path=schema_path)
                await client.initialize_schema(schema_path)
    except Exception as e:
        logger.error(
            "schema_check_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        # If check fails, try initializing anyway
        # Uses Path-relative resolution for portability (R2: Configuration Over Code)
        for schema_file in sorted(_CORE_SCHEMAS_DIR.glob("*.sql")):
            logger.info("initializing_core_schema_fallback", schema_path=schema_file.name)
            await client.initialize_schema(str(schema_file))

        # Initialize capability schemas from registry
        registry = get_capability_resource_registry()
        for schema_path in registry.get_schemas():
            logger.info("initializing_capability_schema_fallback", schema_path=schema_path)
            await client.initialize_schema(schema_path)


def reset_factory():
    """Reset factory state. No-op since factory doesn't cache."""
    pass


__all__ = [
    "create_database_client",
    "reset_factory",
]
