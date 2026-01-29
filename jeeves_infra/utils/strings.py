"""String manipulation utilities."""

from typing import List, Union


def normalize_string_list(value: Union[str, List[str], None]) -> List[str]:
    """Normalize a value that could be a string, list, or None to a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        # Split by common delimiters
        if ',' in value:
            return [s.strip() for s in value.split(',') if s.strip()]
        if '\n' in value:
            return [s.strip() for s in value.split('\n') if s.strip()]
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(s).strip() for s in value if s]
    return []


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate string to max length with suffix."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
