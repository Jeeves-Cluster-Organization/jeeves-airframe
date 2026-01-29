"""StructlogAdapter - Adapts structlog to LoggerProtocol for DI.

ADR-001 Decision 2: Logger Injection Architecture
This module provides the StructlogAdapter that implements LoggerProtocol,
enabling dependency injection of logging throughout the system.

Usage:
    from jeeves_infra.logging.adapter import StructlogAdapter
    import structlog

    # Create adapter for injection
    logger = StructlogAdapter(structlog.get_logger())
    agent = MyAgent(logger=logger)

    # Bind context
    bound_logger = logger.bind(request_id="req-123")
"""

from typing import Any, Optional

import structlog

from jeeves_infra.protocols import LoggerProtocol


class StructlogAdapter(LoggerProtocol):
    """Adapts structlog to LoggerProtocol for dependency injection.

    This adapter wraps a structlog BoundLogger and implements the
    LoggerProtocol interface, enabling clean DI of logging.

    ADR-001 Decision 2: Hybrid DI + contextvars for logging.
    - Core engine components receive LoggerProtocol via constructor
    - Tools/utilities can use get_current_logger() for context-based access
    """

    def __init__(
        self,
        logger: Optional[structlog.BoundLogger] = None,
    ):
        """Initialize adapter.

        Args:
            logger: Underlying structlog logger. If None, creates a new one.
        """
        self._logger = logger if logger is not None else structlog.get_logger()

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log at DEBUG level."""
        self._logger.debug(msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log at INFO level."""
        self._logger.info(msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log at WARNING level."""
        self._logger.warning(msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log at ERROR level."""
        self._logger.error(msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        """Log at ERROR level with exception info."""
        self._logger.exception(msg, **kwargs)

    def bind(self, **kwargs: Any) -> "StructlogAdapter":
        """Create child logger with bound context.

        Args:
            **kwargs: Context to bind to the logger

        Returns:
            New StructlogAdapter with bound context
        """
        return StructlogAdapter(self._logger.bind(**kwargs))

    def unbind(self, *keys: str) -> "StructlogAdapter":
        """Create child logger without specified context keys.

        Args:
            *keys: Context keys to remove

        Returns:
            New StructlogAdapter without the specified keys
        """
        return StructlogAdapter(self._logger.unbind(*keys))

    def new(self, **kwargs: Any) -> "StructlogAdapter":
        """Create new logger with only the specified context.

        Args:
            **kwargs: Initial context for the new logger

        Returns:
            New StructlogAdapter with fresh context
        """
        return StructlogAdapter(self._logger.new(**kwargs))


# Convenience function for creating adapters
def create_structlog_adapter(**context: Any) -> StructlogAdapter:
    """Create a StructlogAdapter with optional initial context.

    Args:
        **context: Initial context to bind

    Returns:
        StructlogAdapter ready for injection
    """
    logger = structlog.get_logger()
    if context:
        logger = logger.bind(**context)
    return StructlogAdapter(logger)


__all__ = [
    "StructlogAdapter",
    "create_structlog_adapter",
]
