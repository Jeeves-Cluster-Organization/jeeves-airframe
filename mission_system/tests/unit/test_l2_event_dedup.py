"""Unit tests for L2 event deduplication (v0.14 Phase 3).

Tests session-scoped event deduplication in EventEmitter.
Per CYCLIC_MIGRATION_PLAN.md Phase 3: L2 events deduplicated within session.

Constitutional Import Boundary Note:
- Mission system layer tests the jeeves_infra layer functionality
- Direct jeeves_infra imports are acceptable here for testing
- App layer tests must use mission_system.adapters instead
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

# Mission system tests jeeves_infra functionality - direct import acceptable
from jeeves_infra.memory.services.event_emitter import (
    EventEmitter,
    SessionDedupCache,
    get_global_dedup_cache,
    clear_global_dedup_cache
)

# Requires PostgreSQL database
pytestmark = pytest.mark.requires_postgres


class TestSessionDedupCache:
    """Tests for SessionDedupCache."""

    def test_is_duplicate_returns_false_for_new_event(self):
        """New events should not be flagged as duplicates."""
        cache = SessionDedupCache()

        result = cache.is_duplicate(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test task"}
        )

        assert result is False

    def test_is_duplicate_returns_true_after_mark_emitted(self):
        """Events marked as emitted should be flagged as duplicates."""
        cache = SessionDedupCache()

        # First, mark as emitted
        cache.mark_emitted(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test task"}
        )

        # Now check - should be duplicate
        result = cache.is_duplicate(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test task"}
        )

        assert result is True

    def test_different_sessions_are_independent(self):
        """Events in different sessions should not affect each other."""
        cache = SessionDedupCache()

        # Mark event in session 1
        cache.mark_emitted(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test task"}
        )

        # Check in session 2 - should NOT be duplicate
        result = cache.is_duplicate(
            session_id="session-2",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test task"}
        )

        assert result is False

    def test_different_payloads_are_not_duplicates(self):
        """Same event type but different payload should not be duplicate."""
        cache = SessionDedupCache()

        # Mark first event
        cache.mark_emitted(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_updated",
            payload={"changes": [{"field": "title", "old": "A", "new": "B"}]}
        )

        # Different payload - should NOT be duplicate
        result = cache.is_duplicate(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_updated",
            payload={"changes": [{"field": "title", "old": "B", "new": "C"}]}
        )

        assert result is False

    def test_no_session_id_cannot_deduplicate(self):
        """Without session_id, deduplication is disabled."""
        cache = SessionDedupCache()

        # Mark without session_id (no-op)
        cache.mark_emitted(
            session_id=None,
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={}
        )

        # Check without session_id
        result = cache.is_duplicate(
            session_id=None,
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={}
        )

        assert result is False

    def test_clear_session_removes_cache(self):
        """Clearing a session should remove its cache."""
        cache = SessionDedupCache()

        cache.mark_emitted(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={}
        )

        # Clear session
        cache.clear_session("session-1")

        # Should NOT be duplicate after clear
        result = cache.is_duplicate(
            session_id="session-1",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={}
        )

        assert result is False

    def test_clear_all_removes_all_caches(self):
        """Clearing all should remove all session caches."""
        cache = SessionDedupCache()

        # Add to multiple sessions
        for i in range(5):
            cache.mark_emitted(
                session_id=f"session-{i}",
                aggregate_type="task",
                aggregate_id="task-1",
                event_type="task_created",
                payload={}
            )

        assert cache.session_count == 5

        # Clear all
        cache.clear_all()

        assert cache.session_count == 0

    def test_max_size_eviction(self):
        """Cache should evict entries when max_size is reached."""
        cache = SessionDedupCache(max_size=5)

        # Add 10 entries (exceeds max_size of 5)
        for i in range(10):
            cache.mark_emitted(
                session_id="session-1",
                aggregate_type="task",
                aggregate_id=f"task-{i}",
                event_type="task_created",
                payload={}
            )

        # Cache size should be controlled
        assert cache.get_session_size("session-1") <= 5


class TestEventEmitterDeduplication:
    """Tests for EventEmitter with deduplication."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock event repository."""
        repo = MagicMock()
        repo.append = AsyncMock(return_value="event-123")
        return repo

    @pytest.fixture
    def mock_flags(self):
        """Mock feature flags to enable event sourcing."""
        mock_flags = MagicMock()
        mock_flags.is_enabled = MagicMock(return_value=True)
        return mock_flags

    @pytest.fixture
    def emitter(self, mock_repository, mock_flags):
        """Create EventEmitter with fresh dedup cache."""
        cache = SessionDedupCache()
        return EventEmitter(mock_repository, dedup_cache=cache, feature_flags=mock_flags)

    @pytest.mark.asyncio
    async def test_first_emit_succeeds(self, emitter, mock_repository):
        """First emit should succeed and return event ID."""
        result = await emitter.emit(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test"},
            user_id="user-1",
            session_id="session-1"
        )

        assert result == "event-123"
        mock_repository.append.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_emit_returns_none(self, emitter, mock_repository):
        """Second emit with same params in same session should return None."""
        # First emit
        await emitter.emit(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test"},
            user_id="user-1",
            session_id="session-1"
        )

        # Reset mock to check second call
        mock_repository.append.reset_mock()

        # Second emit - should be deduplicated
        result = await emitter.emit(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test"},
            user_id="user-1",
            session_id="session-1"
        )

        assert result is None
        mock_repository.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_different_session_not_deduplicated(self, emitter, mock_repository):
        """Same event in different session should not be deduplicated."""
        # First emit in session-1
        await emitter.emit(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test"},
            user_id="user-1",
            session_id="session-1"
        )

        mock_repository.append.reset_mock()

        # Second emit in session-2 - should NOT be deduplicated
        result = await emitter.emit(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test"},
            user_id="user-1",
            session_id="session-2"
        )

        assert result == "event-123"
        mock_repository.append.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_session_id_disables_dedup(self, emitter, mock_repository):
        """Without session_id, deduplication should be disabled."""
        # First emit without session_id
        await emitter.emit(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test"},
            user_id="user-1"
            # No session_id
        )

        mock_repository.append.reset_mock()

        # Second emit without session_id - should still emit
        result = await emitter.emit(
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={"title": "Test"},
            user_id="user-1"
            # No session_id
        )

        assert result == "event-123"
        mock_repository.append.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_created_factory_with_session(self, emitter, mock_repository):
        """Test task_created factory method with session_id."""
        result = await emitter.emit_task_created(
            task_id="task-1",
            user_id="user-1",
            title="Test task",
            session_id="session-1"
        )

        assert result == "event-123"
        mock_repository.append.assert_called_once()

        # Second call - should be deduplicated
        mock_repository.append.reset_mock()
        result2 = await emitter.emit_task_created(
            task_id="task-1",
            user_id="user-1",
            title="Test task",
            session_id="session-1"
        )

        assert result2 is None
        mock_repository.append.assert_not_called()


class TestGlobalDedupCache:
    """Tests for global dedup cache functions."""

    def test_get_global_dedup_cache(self):
        """get_global_dedup_cache should return the global instance."""
        cache = get_global_dedup_cache()
        assert isinstance(cache, SessionDedupCache)

    def test_clear_global_dedup_cache(self):
        """clear_global_dedup_cache should clear all entries."""
        cache = get_global_dedup_cache()

        # Add an entry
        cache.mark_emitted(
            session_id="test-session",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={}
        )

        # Clear
        clear_global_dedup_cache()

        # Should not be duplicate after clear
        result = cache.is_duplicate(
            session_id="test-session",
            aggregate_type="task",
            aggregate_id="task-1",
            event_type="task_created",
            payload={}
        )

        assert result is False
