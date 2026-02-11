"""Thin OpenTelemetry init — configure SDK, expose global adapter.

Replaces the 576-LOC over-engineered adapter with standard OTEL SDK usage.
The adapter provides start_span() for manual instrumentation and a global
singleton pattern for bootstrap integration.
"""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

try:
    from opentelemetry import trace
    from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


class OpenTelemetryAdapter:
    """Thin wrapper around OTEL tracer for span management."""

    def __init__(self, tracer: Optional[Any] = None):
        self._tracer = tracer
        self._enabled = OTEL_AVAILABLE and tracer is not None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: Optional[Any] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Optional[Any]]:
        """Start a span as a context manager."""
        if not self._enabled:
            yield None
            return

        span_kind = kind if kind is not None else SpanKind.INTERNAL
        span = self._tracer.start_span(name, kind=span_kind)
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v if isinstance(v, (int, float, bool, str)) else str(v))
        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
        finally:
            span.end()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_global_adapter: Optional[OpenTelemetryAdapter] = None


def get_global_otel_adapter() -> Optional[OpenTelemetryAdapter]:
    """Get the global adapter (set by init_global_otel)."""
    return _global_adapter


def set_global_otel_adapter(adapter: OpenTelemetryAdapter) -> None:
    """Override global adapter (useful for testing)."""
    global _global_adapter
    _global_adapter = adapter


def init_global_otel(
    service_name: str = "jeeves",
    service_version: str = "1.0.0",
    exporter: Optional[Any] = None,
) -> Optional[OpenTelemetryAdapter]:
    """Initialize the global OTEL adapter with a TracerProvider."""
    if not OTEL_AVAILABLE:
        return None

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: service_version,
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter or ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer(service_name, service_version)
    adapter = OpenTelemetryAdapter(tracer)
    set_global_otel_adapter(adapter)
    return adapter


def create_tracer(
    service_name: str = "jeeves",
    service_version: str = "1.0.0",
    exporter: Optional[Any] = None,
) -> Optional[Any]:
    """Create a standalone OTEL tracer (no global side-effects)."""
    if not OTEL_AVAILABLE:
        return None

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: service_version,
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter or ConsoleSpanExporter()))
    return provider.get_tracer(service_name, service_version)
