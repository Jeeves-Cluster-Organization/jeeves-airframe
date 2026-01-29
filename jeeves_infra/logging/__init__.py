"""Centralized Logging Infrastructure for Jeeves Runtime.

This module provides logging configuration with optional OTEL tracing support.
Base logging functionality comes from jeeves_infra.utils.logging.
Real OpenTelemetry tracing is provided by avionics.observability.

Constitutional Compliance:
- Avionics owns OTEL configuration flag
- Base logging utilities come from shared (L0)
- Real OTEL spans are managed by observability/otel_adapter.py
- Other layers only use injected LoggerProtocol

Usage:
    from avionics.logging import create_logger, configure_logging

    # At application startup (once)
    configure_logging(level="INFO", json_output=True, enable_otel=True)

    # Create logger for injection
    logger = create_logger("my_component", envelope_id="...")

    # Inject into services/agents
    service = MyService(logger=logger)
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, Optional, TYPE_CHECKING

from jeeves_infra.protocols import LoggerProtocol

# Import base logging from shared (L0)
from jeeves_infra.utils.logging import (
    Logger,
    configure_logging as _base_configure_logging,
    create_logger,
    create_agent_logger,
    create_capability_logger,
    create_tool_logger,
    get_component_logger,
    get_current_logger,
    set_current_logger,
    get_request_context,
    set_request_context,
    request_scope,
)

if TYPE_CHECKING:
    from jeeves_infra.feature_flags import FeatureFlags

# Context-aware state for OTEL enabled flag
_otel_enabled: ContextVar[bool] = ContextVar("otel_enabled", default=False)


def _get_otel_enabled() -> bool:
    """Get OTEL enabled state from context."""
    return _otel_enabled.get()


def _set_otel_enabled(value: bool) -> None:
    """Set OTEL enabled state in context."""
    _otel_enabled.set(value)


# =============================================================================
# Configuration with OTEL Support
# =============================================================================

def configure_logging(
    level: str = "INFO",
    *,
    json_output: bool = True,
    enable_otel: bool = False,
    component_levels: Optional[Dict[str, str]] = None,
) -> None:
    """Configure logging for the Jeeves runtime with OTEL support.

    This should be called ONCE at application startup.
    All subsequent logging uses the configuration set here.

    For actual OpenTelemetry tracing, use avionics.observability.

    Args:
        level: Default log level (DEBUG, INFO, WARNING, ERROR)
        json_output: If True, output JSON; if False, console format
        enable_otel: If True, enable OTEL span tracking via observability module
        component_levels: Override levels for specific components
    """
    _set_otel_enabled(enable_otel)

    # Delegate to base configuration
    _base_configure_logging(
        level=level,
        json_output=json_output,
        component_levels=component_levels,
    )


def configure_from_flags(flags: "FeatureFlags") -> None:
    """Configure logging from feature flags.

    Args:
        flags: FeatureFlags instance
    """
    configure_logging(
        level="DEBUG" if flags.enable_debug_logging else "INFO",
        json_output=True,
        enable_otel=flags.enable_tracing,
    )


def is_otel_enabled() -> bool:
    """Check if OTEL tracing is enabled.
    
    Returns:
        True if OTEL was enabled via configure_logging
    """
    return _get_otel_enabled()


# =============================================================================
# Exports
# =============================================================================

# Re-export from adapter module (ADR-001)
from jeeves_infra.logging.adapter import StructlogAdapter, create_structlog_adapter

# Re-export from context module (ADR-001)
from jeeves_infra.logging.context import (
    bind_logger_context,
    request_context,
)


__all__ = [
    # Configuration
    "configure_logging",
    "configure_from_flags",
    "is_otel_enabled",
    # Logger creation (re-exported from shared)
    "create_logger",
    "create_agent_logger",
    "create_capability_logger",
    "create_tool_logger",
    "get_component_logger",
    # Types
    "Logger",
    # ADR-001: Adapter
    "StructlogAdapter",
    "create_structlog_adapter",
    # Context (re-exported from shared)
    "get_request_context",
    "set_request_context",
    "get_current_logger",
    "set_current_logger",
    "request_scope",
    # ADR-001: Context extensions
    "bind_logger_context",
    "request_context",
]
