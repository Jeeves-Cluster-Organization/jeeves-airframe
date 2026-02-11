"""Database infrastructure - protocol and utilities.

Concrete implementations are owned by capabilities.
Airframe provides only the protocol interface.
"""

from jeeves_infra.database.client import DatabaseClientProtocol

__all__ = [
    "DatabaseClientProtocol",
]
