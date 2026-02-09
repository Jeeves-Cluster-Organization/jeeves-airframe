"""Database factory using registry pattern.

Constitutional Reference:
- Avionics R4: Swappable Implementations
- Avionics R6: Database Backend Registry
- Avionics R2: Configuration Over Code
- Database Decoupling Audit (Option B)

Ownership Model:
- Production: Server lifespan owns database lifecycle
- Tests: Fixtures may inject pre-created database via app_state.db
- Factory creates clients on demand - no global caching

This ensures clean separation and no event loop issues.
"""

from typing import Optional, TYPE_CHECKING
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol
from jeeves_infra.database.registry import create_database_client as _create_client

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

    All schemas come from CapabilityResourceRegistry — capabilities own their
    schemas and register them during wire_capabilities().

    Reference: Avionics R3 (No Domain Logic), R4 (Swappable Implementations)
    """
    from jeeves_infra.protocols import get_capability_resource_registry

    registry = get_capability_resource_registry()
    all_schemas = registry.get_schemas()
    if not all_schemas:
        return

    try:
        await client.fetch_one("SELECT 1 FROM sessions LIMIT 1")
        return  # Schema already initialized
    except Exception:
        pass  # Table doesn't exist, proceed with schema init

    logger.info("initializing_database_schema")
    for schema_path in all_schemas:
        logger.info("initializing_schema", schema_path=schema_path)
        await client.initialize_schema(schema_path)


def reset_factory():
    """Reset factory state. No-op since factory doesn't cache."""
    pass


__all__ = [
    "create_database_client",
    "reset_factory",
]
