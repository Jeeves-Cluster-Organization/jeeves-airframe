"""Database client module.

Provides protocol-based database access via registry pattern.
PostgreSQL is the default backend (Constitution v3.0).

Constitutional Reference:
- CommBus: DatabaseClientProtocol definition
- Avionics R4: Swappable Implementations
- Avionics R6: Database Backend Registry
- PostgreSQL Decoupling Audit (Option B)

Usage:
    from avionics.database.client import (
        DatabaseClientProtocol,
        create_database_client,
    )

    # Create client
    client = await create_database_client(settings)
    await client.connect()

    # Use client
    result = await client.fetch_one("SELECT * FROM users WHERE id = :id", {"id": 1})

    # Cleanup
    await client.disconnect()
"""

# Re-export protocol from canonical location
from jeeves_infra.protocols import DatabaseClientProtocol, VectorStorageProtocol

# Re-export registry functions
from jeeves_infra.database.registry import (
    create_database_client,
    register_backend,
    unregister_backend,
    list_backends,
    is_backend_registered,
)

# Re-export JSON utilities from centralized location
from jeeves_infra.utils.serialization import (
    JSONEncoderWithUUID,
    to_json,
    from_json,
)


__all__ = [
    # Protocols (from commbus)
    "DatabaseClientProtocol",
    "VectorStorageProtocol",
    # Factory (from registry)
    "create_database_client",
    # Registry functions
    "register_backend",
    "unregister_backend",
    "list_backends",
    "is_backend_registered",
    # JSON utilities
    "JSONEncoderWithUUID",
    "to_json",
    "from_json",
]
