"""ID Generator Implementation.

Provides UUID-based ID generation implementing IdGeneratorProtocol.
This is the standard implementation for generating unique identifiers
throughout the system.

Constitutional Reference:
- Contracts C3: Dependency Injection - all services injected, not imported
- Kubernetes Pattern: Protocol-first design with swappable implementations

Usage:
    from jeeves_infra.utils.id_generator import UUIDGenerator

    generator = UUIDGenerator()
    id = generator.generate()  # "550e8400-e29b-41d4-a716-446655440000"
    prefixed = generator.generate_prefixed("req")  # "req_550e8400..."

For testing, use DeterministicIdGenerator which generates predictable IDs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterator, Optional
from uuid import UUID, uuid4, uuid5

from jeeves_infra.protocols import IdGeneratorProtocol


# Fixed namespace for deterministic ID generation
_TEST_NAMESPACE = UUID("12345678-1234-5678-1234-567812345678")


class UUIDGenerator:
    """UUID-based ID generator implementing IdGeneratorProtocol.

    Uses uuid4() for random IDs and uuid5() for deterministic prefixed IDs.
    This is the standard production implementation.

    Thread-safe for concurrent usage.
    """

    def generate(self) -> str:
        """Generate a new random UUID.

        Returns:
            UUID string in standard format (e.g., "550e8400-e29b-41d4-a716-446655440000")
        """
        return str(uuid4())

    def generate_prefixed(self, prefix: str) -> str:
        """Generate a prefixed ID.

        The prefix is prepended with an underscore separator.
        The UUID portion is still random.

        Args:
            prefix: Prefix string (e.g., "req", "task", "session")

        Returns:
            Prefixed UUID string (e.g., "req_550e8400-e29b-41d4-a716-446655440000")
        """
        return f"{prefix}_{uuid4()}"


class DeterministicIdGenerator:
    """Deterministic ID generator for testing.

    Generates predictable, reproducible IDs based on a seed value.
    Useful for testing scenarios where ID predictability is important.

    Not thread-safe - use separate instances per thread in concurrent tests.
    """

    def __init__(self, seed: str = "test"):
        """Initialize with a seed value.

        Args:
            seed: Seed string for deterministic generation
        """
        self._seed = seed
        self._counter = 0

    def generate(self) -> str:
        """Generate a deterministic UUID based on seed and counter.

        Returns:
            Deterministic UUID string
        """
        self._counter += 1
        input_str = f"{self._seed}:{self._counter}"
        return str(uuid5(_TEST_NAMESPACE, input_str))

    def generate_prefixed(self, prefix: str) -> str:
        """Generate a prefixed deterministic ID.

        Args:
            prefix: Prefix string (e.g., "req", "task")

        Returns:
            Prefixed deterministic UUID string
        """
        return f"{prefix}_{self.generate()}"

    def reset(self) -> None:
        """Reset the counter to 0.

        Useful between test cases to get reproducible sequences.
        """
        self._counter = 0


class SequentialIdGenerator:
    """Sequential ID generator for debugging.

    Generates simple, human-readable sequential IDs.
    Useful for debugging and log analysis where UUIDs are hard to track.

    Format: "{prefix}_{counter:06d}" or "{counter:06d}" without prefix

    Not for production use - IDs are not unique across instances.
    """

    def __init__(self, start: int = 1):
        """Initialize with a starting counter value.

        Args:
            start: Starting counter value (default: 1)
        """
        self._counter = start

    def generate(self) -> str:
        """Generate a sequential ID.

        Returns:
            Zero-padded sequential ID (e.g., "000001", "000002")
        """
        result = f"{self._counter:06d}"
        self._counter += 1
        return result

    def generate_prefixed(self, prefix: str) -> str:
        """Generate a prefixed sequential ID.

        Args:
            prefix: Prefix string

        Returns:
            Prefixed sequential ID (e.g., "req_000001")
        """
        return f"{prefix}_{self.generate()}"


class TimestampIdGenerator:
    """Timestamp-based ID generator.

    Generates IDs that include a timestamp component for sortability.
    Format: "{timestamp}_{random}" where timestamp is ISO format without colons.

    Useful when chronological ordering of IDs is needed.
    """

    def generate(self) -> str:
        """Generate a timestamp-based ID.

        Returns:
            Timestamp-prefixed UUID (e.g., "20240119T143022_550e8400...")
        """
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        return f"{ts}_{uuid4().hex[:12]}"

    def generate_prefixed(self, prefix: str) -> str:
        """Generate a prefixed timestamp-based ID.

        Args:
            prefix: Prefix string

        Returns:
            Prefixed timestamp ID (e.g., "req_20240119T143022_550e8400...")
        """
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        return f"{prefix}_{ts}_{uuid4().hex[:12]}"


# Default singleton instance
_default_generator: Optional[UUIDGenerator] = None


def get_id_generator() -> IdGeneratorProtocol:
    """Get the default ID generator instance.

    Returns:
        UUIDGenerator singleton instance
    """
    global _default_generator
    if _default_generator is None:
        _default_generator = UUIDGenerator()
    return _default_generator


def reset_id_generator() -> None:
    """Reset the default ID generator (for testing)."""
    global _default_generator
    _default_generator = None


# Verify protocol implementation at module load time
_: IdGeneratorProtocol = UUIDGenerator()


__all__ = [
    "UUIDGenerator",
    "DeterministicIdGenerator",
    "SequentialIdGenerator",
    "TimestampIdGenerator",
    "get_id_generator",
    "reset_id_generator",
]
