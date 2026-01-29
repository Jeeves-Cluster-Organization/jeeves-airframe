"""Tracing Middleware for automatic span creation.

Provides middleware and decorators for adding tracing to functions
and request handlers.

Usage:
    @trace_function("process_request")
    async def process_request(request):
        # Automatically traced
        ...

    # Or with middleware
    middleware = TracingMiddleware(otel_adapter)
    traced_handler = middleware.wrap(handler)

Constitutional Reference: Infrastructure R1 (Adapter Pattern)
"""

import functools
import time
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from contextlib import asynccontextmanager

from jeeves_infra.observability.otel_adapter import (
    OpenTelemetryAdapter,
    get_global_otel_adapter,
    OTEL_AVAILABLE,
)

if OTEL_AVAILABLE:
    from opentelemetry.trace import SpanKind

F = TypeVar("F", bound=Callable[..., Any])


class TracingMiddleware:
    """Middleware for adding tracing to request handlers.

    Wraps handlers to automatically create spans for each request.

    Example:
        middleware = TracingMiddleware(otel_adapter)

        @middleware.trace("handle_request")
        async def handle_request(envelope):
            ...

        # Or wrap existing handler
        traced = middleware.wrap(existing_handler, "handle_request")
    """

    def __init__(
        self,
        adapter: Optional[OpenTelemetryAdapter] = None,
        default_kind: Optional[Any] = None,
    ):
        """Initialize tracing middleware.

        Args:
            adapter: OpenTelemetry adapter (uses global if not provided)
            default_kind: Default SpanKind for created spans
        """
        self._adapter = adapter
        self._default_kind = default_kind if OTEL_AVAILABLE else None

    @property
    def adapter(self) -> Optional[OpenTelemetryAdapter]:
        """Get the adapter, falling back to global."""
        return self._adapter or get_global_otel_adapter()

    def trace(
        self,
        name: str,
        kind: Optional[Any] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Callable[[F], F]:
        """Decorator for tracing a function.

        Args:
            name: Span name
            kind: SpanKind for the span
            attributes: Static attributes to add to span

        Returns:
            Decorated function
        """
        def decorator(func: F) -> F:
            if asyncio_iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    adapter = self.adapter
                    if not adapter or not adapter.enabled:
                        return await func(*args, **kwargs)

                    # Extract request_id from kwargs or args
                    request_id = self._extract_request_id(args, kwargs)
                    span_kind = kind or self._default_kind

                    with adapter.start_span(
                        name,
                        kind=span_kind,
                        attributes=attributes,
                        context_key=request_id,
                    ) as span:
                        if span:
                            span.set_attribute("function.name", func.__name__)
                            span.set_attribute("function.module", func.__module__)

                        start_time = time.time()
                        try:
                            result = await func(*args, **kwargs)
                            if span:
                                span.set_attribute(
                                    "function.duration_ms",
                                    (time.time() - start_time) * 1000
                                )
                            return result
                        except Exception as e:
                            if span:
                                span.set_attribute("error.type", type(e).__name__)
                            raise

                return async_wrapper  # type: ignore
            else:
                @functools.wraps(func)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    adapter = self.adapter
                    if not adapter or not adapter.enabled:
                        return func(*args, **kwargs)

                    request_id = self._extract_request_id(args, kwargs)
                    span_kind = kind or self._default_kind

                    with adapter.start_span(
                        name,
                        kind=span_kind,
                        attributes=attributes,
                        context_key=request_id,
                    ) as span:
                        if span:
                            span.set_attribute("function.name", func.__name__)
                            span.set_attribute("function.module", func.__module__)

                        start_time = time.time()
                        try:
                            result = func(*args, **kwargs)
                            if span:
                                span.set_attribute(
                                    "function.duration_ms",
                                    (time.time() - start_time) * 1000
                                )
                            return result
                        except Exception as e:
                            if span:
                                span.set_attribute("error.type", type(e).__name__)
                            raise

                return sync_wrapper  # type: ignore

        return decorator

    def wrap(
        self,
        handler: Callable[..., Any],
        name: str,
        kind: Optional[Any] = None,
    ) -> Callable[..., Any]:
        """Wrap an existing handler with tracing.

        Args:
            handler: Handler function to wrap
            name: Span name
            kind: SpanKind for the span

        Returns:
            Wrapped handler
        """
        return self.trace(name, kind)(handler)

    def _extract_request_id(
        self,
        args: tuple,
        kwargs: Dict[str, Any],
    ) -> str:
        """Extract request_id from function arguments.

        Looks for request_id in kwargs, or tries to extract from
        common argument patterns (envelope, request, context).
        """
        # Check kwargs directly
        if "request_id" in kwargs:
            return str(kwargs["request_id"])

        if "envelope" in kwargs:
            envelope = kwargs["envelope"]
            if hasattr(envelope, "request_id"):
                return str(envelope.request_id)
            if hasattr(envelope, "envelope_id"):
                return str(envelope.envelope_id)

        # Check first positional arg
        if args:
            first_arg = args[0]
            if hasattr(first_arg, "request_id"):
                return str(first_arg.request_id)
            if hasattr(first_arg, "envelope_id"):
                return str(first_arg.envelope_id)

        return "default"


def asyncio_iscoroutinefunction(func: Any) -> bool:
    """Check if function is a coroutine function."""
    import asyncio
    return asyncio.iscoroutinefunction(func)


def trace_function(
    name: str,
    kind: Optional[Any] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """Decorator for tracing a function using the global adapter.

    Convenience function that uses TracingMiddleware with global adapter.

    Args:
        name: Span name
        kind: SpanKind for the span
        attributes: Static attributes to add to span

    Returns:
        Decorator function

    Example:
        @trace_function("process_data")
        async def process_data(data):
            ...
    """
    middleware = TracingMiddleware()
    return middleware.trace(name, kind, attributes)


@asynccontextmanager
async def trace_block(
    name: str,
    request_id: str = "default",
    attributes: Optional[Dict[str, Any]] = None,
):
    """Async context manager for tracing a code block.

    Args:
        name: Span name
        request_id: Request ID for context correlation
        attributes: Span attributes

    Example:
        async with trace_block("process_step", request_id=req_id):
            await do_something()
    """
    adapter = get_global_otel_adapter()
    if not adapter or not adapter.enabled:
        yield None
        return

    with adapter.start_span(
        name,
        attributes=attributes,
        context_key=request_id,
    ) as span:
        yield span


class SpanContextPropagator:
    """Helper for propagating trace context across boundaries.

    Used to propagate trace context through:
    - HTTP headers
    - Message queues
    - Go/Python bridge

    Example:
        # Sender side
        propagator = SpanContextPropagator(adapter)
        headers = propagator.inject(request_id)
        # Send headers with request...

        # Receiver side
        propagator.extract(headers, request_id)
        # Now spans will be children of the original trace
    """

    def __init__(self, adapter: Optional[OpenTelemetryAdapter] = None):
        """Initialize propagator.

        Args:
            adapter: OpenTelemetry adapter (uses global if not provided)
        """
        self._adapter = adapter

    @property
    def adapter(self) -> Optional[OpenTelemetryAdapter]:
        """Get the adapter, falling back to global."""
        return self._adapter or get_global_otel_adapter()

    def inject(self, request_id: str) -> Dict[str, str]:
        """Inject trace context into headers.

        Args:
            request_id: Request ID for context lookup

        Returns:
            Headers dict with trace context
        """
        headers: Dict[str, str] = {}

        adapter = self.adapter
        if adapter:
            trace_ctx = adapter.get_trace_context(request_id)
            if trace_ctx:
                # W3C Trace Context format
                headers["traceparent"] = (
                    f"00-{trace_ctx.trace_id}-{trace_ctx.span_id}-"
                    f"{trace_ctx.trace_flags:02x}"
                )
                if trace_ctx.trace_state:
                    headers["tracestate"] = trace_ctx.trace_state

        return headers

    def inject_to_envelope(
        self,
        envelope: Any,
        request_id: Optional[str] = None,
    ) -> None:
        """Inject trace context into a Envelope.

        Args:
            envelope: Envelope to inject into
            request_id: Request ID (defaults to envelope.request_id)
        """
        req_id = request_id or getattr(envelope, "request_id", "default")
        headers = self.inject(req_id)

        if headers:
            if not hasattr(envelope, "metadata"):
                envelope.metadata = {}
            envelope.metadata["trace_context"] = headers

    def extract_from_envelope(
        self,
        envelope: Any,
    ) -> Optional[Dict[str, str]]:
        """Extract trace context from a Envelope.

        Args:
            envelope: Envelope to extract from

        Returns:
            Trace context headers or None
        """
        if hasattr(envelope, "metadata") and envelope.metadata:
            return envelope.metadata.get("trace_context")
        return None
