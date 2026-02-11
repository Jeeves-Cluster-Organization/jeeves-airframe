"""Database client module.

Re-exports DatabaseClientProtocol and JSON utilities.
Concrete implementations are owned by capabilities (e.g. SQLiteClient).

Constitutional Reference:
- jeeves_infra.protocols: DatabaseClientProtocol definition
- Constitution R4: Swappable Implementations
"""

# Re-export protocol from canonical location
from jeeves_infra.protocols import DatabaseClientProtocol

# Re-export JSON utilities from centralized location
from jeeves_infra.utils.serialization import (
    JSONEncoderWithUUID,
    to_json,
    from_json,
)


__all__ = [
    "DatabaseClientProtocol",
    "JSONEncoderWithUUID",
    "to_json",
    "from_json",
]
