"""OpenTelemetry Adapter for Event Emitter.

Provides OpenTelemetry tracing integration that plugs into the existing
EventEmitter infrastructure. This adapter:

1. Creates spans for agent/tool executions
2. Propagates trace context through the pipeline
3. Exports traces to configured backends (Jaeger, Zipkin, OTLP, etc.)

Usage:
    from avionics.observability import OpenTelemetryAdapter, create_tracer

    # Initialize
    tracer = create_tracer("jeeves-my-capability")
    otel_adapter = OpenTelemetryAdapter(tracer)

    # Use with EventEmitter
    event_emitter.add_subscriber(otel_adapter)

    # Or use directly
    with otel_adapter.start_span("agent.planner") as span:
        span.set_attribute("agent.name", "planner")
        # ... agent execution ...

Constitutional Reference: Avionics R1 (Adapter Pattern)
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional
import threading

from jeeves_infra.protocols import LoggerProtocol

# OpenTelemetry imports with graceful fallback
try:
    from opentelemetry import trace
    from opentelemetry.trace import (
        Tracer,
        Span,
        SpanKind,
        Status,
        StatusCode,
    )
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    Tracer = Any
    Span = Any
    SpanKind = Any
    Status = Any
    StatusCode = Any


@dataclass
class TracingContext:
    """Context for trace propagation across process boundaries.

    Used to propagate trace context through the Go/Python bridge
    and between services.
    """
    trace_id: str
    span_id: str
    trace_flags: int = 1
    trace_state: str = ""
    baggage: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON transport."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "trace_flags": self.trace_flags,
            "trace_state": self.trace_state,
            "baggage": self.baggage,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TracingContext":
        """Deserialize from JSON transport."""
        return cls(
            trace_id=data.get("trace_id", ""),
            span_id=data.get("span_id", ""),
            trace_flags=data.get("trace_flags", 1),
            trace_state=data.get("trace_state", ""),
            baggage=data.get("baggage", {}),
        )


def create_tracer(
    service_name: str = "jeeves",
    service_version: str = "1.0.0",
    exporter: Optional[Any] = None,
) -> Optional[Tracer]:
    """Create an OpenTelemetry tracer.

    Args:
        service_name: Name of the service for tracing
        service_version: Version of the service
        exporter: Optional SpanExporter (defaults to ConsoleSpanExporter)

    Returns:
        Configured Tracer or None if OpenTelemetry is not available
    """
    if not OTEL_AVAILABLE:
        return None

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: service_version,
    })

    provider = TracerProvider(resource=resource)

    # Configure exporter
    if exporter is None:
        exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name, service_version)


def get_current_span() -> Optional[Span]:
    """Get the current active span.

    Returns:
        Current span or None if not available
    """
    if not OTEL_AVAILABLE:
        return None
    return trace.get_current_span()


def inject_trace_context(carrier: Dict[str, str]) -> None:
    """Inject trace context into a carrier dict for propagation.

    Args:
        carrier: Dict to inject trace headers into
    """
    if not OTEL_AVAILABLE:
        return

    propagator = TraceContextTextMapPropagator()
    propagator.inject(carrier)


def extract_trace_context(carrier: Dict[str, str]) -> Optional[Any]:
    """Extract trace context from a carrier dict.

    Args:
        carrier: Dict containing trace headers

    Returns:
        Context object or None
    """
    if not OTEL_AVAILABLE:
        return None

    propagator = TraceContextTextMapPropagator()
    return propagator.extract(carrier)


class OpenTelemetryAdapter:
    """Adapter that bridges EventEmitter events to OpenTelemetry spans.

    This adapter subscribes to domain events and creates corresponding
    OpenTelemetry spans for distributed tracing.

    Event to Span Mapping:
    - agent_started -> Start span with agent.name attribute
    - agent_completed -> End span with status
    - tool_executed -> Child span under current agent
    - plan_created -> Span with plan metadata
    - critic_decision -> Span event with decision details

    Thread Safety:
    - Uses thread-local storage for span context
    - Safe for concurrent agent executions
    """

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        logger: Optional[LoggerProtocol] = None,
        service_name: str = "jeeves",
    ):
        """Initialize OpenTelemetry adapter.

        Args:
            tracer: OpenTelemetry tracer (creates one if not provided)
            logger: Optional logger for debugging
            service_name: Service name for tracer creation
        """
        self._tracer = tracer or create_tracer(service_name)
        self._logger = logger
        self._enabled = OTEL_AVAILABLE and self._tracer is not None

        # Thread-local storage for span stacks (supports nested spans)
        self._span_stacks: Dict[str, List[Span]] = {}
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        """Check if OpenTelemetry tracing is enabled."""
        return self._enabled

    @contextmanager
    def start_span(
        self,
        name: str,
        kind: Optional[Any] = None,
        attributes: Optional[Dict[str, Any]] = None,
        context_key: str = "default",
    ) -> Iterator[Optional[Span]]:
        """Start a new span as a context manager.

        Args:
            name: Span name (e.g., "agent.planner", "tool.grep_search")
            kind: SpanKind (defaults to INTERNAL)
            attributes: Initial span attributes
            context_key: Key for span stack (e.g., request_id)

        Yields:
            Span object or None if tracing disabled
        """
        if not self._enabled:
            yield None
            return

        span_kind = kind if kind is not None else SpanKind.INTERNAL

        # Get parent span from stack
        parent_span = self._get_current_span(context_key)

        # Start new span
        if parent_span:
            ctx = trace.set_span_in_context(parent_span)
            span = self._tracer.start_span(name, kind=span_kind, context=ctx)
        else:
            span = self._tracer.start_span(name, kind=span_kind)

        # Set initial attributes
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, str(value) if not isinstance(value, (int, float, bool)) else value)

        # Push to stack
        self._push_span(context_key, span)

        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
        finally:
            span.end()
            self._pop_span(context_key)

    def _push_span(self, context_key: str, span: Span) -> None:
        """Push a span onto the context stack."""
        with self._lock:
            if context_key not in self._span_stacks:
                self._span_stacks[context_key] = []
            self._span_stacks[context_key].append(span)

    def _pop_span(self, context_key: str) -> Optional[Span]:
        """Pop a span from the context stack."""
        with self._lock:
            if context_key in self._span_stacks and self._span_stacks[context_key]:
                return self._span_stacks[context_key].pop()
            return None

    def _get_current_span(self, context_key: str) -> Optional[Span]:
        """Get the current span for a context."""
        with self._lock:
            if context_key in self._span_stacks and self._span_stacks[context_key]:
                return self._span_stacks[context_key][-1]
            return None

    # =========================================================================
    # Event Handler Methods (for EventEmitter subscription)
    # =========================================================================

    async def on_agent_started(
        self,
        agent_name: str,
        request_id: str,
        stage_order: int = 0,
        **kwargs: Any,
    ) -> Optional[str]:
        """Handle agent_started event - creates a new span.

        Returns:
            Span ID for correlation
        """
        if not self._enabled:
            return None

        span = self._tracer.start_span(
            f"agent.{agent_name}",
            kind=SpanKind.INTERNAL,
        )

        span.set_attribute("agent.name", agent_name)
        span.set_attribute("agent.stage_order", stage_order)
        span.set_attribute("request.id", request_id)

        for key, value in kwargs.items():
            if value is not None and isinstance(value, (str, int, float, bool)):
                span.set_attribute(f"agent.{key}", value)

        self._push_span(request_id, span)

        if self._logger:
            self._logger.debug(
                "otel_span_started",
                span_name=f"agent.{agent_name}",
                request_id=request_id,
            )

        return span.get_span_context().span_id.to_bytes(8, "big").hex()

    async def on_agent_completed(
        self,
        agent_name: str,
        request_id: str,
        status: str = "success",
        error: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Handle agent_completed event - ends the span."""
        if not self._enabled:
            return

        span = self._pop_span(request_id)
        if span:
            if status == "success":
                span.set_status(Status(StatusCode.OK))
            elif status == "error":
                span.set_status(Status(StatusCode.ERROR, error or "Unknown error"))
                if error:
                    span.set_attribute("error.message", error)
            else:
                span.set_attribute("agent.status", status)

            for key, value in kwargs.items():
                if value is not None and isinstance(value, (str, int, float, bool)):
                    span.set_attribute(f"agent.result.{key}", value)

            span.end()

            if self._logger:
                self._logger.debug(
                    "otel_span_ended",
                    span_name=f"agent.{agent_name}",
                    request_id=request_id,
                    status=status,
                )

    async def on_tool_executed(
        self,
        tool_name: str,
        request_id: str,
        status: str = "success",
        execution_time_ms: Optional[int] = None,
        error: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool_executed event - creates a child span."""
        if not self._enabled:
            return

        parent_span = self._get_current_span(request_id)

        with self.start_span(
            f"tool.{tool_name}",
            kind=SpanKind.INTERNAL,
            attributes={
                "tool.name": tool_name,
                "tool.status": status,
                "tool.execution_time_ms": execution_time_ms,
            },
            context_key=f"{request_id}_tool",
        ) as span:
            if span:
                if status == "error" and error:
                    span.set_status(Status(StatusCode.ERROR, error))
                    span.set_attribute("error.message", error)
                else:
                    span.set_status(Status(StatusCode.OK))

    async def on_llm_call(
        self,
        request_id: str,
        provider: str,
        model: str,
        agent_name: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0,
        cost_usd: float = 0,
        **kwargs: Any,
    ) -> None:
        """Handle LLM call event - creates a child span."""
        if not self._enabled:
            return

        with self.start_span(
            f"llm.{provider}",
            kind=SpanKind.CLIENT,
            attributes={
                "llm.provider": provider,
                "llm.model": model,
                "llm.agent": agent_name,
                "llm.tokens.input": tokens_in,
                "llm.tokens.output": tokens_out,
                "llm.latency_ms": latency_ms,
                "llm.cost_usd": cost_usd,
            },
            context_key=f"{request_id}_llm",
        ):
            pass  # Span auto-ends

    def record_event(
        self,
        name: str,
        request_id: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an event on the current span.

        Args:
            name: Event name
            request_id: Request ID for context lookup
            attributes: Event attributes
        """
        if not self._enabled:
            return

        span = self._get_current_span(request_id)
        if span:
            span.add_event(name, attributes=attributes or {})

    def set_attribute(
        self,
        key: str,
        value: Any,
        request_id: str,
    ) -> None:
        """Set an attribute on the current span.

        Args:
            key: Attribute key
            value: Attribute value
            request_id: Request ID for context lookup
        """
        if not self._enabled:
            return

        span = self._get_current_span(request_id)
        if span and value is not None:
            if isinstance(value, (str, int, float, bool)):
                span.set_attribute(key, value)
            else:
                span.set_attribute(key, str(value))

    def get_trace_context(self, request_id: str) -> Optional[TracingContext]:
        """Get the current trace context for propagation.

        Args:
            request_id: Request ID for context lookup

        Returns:
            TracingContext for propagation or None
        """
        if not self._enabled:
            return None

        span = self._get_current_span(request_id)
        if not span:
            return None

        ctx = span.get_span_context()
        return TracingContext(
            trace_id=format(ctx.trace_id, "032x"),
            span_id=format(ctx.span_id, "016x"),
            trace_flags=ctx.trace_flags,
            trace_state=str(ctx.trace_state) if ctx.trace_state else "",
        )

    def cleanup_context(self, request_id: str) -> None:
        """Clean up span stack for a completed request.

        Args:
            request_id: Request ID to clean up
        """
        with self._lock:
            # Clean up main stack
            if request_id in self._span_stacks:
                # End any remaining spans
                for span in self._span_stacks[request_id]:
                    span.end()
                del self._span_stacks[request_id]

            # Clean up related stacks (tool, llm)
            for suffix in ["_tool", "_llm"]:
                key = f"{request_id}{suffix}"
                if key in self._span_stacks:
                    for span in self._span_stacks[key]:
                        span.end()
                    del self._span_stacks[key]


# Singleton instance for convenience
_global_adapter: Optional[OpenTelemetryAdapter] = None


def get_global_otel_adapter() -> Optional[OpenTelemetryAdapter]:
    """Get the global OpenTelemetry adapter.

    Returns:
        Global adapter or None if not initialized
    """
    return _global_adapter


def set_global_otel_adapter(adapter: OpenTelemetryAdapter) -> None:
    """Set the global OpenTelemetry adapter.

    Args:
        adapter: Adapter instance to use globally
    """
    global _global_adapter
    _global_adapter = adapter


def init_global_otel(
    service_name: str = "jeeves",
    service_version: str = "1.0.0",
    exporter: Optional[Any] = None,
) -> Optional[OpenTelemetryAdapter]:
    """Initialize global OpenTelemetry adapter.

    Convenience function for quick setup.

    Args:
        service_name: Service name for tracing
        service_version: Service version
        exporter: Optional span exporter

    Returns:
        Initialized adapter or None if OTEL not available
    """
    if not OTEL_AVAILABLE:
        return None

    tracer = create_tracer(service_name, service_version, exporter)
    adapter = OpenTelemetryAdapter(tracer)
    set_global_otel_adapter(adapter)
    return adapter
