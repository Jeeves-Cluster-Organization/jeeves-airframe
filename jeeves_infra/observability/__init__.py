"""Observability Module.

Provides OpenTelemetry integration for distributed tracing and metrics.

Components:
- OpenTelemetryAdapter: EventEmitter adapter that exports to OpenTelemetry
- TracingMiddleware: Middleware for adding trace context to requests
- MetricsCollector: Metrics collection and export

Constitutional Reference: Infrastructure layer (avionics)
"""

from jeeves_infra.observability.otel_adapter import (
    OpenTelemetryAdapter,
    TracingContext,
    create_tracer,
    get_current_span,
    inject_trace_context,
    extract_trace_context,
    init_global_otel,
    get_global_otel_adapter,
    set_global_otel_adapter,
)
from jeeves_infra.observability.tracing_middleware import (
    TracingMiddleware,
    trace_function,
)

__all__ = [
    "OpenTelemetryAdapter",
    "TracingContext",
    "TracingMiddleware",
    "create_tracer",
    "get_current_span",
    "inject_trace_context",
    "extract_trace_context",
    "trace_function",
    "init_global_otel",
    "get_global_otel_adapter",
    "set_global_otel_adapter",
]
