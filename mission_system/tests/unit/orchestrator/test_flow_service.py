"""Unit tests for FlowServicer.

Clean, modern async/await tests using mocked dependencies.
All external dependencies (gRPC, database, capability servicer) are mocked - no gRPC server required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

# Import the servicer (will be gated by _GRPC_AVAILABLE)
from mission_system.orchestrator import flow_service


# Skip all tests if gRPC not available
pytestmark = pytest.mark.skipif(
    not flow_service._GRPC_AVAILABLE,
    reason="gRPC not available"
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.bind.return_value = logger
    return logger


@pytest.fixture
def mock_db():
    """Mock DatabaseClientProtocol."""
    db = AsyncMock()
    db.fetch_one = AsyncMock()
    db.fetch_all = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_capability_servicer():
    """Mock CapabilityServicerProtocol."""
    servicer = MagicMock()
    # process_request returns an async generator
    async def mock_process_request(user_id, session_id, message, context):
        # Yield some mock events
        event1 = MagicMock()
        event1.type = 1
        event1.session_id = session_id or str(uuid4())
        yield event1

        event2 = MagicMock()
        event2.type = 2
        event2.session_id = event1.session_id
        yield event2

    servicer.process_request = mock_process_request
    return servicer


@pytest.fixture
def mock_grpc_context():
    """Mock grpc.aio.ServicerContext."""
    context = AsyncMock()
    context.abort = AsyncMock()
    return context


@pytest.fixture
def flow_servicer(mock_db, mock_capability_servicer, mock_logger):
    """FlowServicer instance with mocked dependencies."""
    return flow_service.FlowServicer(
        db=mock_db,
        capability_servicer=mock_capability_servicer,
        logger=mock_logger
    )


# =============================================================================
# STARTFLOW TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_start_flow_success(flow_servicer, mock_capability_servicer, mock_grpc_context):
    """Test successful flow start with event streaming."""
    request = MagicMock()
    request.user_id = "user123"
    request.session_id = "session-456"
    request.message = "Test message"
    request.context = None

    # Collect events from the generator
    events = []
    async for event in flow_servicer.StartFlow(request, mock_grpc_context):
        events.append(event)

    # Verify events were yielded
    assert len(events) == 2
    assert events[0].session_id == "session-456"
    assert events[1].session_id == "session-456"

    # Verify logger was called
    flow_servicer._logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_start_flow_with_new_session(flow_servicer, mock_grpc_context):
    """Test flow start creates new session when session_id is None."""
    request = MagicMock()
    request.user_id = "user123"
    request.session_id = None  # No session ID
    request.message = "Test message"
    request.context = None

    # Collect events
    events = []
    async for event in flow_servicer.StartFlow(request, mock_grpc_context):
        events.append(event)

    # Verify new session was created (events have a session_id)
    assert len(events) == 2
    assert events[0].session_id is not None
    assert events[1].session_id == events[0].session_id


@pytest.mark.asyncio
async def test_start_flow_delegates_to_servicer(flow_servicer, mock_grpc_context, monkeypatch):
    """Test that StartFlow properly delegates to capability servicer."""
    request = MagicMock()
    request.user_id = "user999"
    request.session_id = "session-999"
    request.message = "Complex query"
    request.context = {"key": "value"}

    # Track calls to process_request
    call_tracker = []

    async def track_process_request(user_id, session_id, message, context):
        call_tracker.append({
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "context": context
        })
        yield MagicMock()

    # Replace the servicer's process_request
    flow_servicer._servicer.process_request = track_process_request

    # Execute
    events = [e async for e in flow_servicer.StartFlow(request, mock_grpc_context)]

    # Verify delegation happened with correct parameters
    assert len(call_tracker) == 1
    assert call_tracker[0]["user_id"] == "user999"
    assert call_tracker[0]["session_id"] == "session-999"
    assert call_tracker[0]["message"] == "Complex query"
    assert call_tracker[0]["context"] == {"key": "value"}


# =============================================================================
# HELPER METHOD TESTS
# =============================================================================


def test_make_event(flow_servicer):
    """Test _make_event creates FlowEvent correctly."""
    event = flow_servicer._make_event(
        event_type=1,
        request_id="req-123",
        session_id="session-456",
        payload={"status": "success", "data": "test"}
    )

    # Verify event structure
    assert event.type == 1
    assert event.request_id == "req-123"
    assert event.session_id == "session-456"
    assert b'"status"' in event.payload
    assert b'"success"' in event.payload
    assert event.timestamp_ms > 0
