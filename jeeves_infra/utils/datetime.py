"""Datetime utilities for timezone-aware operations."""

from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime.

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
