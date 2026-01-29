"""Context propagation for logging and request tracing.

ADR-001 Decision 5: Context Propagation Design
This module provides ContextVars-based context propagation for:
- RequestContext: Immutable request context for tracing
- Current logger: Thread/async-safe logger access for tools

Usage:
    from avionics.logging.context import (
        request_scope,
        get_request_context,
        get_current_logger,
    )

    # At request entry point (e.g., API handler)
    ctx = RequestContext(request_id=str(uuid4()), capability="example", user_id="user-123")
    with request_scope(ctx, logger):
        # All code in this scope has access to context
        current_logger = get_current_logger()
        current_ctx = get_request_context()
"""

from contextlib import contextmanager
from typing import Generator, Iterator

import structlog

from jeeves_infra.protocols import LoggerProtocol

# Import base context functions from jeeves_infra.utils.logging
from jeeves_infra.utils.logging import (
    get_request_context,
    set_request_context,
    get_current_logger,
    set_current_logger,
    request_scope,
)


@contextmanager
def bind_logger_context(**kwargs) -> Generator[LoggerProtocol, None, None]:
    """Temporarily bind additional context to the current logger.

    Creates a new logger with additional bound context for the
    duration of the scope.

    Args:
        **kwargs: Context to bind to the logger

    Yields:
        Logger with additional bound context

    Usage:
        with bind_logger_context(step="validation"):
            get_current_logger().info("validating_input")
    """
    # Import the context var from shared logging
    from jeeves_infra.utils.logging import _current_logger

    current = get_current_logger()
    bound = current.bind(**kwargs)
    token = _current_logger.set(bound)

    try:
        yield bound
    finally:
        _current_logger.reset(token)


@contextmanager
def request_context(request_id: str, user_id: str, **extra_context) -> Iterator[None]:
    """Bind request context to all log messages within the context.

    This uses structlog's contextvars to propagate context through async calls.
    Backward-compatible function moved from jeeves_core_engine.agents.base.

    Args:
        request_id: Request ID for tracing
        user_id: User ID for the request
        **extra_context: Additional context to bind

    Yields:
        None

    Usage:
        with request_context("req-123", "user-456"):
            # All log messages in this scope will have request_id and user_id
            logger.info("processing_request")
    """
    token = structlog.contextvars.bind_contextvars(
        request_id=request_id,
        user_id=user_id,
        **extra_context
    )
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**token)


__all__ = [
    "get_request_context",
    "set_request_context",
    "get_current_logger",
    "set_current_logger",
    "request_scope",
    "bind_logger_context",
    "request_context",
]
