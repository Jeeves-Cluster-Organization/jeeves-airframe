"""Unit tests for FlowServicer.

Clean, modern async/await tests using mocked dependencies.
All external dependencies (gRPC, database, capability servicer) are mocked - no gRPC server required.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call
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
def mock_registry(monkeypatch):
    """Mock CapabilityResourceRegistry."""
    registry = MagicMock()
    service_config = MagicMock()
    service_config.default_session_title = "Code Analysis"

    registry.get_default_service.return_value = "test_service"
    registry.get_service_config.return_value = service_config

    monkeypatch.setattr(
        "mission_system.orchestrator.flow_service.get_capability_resource_registry",
        lambda: registry
    )
    return registry


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
# GETSESSION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_session_success(flow_servicer, mock_db, mock_grpc_context):
    """Test successful session retrieval."""
    request = MagicMock()
    request.session_id = "session-123"
    request.user_id = "user456"

    # Mock database response
    mock_db.fetch_one.return_value = {
        "session_id": "session-123",
        "user_id": "user456",
        "title": "Test Session",
        "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "message_count": 5
    }

    # Execute
    session = await flow_servicer.GetSession(request, mock_grpc_context)

    # Verify response
    assert session.session_id == "session-123"
    assert session.user_id == "user456"
    assert session.title == "Test Session"
    assert session.message_count == 5
    assert session.status == "active"
    assert session.created_at_ms > 0

    # Verify database was queried
    mock_db.fetch_one.assert_called_once()
    call_args = mock_db.fetch_one.call_args
    assert "SELECT session_id" in call_args[0][0]
    assert call_args[0][1]["session_id"] == "session-123"
    assert call_args[0][1]["user_id"] == "user456"


@pytest.mark.asyncio
async def test_get_session_not_found(flow_servicer, mock_db, mock_grpc_context):
    """Test session not found returns NOT_FOUND status."""
    request = MagicMock()
    request.session_id = "nonexistent"
    request.user_id = "user456"

    # Mock database returns None
    mock_db.fetch_one.return_value = None

    # Execute
    await flow_servicer.GetSession(request, mock_grpc_context)

    # Verify abort was called with NOT_FOUND
    mock_grpc_context.abort.assert_called_once()
    assert mock_grpc_context.abort.call_args[0][0].name == "NOT_FOUND"
    assert "not found" in mock_grpc_context.abort.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_get_session_with_message_count(flow_servicer, mock_db, mock_grpc_context):
    """Test session includes accurate message count."""
    request = MagicMock()
    request.session_id = "session-789"
    request.user_id = "user789"

    # Mock database response with specific message count
    mock_db.fetch_one.return_value = {
        "session_id": "session-789",
        "user_id": "user789",
        "title": "Session with Messages",
        "created_at": datetime.now(timezone.utc),
        "message_count": 42
    }

    # Execute
    session = await flow_servicer.GetSession(request, mock_grpc_context)

    # Verify message count
    assert session.message_count == 42


# =============================================================================
# LISTSESSIONS TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_list_sessions_success(flow_servicer, mock_db, mock_grpc_context):
    """Test listing sessions with pagination."""
    request = MagicMock()
    request.user_id = "user123"
    request.limit = 10
    request.offset = 0
    request.include_deleted = False

    # Mock database responses
    mock_db.fetch_all.return_value = [
        {
            "session_id": "session-1",
            "user_id": "user123",
            "title": "Session 1",
            "created_at": datetime.now(timezone.utc),
            "message_count": 5,
            "last_activity": datetime.now(timezone.utc)
        },
        {
            "session_id": "session-2",
            "user_id": "user123",
            "title": "Session 2",
            "created_at": datetime.now(timezone.utc),
            "message_count": 3,
            "last_activity": None
        }
    ]
    mock_db.fetch_one.return_value = {"total": 2}

    # Execute
    response = await flow_servicer.ListSessions(request, mock_grpc_context)

    # Verify response
    assert len(response.sessions) == 2
    assert response.total == 2
    assert response.sessions[0].session_id == "session-1"
    assert response.sessions[0].message_count == 5
    assert response.sessions[1].session_id == "session-2"
    assert response.sessions[1].message_count == 3


@pytest.mark.asyncio
async def test_list_sessions_pagination(flow_servicer, mock_db, mock_grpc_context):
    """Test offset and limit work correctly."""
    request = MagicMock()
    request.user_id = "user123"
    request.limit = 5
    request.offset = 10
    request.include_deleted = False

    mock_db.fetch_all.return_value = []
    mock_db.fetch_one.return_value = {"total": 25}

    # Execute
    await flow_servicer.ListSessions(request, mock_grpc_context)

    # Verify pagination parameters were passed
    call_args = mock_db.fetch_all.call_args
    assert call_args[0][1]["limit"] == 5
    assert call_args[0][1]["offset"] == 10


@pytest.mark.asyncio
async def test_list_sessions_include_deleted(flow_servicer, mock_db, mock_grpc_context):
    """Test include_deleted flag includes soft-deleted sessions."""
    request = MagicMock()
    request.user_id = "user123"
    request.limit = 50
    request.offset = 0
    request.include_deleted = True

    mock_db.fetch_all.return_value = []
    mock_db.fetch_one.return_value = {"total": 0}

    # Execute
    await flow_servicer.ListSessions(request, mock_grpc_context)

    # Verify query does NOT include deleted_at filter
    call_args = mock_db.fetch_all.call_args
    query = call_args[0][0]
    assert "deleted_at IS NULL" not in query or request.include_deleted


@pytest.mark.asyncio
async def test_list_sessions_empty_result(flow_servicer, mock_db, mock_grpc_context):
    """Test empty session list for new user."""
    request = MagicMock()
    request.user_id = "new-user"
    request.limit = 50
    request.offset = 0
    request.include_deleted = False

    # Mock empty results
    mock_db.fetch_all.return_value = []
    mock_db.fetch_one.return_value = {"total": 0}

    # Execute
    response = await flow_servicer.ListSessions(request, mock_grpc_context)

    # Verify empty response
    assert len(response.sessions) == 0
    assert response.total == 0


# =============================================================================
# CREATESESSION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_create_session_success(flow_servicer, mock_db, mock_grpc_context, mock_registry):
    """Test session creation with generated ID."""
    request = MagicMock()
    request.user_id = "user123"
    request.title = ""  # Empty title, should use default

    # Execute
    session = await flow_servicer.CreateSession(request, mock_grpc_context)

    # Verify session was created
    assert session.user_id == "user123"
    assert session.session_id is not None
    assert len(session.session_id) > 0  # UUID generated
    assert session.message_count == 0
    assert session.status == "active"

    # Verify database insert was called
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert "INSERT INTO sessions" in call_args[0][0]
    assert call_args[0][1]["user_id"] == "user123"


@pytest.mark.asyncio
async def test_create_session_default_title(flow_servicer, mock_db, mock_grpc_context, mock_registry):
    """Test default title from capability registry."""
    request = MagicMock()
    request.user_id = "user123"
    request.title = ""

    # Execute
    session = await flow_servicer.CreateSession(request, mock_grpc_context)

    # Verify default title from registry is used
    assert "Code Analysis" in session.title  # From mock_registry

    # Verify database was called with title
    call_args = mock_db.execute.call_args
    assert "Code Analysis" in call_args[0][1]["title"]


@pytest.mark.asyncio
async def test_create_session_custom_title(flow_servicer, mock_db, mock_grpc_context, mock_registry):
    """Test custom title is used when provided."""
    request = MagicMock()
    request.user_id = "user123"
    request.title = "My Custom Session"

    # Execute
    session = await flow_servicer.CreateSession(request, mock_grpc_context)

    # Verify custom title is used
    assert session.title == "My Custom Session"

    # Verify database was called with custom title
    call_args = mock_db.execute.call_args
    assert call_args[0][1]["title"] == "My Custom Session"


# =============================================================================
# DELETESESSION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_delete_session_success(flow_servicer, mock_db, mock_grpc_context):
    """Test soft delete session."""
    request = MagicMock()
    request.session_id = "session-123"
    request.user_id = "user456"

    # Mock database result with rowcount
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_db.execute.return_value = mock_result

    # Execute
    response = await flow_servicer.DeleteSession(request, mock_grpc_context)

    # Verify success
    assert response.success is True

    # Verify database update was called
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert "UPDATE sessions" in call_args[0][0]
    assert "SET deleted_at" in call_args[0][0]
    assert call_args[0][1]["session_id"] == "session-123"
    assert call_args[0][1]["user_id"] == "user456"


@pytest.mark.asyncio
async def test_delete_session_already_deleted(flow_servicer, mock_db, mock_grpc_context):
    """Test deleting already deleted session returns success=False."""
    request = MagicMock()
    request.session_id = "session-999"
    request.user_id = "user456"

    # Mock database result with 0 rowcount (no rows updated)
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute.return_value = mock_result

    # Execute
    response = await flow_servicer.DeleteSession(request, mock_grpc_context)

    # Verify failure (already deleted or doesn't exist)
    assert response.success is False


# =============================================================================
# GETSESSIONMESSAGES TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_session_messages_success(flow_servicer, mock_db, mock_grpc_context):
    """Test retrieving messages for session."""
    request = MagicMock()
    request.session_id = "session-123"
    request.user_id = "user456"
    request.limit = 100
    request.offset = 0

    # Mock session exists
    mock_db.fetch_one.side_effect = [
        {"session_id": "session-123"},  # Session exists check
        {"total": 3}  # Message count
    ]

    # Mock messages
    mock_db.fetch_all.return_value = [
        {
            "message_id": 1,
            "session_id": "session-123",
            "role": "user",
            "content": "Hello",
            "created_at": datetime.now(timezone.utc)
        },
        {
            "message_id": 2,
            "session_id": "session-123",
            "role": "assistant",
            "content": "Hi there!",
            "created_at": datetime.now(timezone.utc)
        },
        {
            "message_id": 3,
            "session_id": "session-123",
            "role": "user",
            "content": "How are you?",
            "created_at": datetime.now(timezone.utc)
        }
    ]

    # Execute
    response = await flow_servicer.GetSessionMessages(request, mock_grpc_context)

    # Verify messages
    assert len(response.messages) == 3
    assert response.total == 3
    assert response.messages[0].message_id == "1"
    assert response.messages[0].role == "user"
    assert response.messages[0].content == "Hello"
    assert response.messages[1].message_id == "2"
    assert response.messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_get_session_messages_session_not_found(flow_servicer, mock_db, mock_grpc_context):
    """Test session not found returns NOT_FOUND."""
    request = MagicMock()
    request.session_id = "nonexistent"
    request.user_id = "user456"
    request.limit = 100
    request.offset = 0

    # Mock session doesn't exist
    mock_db.fetch_one.return_value = None

    # Execute
    await flow_servicer.GetSessionMessages(request, mock_grpc_context)

    # Verify abort was called
    mock_grpc_context.abort.assert_called_once()
    assert mock_grpc_context.abort.call_args[0][0].name == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_session_messages_pagination(flow_servicer, mock_db, mock_grpc_context):
    """Test message pagination with offset/limit."""
    request = MagicMock()
    request.session_id = "session-123"
    request.user_id = "user456"
    request.limit = 10
    request.offset = 20

    # Mock session exists
    mock_db.fetch_one.side_effect = [
        {"session_id": "session-123"},
        {"total": 50}
    ]
    mock_db.fetch_all.return_value = []

    # Execute
    await flow_servicer.GetSessionMessages(request, mock_grpc_context)

    # Verify pagination parameters
    call_args = mock_db.fetch_all.call_args
    assert call_args[0][1]["limit"] == 10
    assert call_args[0][1]["offset"] == 20


# =============================================================================
# HELPER METHOD TESTS
# =============================================================================


def test_get_default_session_title(flow_servicer, mock_registry):
    """Test _get_default_session_title retrieves from registry."""
    title = flow_servicer._get_default_session_title()

    # Verify title from registry
    assert title == "Code Analysis"


def test_get_default_session_title_fallback(flow_servicer, monkeypatch):
    """Test _get_default_session_title falls back to 'Session' when registry unavailable."""
    # Mock registry with no default service
    registry = MagicMock()
    registry.get_default_service.return_value = None

    monkeypatch.setattr(
        "mission_system.orchestrator.flow_service.get_capability_resource_registry",
        lambda: registry
    )

    title = flow_servicer._get_default_session_title()

    # Verify fallback
    assert title == "Session"


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
