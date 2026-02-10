"""OpenTelemetry tracing configuration for jeeves_infra."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

_tracer_provider: TracerProvider | None = None


def init_tracing(service_name: str, jaeger_endpoint: str = "jaeger:4317") -> None:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Service name for traces
        jaeger_endpoint: Jaeger OTLP endpoint (default: jaeger:4317)
    """
    global _tracer_provider

    # Create resource
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "4.0.0",
        DEPLOYMENT_ENVIRONMENT: "development",
    })

    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)

    # Add OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=jaeger_endpoint,
        insecure=True,  # Use TLS in production
    )
    _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set global tracer provider
    trace.set_tracer_provider(_tracer_provider)


def instrument_fastapi(app) -> None:
    """Instrument FastAPI app with OpenTelemetry.

    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor.instrument_app(app)


def instrument_grpc_client() -> None:
    """Instrument gRPC clients with OpenTelemetry."""
    GrpcInstrumentorClient().instrument()


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for the given name.

    Args:
        name: Tracer name (usually module path)

    Returns:
        OpenTelemetry tracer
    """
    return trace.get_tracer(name)


def shutdown_tracing() -> None:
    """Shutdown tracer provider and flush pending spans."""
    global _tracer_provider
    if _tracer_provider:
        _tracer_provider.shutdown()
