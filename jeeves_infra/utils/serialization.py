"""Serialization utilities for datetime, JSON, and UUID handling.

Centralizes common serialization patterns used across the codebase:
- Datetime parsing and serialization
- JSON encoding with UUID and datetime support
- Type-safe conversions
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse a datetime value from various formats.

    Handles:
    - ISO format strings with "Z" suffix (Zulu/UTC time)
    - ISO format strings with timezone offset
    - datetime objects (pass-through)
    - None values

    Args:
        value: Value to parse (str, datetime, or None)

    Returns:
        Parsed datetime or None if input is None

    Example:
        dt = parse_datetime("2025-01-15T10:30:00+00:00")
        dt = parse_datetime("2025-01-15T10:30:00Z")
        dt = parse_datetime(existing_datetime)
        dt = parse_datetime(None)  # Returns None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Handle "Z" suffix for UTC times
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    return None


def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Serialize a datetime to ISO format string.

    Args:
        dt: Datetime to serialize (or None)

    Returns:
        ISO format string or None
    """
    if dt is None:
        return None
    return dt.isoformat()


def parse_datetime_field(data: Dict[str, Any], field: str) -> Optional[datetime]:
    """Parse a datetime field from a dictionary.

    Convenience function for parsing datetime fields in from_dict methods.

    Args:
        data: Dictionary containing the field
        field: Name of the field to parse

    Returns:
        Parsed datetime or None
    """
    return parse_datetime(data.get(field))


class JSONEncoderWithUUID(json.JSONEncoder):
    """JSON encoder that handles UUID and datetime objects.

    Use this encoder when serializing data that may contain:
    - UUID objects (converted to strings)
    - datetime objects (converted to ISO format)

    Example:
        json.dumps(data, cls=JSONEncoderWithUUID)
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def to_json(data: Any) -> str:
    """Convert Python object to JSON string.

    Handles UUID and datetime objects automatically.

    Args:
        data: Python object to serialize

    Returns:
        JSON string
    """
    return json.dumps(data, cls=JSONEncoderWithUUID)


def from_json(json_str: Optional[Union[str, Dict, list]]) -> Any:
    """Convert JSON string to Python object.

    Handles both JSON strings and already-parsed Python objects
    for compatibility with different database backends.

    Args:
        json_str: JSON string, dict, list, or None

    Returns:
        Parsed Python object or None
    """
    if json_str is None:
        return None

    # If already a Python object (dict/list), return as-is
    if isinstance(json_str, (dict, list)):
        return json_str

    # Otherwise parse as JSON string
    return json.loads(json_str)


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime.

    Convenience function for consistent UTC timestamps.

    Returns:
        Current UTC datetime with timezone info
    """
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return current UTC time as ISO format string.

    Returns:
        ISO format string of current UTC time
    """
    return utc_now().isoformat()


def ms_to_iso(ms: int) -> str:
    """Convert milliseconds timestamp to ISO format string.

    Args:
        ms: Unix timestamp in milliseconds

    Returns:
        ISO format string with UTC timezone

    Example:
        ms_to_iso(1702483200000)  # "2023-12-13T16:00:00+00:00"
    """
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def datetime_to_ms(dt: Any) -> int:
    """Convert datetime or datetime string to milliseconds timestamp.

    Args:
        dt: Datetime object, ISO format string, or None

    Returns:
        Unix timestamp in milliseconds, or 0 if dt is None/unparseable

    Example:
        datetime_to_ms(datetime.now(timezone.utc))  # 1702483200000
        datetime_to_ms("2023-12-13T16:00:00Z")  # 1702483200000
    """
    if dt is None:
        return 0
    # Handle strings by parsing first
    parsed = parse_datetime(dt)
    if parsed is None:
        return 0
    if parsed.tzinfo is None:
        # Assume UTC if no timezone
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


__all__ = [
    "parse_datetime",
    "serialize_datetime",
    "parse_datetime_field",
    "JSONEncoderWithUUID",
    "to_json",
    "from_json",
    "utc_now",
    "utc_now_iso",
    "ms_to_iso",
    "datetime_to_ms",
]
