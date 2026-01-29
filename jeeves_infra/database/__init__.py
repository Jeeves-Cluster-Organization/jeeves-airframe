"""Database infrastructure - protocols and factory.

Implementations (PostgreSQLClient, RedisClient, PostgresGraphAdapter) live in
jeeves-infra package. Import from there:

    from jeeves_infra.postgres import PostgreSQLClient, PostgresGraphAdapter
    from jeeves_infra.redis import RedisClient

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
