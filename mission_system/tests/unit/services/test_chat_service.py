"""Unit tests for ChatService.

PostgreSQL-only as of 2025-11-27 (Amendment V).
Tests use pg_test_db fixture from conftest.py.
"""

import pytest
from datetime import datetime, timezone
from mission_system.services.chat_service import ChatService

# Requires PostgreSQL database
pytestmark = pytest.mark.requires_postgres


class TestChatService:
    """Test suite for ChatService."""

    @pytest.fixture
    def chat_service(self, pg_test_db):
        """Create a ChatService instance."""
        return ChatService(pg_test_db, event_manager=None)

    @pytest.mark.asyncio
    async def test_create_session(self, chat_service):
        """Test creating a new chat session."""
        session = await chat_service.create_session(
            user_id="test-user",
            title="Test Session"
        )

        assert session["user_id"] == "test-user"
        assert session["title"] == "Test Session"
        assert session["message_count"] == 0
        assert "session_id" in session
        assert "created_at" in session

    @pytest.mark.asyncio
    async def test_list_sessions(self, chat_service):
        """Test listing sessions for a user."""
        # Create multiple sessions
        await chat_service.create_session(user_id="test-user", title="Session 1")
        await chat_service.create_session(user_id="test-user", title="Session 2")
        await chat_service.create_session(user_id="other-user", title="Session 3")

        # List sessions for test-user
        sessions = await chat_service.list_sessions(user_id="test-user")

        assert len(sessions) == 2
        assert all(s["user_id"] == "test-user" for s in sessions)

    @pytest.mark.asyncio
    async def test_delete_session_soft(self, chat_service):
        """Test soft deleting a session."""
        session = await chat_service.create_session(
            user_id="test-user",
            title="To Delete"
        )

        # Soft delete
        result = await chat_service.delete_session(
            session_id=session["session_id"],
            user_id="test-user",
            soft=True
        )

        assert result["deleted"] is True

        # Should not appear in normal list
        sessions = await chat_service.list_sessions(user_id="test-user")
        assert len(sessions) == 0

        # Should appear when including deleted
        sessions = await chat_service.list_sessions(
            user_id="test-user",
            include_deleted=True
        )
        assert len(sessions) == 1
        assert sessions[0]["deleted_at"] is not None

    @pytest.mark.asyncio
    async def test_update_session(self, chat_service):
        """Test updating a session."""
        session = await chat_service.create_session(
            user_id="test-user",
            title="Old Title"
        )

        # Update title
        updated = await chat_service.update_session(
            session_id=session["session_id"],
            user_id="test-user",
            updates={"title": "New Title"}
        )

        assert updated["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_list_messages(self, chat_service, pg_test_db):
        """Test listing messages in a session."""
        session = await chat_service.create_session(user_id="test-user")

        # Insert test messages directly
        await pg_test_db.insert("messages", {
            "session_id": session["session_id"],
            "role": "user",
            "content": "Hello",
            "created_at": datetime.now(timezone.utc)
        })
        await pg_test_db.insert("messages", {
            "session_id": session["session_id"],
            "role": "assistant",
            "content": "Hi there!",
            "created_at": datetime.now(timezone.utc)
        })

        # List messages
        messages = await chat_service.list_messages(
            session_id=session["session_id"],
            user_id="test-user"
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_delete_message(self, chat_service, pg_test_db):
        """Test deleting a message."""
        session = await chat_service.create_session(user_id="test-user")
        session_id = str(session["session_id"])  # Ensure string for SQL

        # Insert test message and get ID using RETURNING (PostgreSQL feature)
        # commit=True required for INSERT...RETURNING per HANDOFF.md Fix #4
        insert_result = await pg_test_db.fetch_one(
            """
            INSERT INTO messages (session_id, role, content, created_at)
            VALUES (:session_id, :role, :content, :created_at)
            RETURNING message_id
            """,
            {
                "session_id": session_id,
                "role": "user",
                "content": "Test message for deletion",
                "created_at": datetime.now(timezone.utc)
            },
            commit=True
        )
        message_id = insert_result["message_id"]

        # Delete message
        result = await chat_service.delete_message(
            message_id=message_id,
            user_id="test-user",
            soft=True
        )

        assert result["deleted"] is True

        # Should not appear in normal list
        messages = await chat_service.list_messages(
            session_id=session_id,
            user_id="test-user"
        )
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_export_session_json(self, chat_service, pg_test_db):
        """Test exporting a session to JSON."""
        session = await chat_service.create_session(
            user_id="test-user",
            title="Export Test"
        )

        # Insert test messages
        await pg_test_db.insert("messages", {
            "session_id": session["session_id"],
            "role": "user",
            "content": "Test",
            "created_at": datetime.now(timezone.utc)
        })

        # Export
        export_data = await chat_service.export_session(
            session_id=session["session_id"],
            user_id="test-user",
            format="json"
        )

        import json
        data = json.loads(export_data)

        assert "session" in data
        assert "messages" in data
        assert data["session"]["title"] == "Export Test"
        assert len(data["messages"]) == 1
