"""Database infrastructure - protocols and factory.

Concrete implementations (PostgreSQLClient, etc.) are owned by capabilities
and registered via the backend registry at startup.

This module provides:
- DatabaseClientProtocol (interface)
- create_database_client (factory that uses registry)
"""

from jeeves_infra.database.client import DatabaseClientProtocol
from jeeves_infra.database.factory import create_database_client

__all__ = [
    "DatabaseClientProtocol",
    "create_database_client",
]
