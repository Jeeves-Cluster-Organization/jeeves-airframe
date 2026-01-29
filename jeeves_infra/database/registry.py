"""Database backend registry.

Provides factory pattern for database client creation with support
for multiple backends. The registry is empty by default - backends
must be registered by the application/capability at startup.

Constitutional Reference:
- Avionics R4: Swappable Implementations
- Avionics R6: Database Backend Registry
- PostgreSQL Decoupling Audit (Option B)

Usage:
    # In capability/application startup:
    from avionics.database.registry import register_backend
    from jeeves_infra.postgres.client import PostgreSQLClient

    register_backend("postgres", PostgreSQLClient, postgres_config_builder)

    # Then create clients:
    client = await create_database_client(settings)
"""

from typing import Any, Callable, Dict, Optional, Type, TYPE_CHECKING
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol

if TYPE_CHECKING:
    from jeeves_infra.settings import Settings


# Backend registry: maps backend name to (client_class, config_builder)
# Config builder is a callable that takes (settings, logger) and returns kwargs for client
_BACKENDS: Dict[str, tuple[Type, Callable[['Settings', LoggerProtocol], Dict[str, Any]]]] = {}


def register_backend(
    name: str,
    client_class: Type[DatabaseClientProtocol],
    config_builder: Callable[['Settings', LoggerProtocol], Dict[str, Any]]
) -> None:
    """Register a database backend implementation.

    Args:
        name: Backend identifier (e.g., 'postgres', 'sqlite')
        client_class: Class implementing DatabaseClientProtocol
        config_builder: Function that builds client config from settings

    Example:
        def postgres_config(settings, logger):
            return {
                "database_url": settings.get_postgres_url(),
                "pool_size": settings.postgres_pool_size,
                ...
            }

        register_backend("postgres", PostgreSQLClient, postgres_config)
    """
    _BACKENDS[name] = (client_class, config_builder)


def unregister_backend(name: str) -> bool:
    """Unregister a database backend.

    Args:
        name: Backend identifier to remove

    Returns:
        True if backend was registered and removed
    """
    if name in _BACKENDS:
        del _BACKENDS[name]
        return True
    return False


def get_backend(name: str) -> Optional[tuple[Type[DatabaseClientProtocol], Callable]]:
    """Get a registered backend class and config builder.

    Args:
        name: Backend identifier

    Returns:
        Tuple of (client_class, config_builder) or None if not found
    """
    return _BACKENDS.get(name)


def list_backends() -> list[str]:
    """List all registered backend names.

    Returns:
        List of registered backend identifiers
    """
    return list(_BACKENDS.keys())


def is_backend_registered(name: str) -> bool:
    """Check if a backend is registered.

    Args:
        name: Backend identifier

    Returns:
        True if backend is registered
    """
    return name in _BACKENDS


async def create_database_client(
    settings: 'Settings',
    backend: Optional[str] = None,
    logger: Optional[LoggerProtocol] = None,
    **kwargs
) -> DatabaseClientProtocol:
    """Factory function to create database client.

    Creates a new client instance using the registry. The caller
    owns the client lifecycle (connect/disconnect).

    Args:
        settings: Application settings
        backend: Backend name (default: from settings.database_backend)
        logger: Logger for DI (uses context logger if not provided)
        **kwargs: Additional kwargs passed to client constructor

    Returns:
        Database client implementing DatabaseClientProtocol

    Raises:
        ValueError: If backend is not registered. Make sure to register
                   backends at application startup before calling this.
    """
    _logger = logger or get_current_logger()
    backend_name = backend or settings.database_backend

    entry = _BACKENDS.get(backend_name)
    if not entry:
        available = ", ".join(_BACKENDS.keys()) or "(none - register backends at startup)"
        raise ValueError(f"Unknown database backend '{backend_name}'. Available: {available}")

    client_class, config_builder = entry

    _logger.info("creating_database_client", backend=backend_name)

    # Build configuration from settings
    config = config_builder(settings, _logger)

    # Override with explicit kwargs
    config.update(kwargs)

    # Create client instance
    client = client_class(**config)

    return client


# =============================================================================
# Config Builder Helpers (for use by jeeves-infra or capabilities)
# =============================================================================

def postgres_config_builder(settings: 'Settings', logger: LoggerProtocol) -> Dict[str, Any]:
    """Build PostgreSQL client configuration from settings.

    This is a helper function that can be used when registering the postgres backend:

        from jeeves_infra.postgres.client import PostgreSQLClient
        from avionics.database.registry import register_backend, postgres_config_builder

        register_backend("postgres", PostgreSQLClient, postgres_config_builder)
    """
    return {
        "database_url": settings.get_postgres_url(),
        "pool_size": settings.postgres_pool_size,
        "max_overflow": settings.postgres_max_overflow,
        "pool_timeout": settings.postgres_pool_timeout,
        "pool_recycle": settings.postgres_pool_recycle,
        "logger": logger,
    }


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Registration functions
    "register_backend",
    "unregister_backend",
    "get_backend",
    "list_backends",
    "is_backend_registered",
    # Factory function
    "create_database_client",
    # Config builder helpers
    "postgres_config_builder",
]
