"""
Event emitter service for domain event emission.

Provides:
- Centralized event emission with feature flag check
- Event factory methods for common event types
- Async emission (non-blocking)
- Correlation ID propagation
- Session-scoped deduplication (v0.14 Phase 3)
- CommBus event publishing for observability (P0 wiring)

Constitutional Reference:
- Memory Module CONSTITUTION P4: Memory operations publish events via CommBus
"""

from typing import Dict, Any, Optional, List, Set, TYPE_CHECKING
from datetime import datetime, timezone
from uuid import uuid4
import asyncio
import hashlib
import json

from jeeves_infra.memory.repositories.event_repository import EventRepository, DomainEvent
from jeeves_infra.logging import get_component_logger
from jeeves_infra.protocols import LoggerProtocol, FeatureFlagsProtocol

if TYPE_CHECKING:
    # CommBus is now in Go (commbus/) - use Protocol for type hints
    from typing import Protocol
    class InMemoryCommBus(Protocol):
        """Stub protocol for CommBus (actual implementation is Go)."""
        async def publish(self, topic: str, message: Any) -> None: ...


class SessionDedupCache:
    """
    Session-scoped event deduplication cache.

    v0.14 Phase 3: Prevents duplicate L2 event emission within a session.
    This is critical for retry safety - if the same action is retried
    within a session, we don't want to emit duplicate events.

    Key format: sha256(session_id:aggregate_type:aggregate_id:event_type:payload_hash)[:32]
    """

    def __init__(self, max_size: int = 10000, logger: Optional[LoggerProtocol] = None):
        """
        Initialize deduplication cache.

        Args:
            max_size: Maximum entries per session (prevents memory bloat)
            logger: Optional logger instance (ADR-001 DI)
        """
        self._logger = get_component_logger("session_dedup_cache", logger)
        self._caches: Dict[str, Set[str]] = {}
        self._max_size = max_size

    def _generate_dedup_key(
        self,
        session_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> str:
        """
        Generate a deterministic deduplication key.

        The key includes payload hash to distinguish semantically different events
        on the same aggregate (e.g., different task updates).
        """
        # Stable hash of payload (sorted keys for determinism)
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()[:16]

        key_input = f"{session_id}:{aggregate_type}:{aggregate_id}:{event_type}:{payload_hash}"
        return hashlib.sha256(key_input.encode()).hexdigest()[:32]

    def is_duplicate(
        self,
        session_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Check if this event was already emitted in this session.

        Args:
            session_id: Session ID for scoping
            aggregate_type: Type of aggregate
            aggregate_id: Aggregate ID
            event_type: Event type
            payload: Event payload

        Returns:
            True if duplicate (already emitted), False if new
        """
        if not session_id:
            # No session context - can't deduplicate
            return False

        dedup_key = self._generate_dedup_key(
            session_id, aggregate_type, aggregate_id, event_type, payload
        )

        session_cache = self._caches.get(session_id, set())
        return dedup_key in session_cache

    def mark_emitted(
        self,
        session_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        Mark an event as emitted in this session.

        Args:
            session_id: Session ID for scoping
            aggregate_type: Type of aggregate
            aggregate_id: Aggregate ID
            event_type: Event type
            payload: Event payload
        """
        if not session_id:
            return

        dedup_key = self._generate_dedup_key(
            session_id, aggregate_type, aggregate_id, event_type, payload
        )

        if session_id not in self._caches:
            self._caches[session_id] = set()

        # Evict oldest entries if cache is full (simple LRU-like behavior)
        if len(self._caches[session_id]) >= self._max_size:
            self._logger.warning(
                "session_dedup_cache_full",
                session_id=session_id,
                size=len(self._caches[session_id])
            )
            # Clear half the cache (simple eviction strategy)
            entries = list(self._caches[session_id])
            self._caches[session_id] = set(entries[len(entries) // 2:])

        self._caches[session_id].add(dedup_key)

    def clear_session(self, session_id: str) -> None:
        """Clear cache for a specific session."""
        if session_id in self._caches:
            del self._caches[session_id]
            self._logger.debug("session_dedup_cache_cleared", session_id=session_id)

    def clear_all(self) -> None:
        """Clear all session caches."""
        self._caches.clear()
        self._logger.debug("session_dedup_cache_cleared_all")

    @property
    def session_count(self) -> int:
        """Number of active session caches."""
        return len(self._caches)

    def get_session_size(self, session_id: str) -> int:
        """Get number of cached entries for a session."""
        return len(self._caches.get(session_id, set()))


# Lazy initialization - no module-level instantiation (ADR-001 compliance)
_global_dedup_cache: Optional[SessionDedupCache] = None


def _get_global_dedup_cache() -> SessionDedupCache:
    """Internal getter for lazy initialization of global dedup cache."""
    global _global_dedup_cache
    if _global_dedup_cache is None:
        _global_dedup_cache = SessionDedupCache()
    return _global_dedup_cache


class EventEmitter:
    """
    Service for emitting domain events.

    Per Memory Contract M2: Events are immutable history.
    Per Constitution P6: All operations logged and traceable.

    v0.14 Phase 3: Session-scoped deduplication prevents duplicate events
    during retries within the same session.

    Constitutional Reference:
        - Memory Module: Use protocol injection instead of direct imports
        - Respect layer boundaries (L1 infra → L0 core only)
    """

    def __init__(
        self,
        event_repository: EventRepository,
        feature_flags: Optional[FeatureFlagsProtocol] = None,
        dedup_cache: Optional[SessionDedupCache] = None,
        logger: Optional[LoggerProtocol] = None,
        commbus: Optional["InMemoryCommBus"] = None,
    ):
        """
        Initialize event emitter.

        Args:
            event_repository: Repository for event persistence
            feature_flags: Feature flags protocol for checking if event sourcing is enabled
            dedup_cache: Optional custom deduplication cache (uses global if not provided)
            logger: Optional logger instance (ADR-001 DI)
            commbus: Optional CommBus for event publishing (P0 wiring)
        """
        self._logger = get_component_logger("event_emitter", logger)
        self.repository = event_repository
        self._feature_flags = feature_flags
        self._dedup_cache = dedup_cache or _get_global_dedup_cache()
        self._commbus = commbus

    async def _get_commbus(self) -> Optional["InMemoryCommBus"]:
        """Get the CommBus instance (async lazy initialization).

        Uses kernel_client to access the Go kernel's CommBus via gRPC.
        This follows the Agentic OS pattern: Python → kernel_client → gRPC → Go kernel.
        """
        if self._commbus is None:
            try:
                from jeeves_infra.kernel_client import get_commbus
                self._commbus = await get_commbus()
            except Exception:
                # Kernel not running, CommBus unavailable
                pass
        return self._commbus

    @property
    def enabled(self) -> bool:
        """Check if event sourcing is enabled.

        If no feature flags were injected, defaults to enabled.
        """
        if self._feature_flags is None:
            return True
        return self._feature_flags.is_enabled("memory_event_sourcing")

    @property
    def dedup_cache(self) -> SessionDedupCache:
        """Access to deduplication cache for testing/management."""
        return self._dedup_cache

    async def emit(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        user_id: str,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Emit a domain event with session-scoped deduplication.

        v0.14 Phase 3: When session_id is provided, duplicate events within
        the same session are automatically skipped. This prevents duplicate
        L2 events during cyclic retries.

        Args:
            aggregate_type: Type of aggregate ('task', 'journal', etc.)
            aggregate_id: ID of the aggregate
            event_type: Type of event ('task_created', etc.)
            payload: Event payload
            user_id: User ID
            actor: Who caused this event
            correlation_id: Request-level grouping
            causation_id: Direct cause
            session_id: Optional session ID for deduplication (v0.14)

        Returns:
            Event ID if emitted, None if disabled or deduplicated
        """
        if not self.enabled:
            self._logger.debug(
                "event_emission_disabled",
                event_type=event_type
            )
            return None

        # v0.14: Session-scoped deduplication
        if session_id and self._dedup_cache.is_duplicate(
            session_id=session_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload
        ):
            self._logger.debug(
                "event_deduplicated",
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                session_id=session_id
            )
            return None

        event = DomainEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            causation_id=causation_id
        )

        try:
            event_id = await self.repository.append(event)

            # v0.14: Mark as emitted in session cache
            if session_id:
                self._dedup_cache.mark_emitted(
                    session_id=session_id,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    event_type=event_type,
                    payload=payload
                )

            self._logger.info(
                "event_emitted",
                event_id=event_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                session_id=session_id
            )

            # P0 wiring: Publish to CommBus for observability
            await self._publish_to_commbus(
                event_id=event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
                user_id=user_id,
                session_id=session_id,
            )

            return event_id

        except Exception as e:
            self._logger.error(
                "event_emission_failed",
                error=str(e),
                event_type=event_type
            )
            # Don't fail the operation if event emission fails
            return None

    async def _publish_to_commbus(
        self,
        event_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        user_id: str,
        session_id: Optional[str] = None,
    ) -> None:
        """Publish event to CommBus for observability.

        Uses kernel_client to access Go kernel's CommBus via gRPC.
        Non-blocking - errors are logged but don't fail the main operation.

        Agentic OS Pattern: Python → kernel_client → gRPC → Go kernel CommBus
        """
        commbus = await self._get_commbus()
        if commbus is None:
            return

        try:
            # Publish via gRPC to Go kernel's CommBus
            # CommBusClient.publish(event_type, payload) interface
            await commbus.publish(
                event_type="MemoryStored",
                payload={
                    "item_id": event_id,
                    "layer": "L2",  # Event log layer
                    "user_id": user_id,
                    "item_type": event_type,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "session_id": session_id,
                    **payload,
                },
            )
            self._logger.debug(
                "event_published_to_commbus",
                event_id=event_id,
                event_type=event_type,
            )
        except Exception as e:
            # Log but don't fail - CommBus publishing is observability, not critical path
            self._logger.warning(
                "commbus_publish_failed",
                event_id=event_id,
                error=str(e),
            )

    async def emit_async(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        user_id: str,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """
        Emit a domain event asynchronously (fire-and-forget).

        Use this for non-critical events where you don't need the event ID.

        Args:
            Same as emit()
        """
        asyncio.create_task(
            self.emit(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
                user_id=user_id,
                actor=actor,
                correlation_id=correlation_id,
                causation_id=causation_id,
                session_id=session_id
            )
        )

    # ============================================================
    # Task Event Factories
    # ============================================================

    async def emit_task_created(
        self,
        task_id: str,
        user_id: str,
        title: str,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        due_at: Optional[datetime] = None,
        actor: str = "user",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit task_created event."""
        return await self.emit(
            aggregate_type="task",
            aggregate_id=task_id,
            event_type="task_created",
            payload={
                "title": title,
                "description": description,
                "priority": priority,
                "due_at": due_at.isoformat() if due_at else None
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_task_updated(
        self,
        task_id: str,
        user_id: str,
        changes: List[Dict[str, Any]],
        actor: str = "user",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Emit task_updated event.

        Args:
            task_id: Task ID
            user_id: User ID
            changes: List of changes [{field, old, new}, ...]
            actor: Who made the change
            correlation_id: Request grouping
            session_id: Optional session ID for deduplication (v0.14)
        """
        return await self.emit(
            aggregate_type="task",
            aggregate_id=task_id,
            event_type="task_updated",
            payload={"changes": changes},
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_task_completed(
        self,
        task_id: str,
        user_id: str,
        actor: str = "user",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit task_completed event."""
        return await self.emit(
            aggregate_type="task",
            aggregate_id=task_id,
            event_type="task_completed",
            payload={"completed_at": datetime.now(timezone.utc).isoformat()},
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_task_deleted(
        self,
        task_id: str,
        user_id: str,
        soft: bool = True,
        actor: str = "user",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit task_deleted event."""
        return await self.emit(
            aggregate_type="task",
            aggregate_id=task_id,
            event_type="task_deleted",
            payload={"soft": soft},
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    # ============================================================
    # Journal Event Factories
    # ============================================================

    async def emit_journal_ingested(
        self,
        entry_id: str,
        user_id: str,
        content: str,
        word_count: Optional[int] = None,
        actor: str = "user",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit journal_ingested event."""
        return await self.emit(
            aggregate_type="journal",
            aggregate_id=entry_id,
            event_type="journal_ingested",
            payload={
                "content_preview": content[:200] if content else "",
                "word_count": word_count or len(content.split()) if content else 0
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_journal_summarized(
        self,
        entry_id: str,
        user_id: str,
        summary: str,
        summarizer_model: Optional[str] = None,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit journal_summarized event."""
        return await self.emit(
            aggregate_type="journal",
            aggregate_id=entry_id,
            event_type="journal_summarized",
            payload={
                "summary": summary,
                "summarizer_model": summarizer_model
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    # ============================================================
    # Session Event Factories
    # ============================================================

    async def emit_session_started(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
        actor: str = "user",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit session_started event.

        Note: session_started uses session_id as the aggregate_id,
        so deduplication is automatic via the aggregate key.
        """
        return await self.emit(
            aggregate_type="session",
            aggregate_id=session_id,
            event_type="session_started",
            payload={"title": title},
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id  # Session events use their own ID for dedup
        )

    async def emit_session_summarized(
        self,
        session_id: str,
        user_id: str,
        summary: str,
        up_to_event_id: str,
        actor: str = "system",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit session_summarized event."""
        return await self.emit(
            aggregate_type="session",
            aggregate_id=session_id,
            event_type="session_summarized",
            payload={
                "summary": summary,
                "up_to_event_id": up_to_event_id
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id  # Session events use their own ID for dedup
        )

    # ============================================================
    # Config Event Factories
    # ============================================================

    async def emit_config_changed(
        self,
        key: str,
        user_id: str,
        old_value: Any,
        new_value: Any,
        actor: str = "user",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit config_changed event."""
        return await self.emit(
            aggregate_type="config",
            aggregate_id=key,
            event_type="config_changed",
            payload={
                "key": key,
                "old_value": old_value,
                "new_value": new_value
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    # ============================================================
    # Governance Event Factories
    # ============================================================

    async def emit_tool_quarantined(
        self,
        tool_name: str,
        user_id: str,
        reason: str,
        error_rate: float,
        threshold: float,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit tool_quarantined event."""
        return await self.emit(
            aggregate_type="governance",
            aggregate_id=tool_name,
            event_type="tool_quarantined",
            payload={
                "tool_name": tool_name,
                "reason": reason,
                "error_rate": error_rate,
                "threshold": threshold
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_tool_restored(
        self,
        tool_name: str,
        user_id: str,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit tool_restored event."""
        return await self.emit(
            aggregate_type="governance",
            aggregate_id=tool_name,
            event_type="tool_restored",
            payload={"tool_name": tool_name},
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    # ============================================================
    # Fact Event Factories
    # ============================================================

    async def emit_fact_created(
        self,
        fact_id: str,
        user_id: str,
        domain: str,
        key: str,
        value: Any,
        actor: str = "user",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit fact_created event."""
        return await self.emit(
            aggregate_type="fact",
            aggregate_id=fact_id,
            event_type="fact_created",
            payload={
                "domain": domain,
                "key": key,
                "value": value
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    # ============================================================
    # Message Event Factories
    # ============================================================

    async def emit_message_created(
        self,
        message_id: str,
        session_id: str,
        user_id: str,
        role: str,
        content_preview: str,
        actor: str = "user",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit message_created event."""
        return await self.emit(
            aggregate_type="message",
            aggregate_id=message_id,
            event_type="message_created",
            payload={
                "session_id": session_id,
                "role": role,
                "content_preview": content_preview[:100]
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id  # Message events use their session for dedup
        )

    # ============================================================
    # Memory Event Factories (CommBus integration)
    # Emits events defined in jeeves_infra/memory/messages/events.py
    # ============================================================

    async def emit_memory_stored(
        self,
        item_id: str,
        layer: str,
        user_id: str,
        item_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit memory_stored event when a memory item is persisted.

        Maps to MemoryStored from messages/events.py.
        """
        return await self.emit(
            aggregate_type="memory",
            aggregate_id=item_id,
            event_type="memory_stored",
            payload={
                "layer": layer,
                "item_type": item_type,
                "metadata": metadata or {}
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_memory_retrieved(
        self,
        user_id: str,
        query: str,
        layer: str,
        results_count: int,
        latency_ms: float,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit memory_retrieved event when memory is queried.

        Maps to MemoryRetrieved from messages/events.py.
        """
        # Generate a unique aggregate ID for the search operation
        from uuid import uuid4
        search_id = f"search_{uuid4().hex[:12]}"

        return await self.emit(
            aggregate_type="memory",
            aggregate_id=search_id,
            event_type="memory_retrieved",
            payload={
                "query": query[:200] if query else "",
                "layer": layer,
                "results_count": results_count,
                "latency_ms": latency_ms
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_memory_deleted(
        self,
        item_id: str,
        layer: str,
        user_id: str,
        soft_delete: bool = True,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit memory_deleted event when a memory item is deleted.

        Maps to MemoryDeleted from messages/events.py.
        """
        return await self.emit(
            aggregate_type="memory",
            aggregate_id=item_id,
            event_type="memory_deleted",
            payload={
                "layer": layer,
                "soft_delete": soft_delete
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_session_state_changed(
        self,
        session_id: str,
        user_id: str,
        change_type: str,
        actor: str = "system",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit session_state_changed event when session state changes.

        Maps to SessionStateChanged from messages/events.py.
        """
        return await self.emit(
            aggregate_type="session",
            aggregate_id=session_id,
            event_type="session_state_changed",
            payload={
                "change_type": change_type
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_focus_changed(
        self,
        session_id: str,
        focus_type: str,
        user_id: str,
        focus_id: Optional[str] = None,
        focus_label: Optional[str] = None,
        actor: str = "system",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit focus_changed event when session focus changes.

        Maps to FocusChanged from messages/events.py.
        """
        return await self.emit(
            aggregate_type="session",
            aggregate_id=session_id,
            event_type="focus_changed",
            payload={
                "focus_type": focus_type,
                "focus_id": focus_id,
                "focus_label": focus_label
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_entity_referenced(
        self,
        session_id: str,
        entity_type: str,
        entity_id: str,
        label: str,
        user_id: str,
        actor: str = "system",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit entity_referenced event when an entity is referenced in a session.

        Maps to EntityReferenced from messages/events.py.
        """
        return await self.emit(
            aggregate_type="session",
            aggregate_id=session_id,
            event_type="entity_referenced",
            payload={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "label": label
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_clarification_requested(
        self,
        session_id: str,
        question: str,
        original_request: str,
        user_id: str,
        options: Optional[List[str]] = None,
        actor: str = "system",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit clarification_requested event when clarification is needed.

        Maps to ClarificationRequested from messages/events.py.
        """
        return await self.emit(
            aggregate_type="session",
            aggregate_id=session_id,
            event_type="clarification_requested",
            payload={
                "question": question,
                "original_request": original_request[:500] if original_request else "",
                "options": options or []
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_clarification_resolved(
        self,
        session_id: str,
        answer: str,
        user_id: str,
        was_expired: bool = False,
        actor: str = "system",
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit clarification_resolved event when clarification is resolved.

        Maps to ClarificationResolved from messages/events.py.
        """
        return await self.emit(
            aggregate_type="session",
            aggregate_id=session_id,
            event_type="clarification_resolved",
            payload={
                "answer": answer,
                "was_expired": was_expired
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    # ============================================================
    # Workflow Event Factories (v1.0 Hardening)
    # ============================================================

    async def emit_plan_created(
        self,
        plan_id: str,
        request_id: str,
        user_id: str,
        intent: str,
        confidence: float,
        tool_count: int,
        tools: List[str],
        clarification_needed: bool = False,
        actor: str = "planner",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit plan_created event when Planner generates an execution plan."""
        return await self.emit(
            aggregate_type="plan",
            aggregate_id=plan_id,
            event_type="plan_created",
            payload={
                "request_id": request_id,
                "intent": intent,
                "confidence": confidence,
                "tool_count": tool_count,
                "tools": tools,
                "clarification_needed": clarification_needed
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_critic_decision(
        self,
        request_id: str,
        user_id: str,
        action: str,
        confidence: float,
        issue: Optional[str] = None,
        feedback: Optional[str] = None,
        actor: str = "critic",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit critic_decision event when Critic evaluates a response.

        Loop-back Architecture: action is 'approved', 'loop_back', or 'next_stage'.
        feedback is the refine_intent_hint for loop_back verdict.
        """
        return await self.emit(
            aggregate_type="workflow",
            aggregate_id=request_id,
            event_type="critic_decision",
            payload={
                "action": action,
                "confidence": confidence,
                "issue": issue,
                "feedback": feedback[:200] if feedback else None,
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_retry_attempt(
        self,
        request_id: str,
        user_id: str,
        retry_type: str,
        attempt_number: int,
        reason: str,
        feedback: Optional[str] = None,
        actor: str = "orchestrator",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit retry_attempt event when a retry is triggered.

        Args:
            retry_type: 'validator' or 'planner'
            attempt_number: Which retry attempt this is (1, 2, ...)
            reason: Why the retry was triggered
            feedback: Specific feedback for the retry
        """
        return await self.emit(
            aggregate_type="workflow",
            aggregate_id=request_id,
            event_type="retry_attempt",
            payload={
                "retry_type": retry_type,
                "attempt_number": attempt_number,
                "reason": reason,
                "feedback": feedback[:200] if feedback else None
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_response_drafted(
        self,
        response_id: str,
        request_id: str,
        user_id: str,
        response_preview: str,
        validation_status: str = "pending",
        actor: str = "integration",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit response_drafted event when Integration agent creates a response."""
        return await self.emit(
            aggregate_type="response",
            aggregate_id=response_id,
            event_type="response_drafted",
            payload={
                "request_id": request_id,
                "response_preview": response_preview[:200] if response_preview else "",
                "validation_status": validation_status
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )

    async def emit_tool_executed(
        self,
        request_id: str,
        user_id: str,
        tool_name: str,
        status: str,
        execution_time_ms: Optional[int] = None,
        error: Optional[str] = None,
        actor: str = "traverser",
        correlation_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[str]:
        """Emit tool_executed event when Traverser runs a tool."""
        return await self.emit(
            aggregate_type="workflow",
            aggregate_id=request_id,
            event_type="tool_executed",
            payload={
                "tool_name": tool_name,
                "status": status,
                "execution_time_ms": execution_time_ms,
                "error": error[:100] if error else None
            },
            user_id=user_id,
            actor=actor,
            correlation_id=correlation_id,
            session_id=session_id
        )


def get_global_dedup_cache() -> SessionDedupCache:
    """Get the global deduplication cache.

    Useful for testing and cache management.
    """
    return _get_global_dedup_cache()


def set_global_dedup_cache(cache: SessionDedupCache) -> None:
    """Set the global deduplication cache.

    Use at bootstrap time to inject a pre-configured cache.
    Primarily for testing purposes.

    Args:
        cache: SessionDedupCache instance to use as global
    """
    global _global_dedup_cache
    _global_dedup_cache = cache


def reset_global_dedup_cache() -> None:
    """Reset the global deduplication cache.

    Forces re-creation on next access.
    Primarily for testing purposes.
    """
    global _global_dedup_cache
    _global_dedup_cache = None


def clear_global_dedup_cache() -> None:
    """Clear the global deduplication cache.

    Useful for testing cleanup.
    """
    _get_global_dedup_cache().clear_all()
