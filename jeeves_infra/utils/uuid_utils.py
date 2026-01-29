"""UUID utility functions for consistent UUID handling across the codebase.

This module provides utilities for converting between different UUID formats,
ensuring consistency when working with PostgreSQL UUID columns and test fixtures.

Includes:
- uuid_str(): Universal UUID converter
- uuid_read(): Database row UUID reader
- convert_uuids_to_strings(): Convert all UUIDs in a dict
- UUIDStr: Pydantic type for UUID fields that accepts both UUID objects and strings
- OptionalUUIDStr: Optional variant of UUIDStr
"""

from typing import Annotated, Any, Dict, Optional, Union
from uuid import UUID, uuid5

try:
    from pydantic import BeforeValidator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False


def uuid_read(val: Union[str, UUID, None]) -> Optional[str]:
    """Convert UUID values from database rows to strings.

    Unlike uuid_str(), this function does NOT generate UUIDs from non-UUID strings.
    Use this when reading data FROM the database where values are already stored.

    Args:
        val: Value from database row (UUID object, string, or None)

    Returns:
        String representation if UUID, original string if string, None if None
    """
    if val is None:
        return None
    if isinstance(val, UUID):
        return str(val)
    return val


def uuid_str(identifier: Union[str, UUID, None]) -> Optional[str]:
    """Universal UUID converter - handles all UUID formats.

    This centralized function replaces all str(uuid), UUID() conversions, and
    manual UUID handling throughout the codebase. It intelligently handles:

    1. UUID objects -> converts to string
    2. Valid UUID strings -> returns as-is
    3. Simple test IDs ("test-session-1") -> generates deterministic UUID
    4. None -> returns None (for optional UUID fields)

    Args:
        identifier: Any UUID-like value (UUID object, string, or None)

    Returns:
        Valid UUID string for PostgreSQL, or None if input was None

    Examples:
        # Simple test IDs
        session_id = uuid_str("test-session-1")  # Deterministic UUID

        # UUID objects
        request_id = uuid_str(uuid4())  # String UUID

        # Already valid UUID strings
        task_id = uuid_str("550e8400-e29b-41d4-a716-446655440000")  # Pass-through

        # Optional fields
        parent_id = uuid_str(None)  # None

    Raises:
        TypeError: If the identifier is of an unsupported type
    """
    # Handle None for optional UUID fields
    if identifier is None:
        return None

    # If already a UUID object, convert to string
    if isinstance(identifier, UUID):
        return str(identifier)

    # If it's a string, check if it's a valid UUID
    if isinstance(identifier, str):
        try:
            # Try parsing as UUID - if successful, return as-is
            UUID(identifier)
            return identifier
        except (ValueError, AttributeError):
            pass

        # Not a valid UUID - generate deterministic UUID from the string
        # Use a fixed namespace for test UUIDs to ensure determinism
        TEST_NAMESPACE = UUID('12345678-1234-5678-1234-567812345678')
        return str(uuid5(TEST_NAMESPACE, identifier))

    # For any other type, try converting to string and then to UUID
    try:
        return uuid_str(str(identifier))
    except Exception:
        raise TypeError(
            f"uuid_str() cannot handle type {type(identifier).__name__}: {identifier}"
        )


def convert_uuids_to_strings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert UUID objects to strings in a dictionary.

    PostgreSQL returns UUID objects for UUID columns, but the rest of the
    codebase expects string IDs for consistency.

    Args:
        data: Dictionary potentially containing UUID objects

    Returns:
        Dictionary with UUID objects converted to strings
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        else:
            result[key] = value
    return result


def _coerce_uuid_to_str(v: Union[str, UUID, None]) -> Optional[str]:
    """Convert UUID objects to strings, pass through strings and None.

    This validator runs before Pydantic's standard validation, allowing
    models to accept both UUID objects and strings for ID fields while
    always storing them as strings internally.

    Args:
        v: A UUID object, string, or None

    Returns:
        String representation of UUID, or None if input was None
    """
    if v is None:
        return None
    if isinstance(v, UUID):
        return str(v)
    return v


# Pydantic types for UUID fields (only available if pydantic is installed)
if PYDANTIC_AVAILABLE:
    # UUIDStr: A string field that accepts both UUID objects and strings
    # Use this for all ID fields in Pydantic models (request_id, plan_id, etc.)
    #
    # Example usage:
    #     class MyModel(BaseModel):
    #         request_id: UUIDStr
    #         optional_id: Optional[UUIDStr] = None
    #
    #     # Both of these work:
    #     MyModel(request_id=uuid4())           # UUID object
    #     MyModel(request_id="abc-123-def")     # String
    #
    UUIDStr = Annotated[str, BeforeValidator(_coerce_uuid_to_str)]

    # OptionalUUIDStr: For optional UUID fields that can be None
    OptionalUUIDStr = Annotated[Optional[str], BeforeValidator(_coerce_uuid_to_str)]
else:
    # Fallback when pydantic is not available - just use str
    UUIDStr = str
    OptionalUUIDStr = Optional[str]


__all__ = [
    "uuid_str",
    "uuid_read",
    "convert_uuids_to_strings",
    "UUIDStr",
    "OptionalUUIDStr",
]
