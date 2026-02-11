"""Observability Module — thin OpenTelemetry integration."""

from jeeves_infra.observability.otel_adapter import (
    OpenTelemetryAdapter,
    create_tracer,
    init_global_otel,
    get_global_otel_adapter,
    set_global_otel_adapter,
)

__all__ = [
    "OpenTelemetryAdapter",
    "create_tracer",
    "init_global_otel",
    "get_global_otel_adapter",
    "set_global_otel_adapter",
]
