def test_root_imports():
    from airframe import AirframeClient, InferenceRequest, Message, EndpointSpec  # noqa: F401


def test_health_imports():
    from airframe import HealthProbe, HttpHealthProbe  # noqa: F401


def test_all_exports():
    """Verify all documented exports are available."""
    from airframe import (
        # Types
        InferenceRequest,
        InferenceResult,
        InferenceStreamEvent,
        Message,
        ToolSpec,
        AirframeError,
        ErrorCategory,
        StreamEventType,
        # Endpoints
        EndpointSpec,
        HealthState,
        CapacityHints,
        BackendKind,
        # Registry
        EndpointRegistry,
        StaticRegistry,
        # Client
        AirframeClient,
        # Health
        HealthProbe,
        HttpHealthProbe,
    )

    # Verify they are all classes/types
    assert InferenceRequest is not None
    assert HttpHealthProbe is not None
