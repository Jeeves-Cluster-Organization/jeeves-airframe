"""Centralized Logging Infrastructure for Jeeves Runtime.

This module provides the core logging utilities that can be used by all layers.
It implements LoggerProtocol from protocols.

Usage:
    from jeeves_infra.utils.logging import create_logger, get_component_logger

    # Create logger for injection
    logger = create_logger("my_component", envelope_id="...")

    # Get component-bound logger
    logger = get_component_logger("ChunkService")
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Generator, Optional

import structlog

from jeeves_infra.protocols import LoggerProtocol, RequestContext

# Module state
_CONFIGURED = False

# Context variables for request-scoped data
_request_context: ContextVar[Optional[RequestContext]] = ContextVar(
    "request_context",
    default=None
)

_current_logger: ContextVar[Optional[LoggerProtocol]] = ContextVar(
    "current_logger",
    default=None
)


class Logger:
    """LoggerProtocol implementation backed by structlog.

    This is the primary logger implementation used throughout Jeeves.
    """

    def __init__(
        self,
        base_logger: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Initialize logger.

        Args:
            base_logger: Underlying structlog logger (created if None)
            context: Bound context fields
        """
        self._logger = base_logger or structlog.get_logger()
        self._context = context or {}

        # Apply context bindings
        if self._context:
            self._logger = self._logger.bind(**self._context)

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._logger.debug(msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message."""
        self._logger.info(msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._logger.warning(msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message."""
        self._logger.error(msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        """Log critical message."""
        self._logger.critical(msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        self._logger.exception(msg, **kwargs)

    def bind(self, **kwargs: Any) -> "Logger":
        """Create child logger with additional context."""
        new_context = {**self._context, **kwargs}
        return Logger(
            base_logger=structlog.get_logger(),
            context=new_context,
        )


def configure_logging(
    level: str = "INFO",
    *,
    json_output: bool = True,
    component_levels: Optional[Dict[str, str]] = None,
) -> None:
    """Configure logging for the Jeeves runtime.

    This should be called ONCE at application startup.

    Args:
        level: Default log level (DEBUG, INFO, WARNING, ERROR)
        json_output: If True, output JSON; if False, console format
        component_levels: Override levels for specific components
    """
    global _CONFIGURED

    if _CONFIGURED:
        return

    # Parse level
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib logging
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stdout,
    )

    # Silence noisy libraries
    for noisy in ["httpx", "httpcore", "urllib3", "grpc", "asyncpg"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Apply component-level overrides
    env_overrides = {
        "agent": os.environ.get("AGENT_LOG_LEVEL", "").upper() or level.upper(),
        "tool": os.environ.get("TOOL_LOG_LEVEL", "").upper() or level.upper(),
        "db": os.environ.get("DB_LOG_LEVEL", "").upper() or "WARNING",
    }
    if component_levels:
        env_overrides.update(component_levels)

    for component, comp_level in env_overrides.items():
        logging.getLogger(component).setLevel(
            getattr(logging, comp_level, log_level)
        )

    # Configure structlog
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    if json_output:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def create_logger(
    component: str,
    **context: Any,
) -> LoggerProtocol:
    """Create a logger for dependency injection.

    Args:
        component: Component name (e.g., "planner", "tool_executor")
        **context: Additional context to bind

    Returns:
        LoggerProtocol implementation
    """
    return Logger(context={"component": component, **context})


def create_agent_logger(
    agent_name: str,
    envelope_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> LoggerProtocol:
    """Create a logger for an agent.

    Args:
        agent_name: Name of the agent
        envelope_id: Current envelope ID
        request_id: Current request ID

    Returns:
        LoggerProtocol with agent context
    """
    context = {"agent": agent_name}
    if envelope_id:
        context["envelope_id"] = envelope_id
    if request_id:
        context["request_id"] = request_id
    return Logger(context=context)


def create_capability_logger(
    capability_name: str,
    agent_name: str,
    envelope_id: Optional[str] = None,
    request_id: Optional[str] = None,
    repo_path: Optional[str] = None,
) -> LoggerProtocol:
    """Create a logger for a capability.

    Args:
        capability_name: Name of capability
        agent_name: Agent name
        envelope_id: Current envelope ID
        request_id: Current request ID
        repo_path: Repository path

    Returns:
        LoggerProtocol with capability context
    """
    context = {
        "capability": capability_name,
        "agent": agent_name,
    }
    if envelope_id:
        context["envelope_id"] = envelope_id
    if request_id:
        context["request_id"] = request_id
    if repo_path:
        context["repo_path"] = repo_path
    return Logger(context=context)


def create_tool_logger(
    tool_name: str,
    agent_name: Optional[str] = None,
    request_id: Optional[str] = None,
) -> LoggerProtocol:
    """Create a logger for a tool.

    Args:
        tool_name: Name of the tool
        agent_name: Calling agent name
        request_id: Request ID

    Returns:
        LoggerProtocol with tool context
    """
    context = {"tool": tool_name}
    if agent_name:
        context["caller_agent"] = agent_name
    if request_id:
        context["request_id"] = request_id
    return Logger(context=context)


def get_current_logger() -> LoggerProtocol:
    """Get current logger for context-based access.

    Returns:
        LoggerProtocol - either the context-bound logger or a default.
    """
    logger = _current_logger.get()
    if logger is None:
        return Logger()
    return logger


def set_current_logger(logger: LoggerProtocol) -> None:
    """Set current logger for context-based access.

    Args:
        logger: LoggerProtocol to set as current
    """
    _current_logger.set(logger)


def get_component_logger(
    component: str,
    logger: Optional[LoggerProtocol] = None,
) -> LoggerProtocol:
    """Get a logger bound to a component name.

    This is the canonical way to initialize a logger in services and repositories.

    Args:
        component: Component name (e.g., "ChunkService", "EventRepository")
        logger: Optional injected logger. If None, uses context logger.

    Returns:
        LoggerProtocol bound to the component name
    """
    base_logger = logger or get_current_logger()
    return base_logger.bind(component=component)


def get_request_context() -> Optional[RequestContext]:
    """Get current request context.

    Returns:
        RequestContext if set, None otherwise.
    """
    return _request_context.get()


def set_request_context(ctx: RequestContext) -> None:
    """Set request context for current async context.

    Args:
        ctx: RequestContext to set
    """
    _request_context.set(ctx)


@contextmanager
def request_scope(
    ctx: RequestContext,
    logger: LoggerProtocol,
) -> Generator[RequestContext, None, None]:
    """Context manager for request scope.

    Sets both the request context and current logger for the duration
    of the scope, then restores the previous values on exit.

    Args:
        ctx: RequestContext for the request
        logger: Logger bound to the request context

    Yields:
        The RequestContext for use within the scope
    """
    # Save current values
    token_ctx = _request_context.set(ctx)
    token_log = _current_logger.set(logger)

    try:
        yield ctx
    finally:
        # Restore previous values
        _request_context.reset(token_ctx)
        _current_logger.reset(token_log)


__all__ = [
    # Configuration
    "configure_logging",
    # Logger creation
    "create_logger",
    "create_agent_logger",
    "create_capability_logger",
    "create_tool_logger",
    "get_component_logger",
    # Types
    "Logger",
    # Context
    "get_current_logger",
    "set_current_logger",
    "get_request_context",
    "set_request_context",
    "request_scope",
    # Internal context vars (for extensions)
    "_current_logger",
    "_request_context",
]
