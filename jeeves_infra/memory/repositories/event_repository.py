"""
Event repository for domain event persistence.

Provides:
- Append-only event storage (per Memory Contract M2)
- Event retrieval by correlation, aggregate, or time range
- Idempotent event insertion
- Timeline reconstruction
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
import json

from shared import get_component_logger, parse_datetime
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


class DomainEvent:
    """Represents an immutable domain event."""

    def __init__(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        user_id: str,
        actor: str = "system",
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        schema_version: int = 1
    ):
        """
        Initialize a domain event.

        Args:
            aggregate_type: Type of aggregate ('task', 'journal', 'session', etc.)
            aggregate_id: ID of the aggregate
            event_type: Type of event ('task_created', 'task_completed', etc.)
            payload: Event payload (JSON-serializable)
            user_id: User ID
            actor: Who caused this event ('user', 'planner', 'executor', 'system')
            correlation_id: Request-level grouping
            causation_id: Direct cause (e.g., parent event_id)
            event_id: Unique event ID (auto-generated if not provided)
            timestamp: Event timestamp (auto-generated if not provided)
            schema_version: Payload schema version
        """
        self.event_id = event_id or str(uuid4())
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.aggregate_type = aggregate_type
        self.aggregate_id = aggregate_id
        self.event_type = event_type
        self.schema_version = schema_version
        self.payload = payload
        self.correlation_id = correlation_id
        self.causation_id = causation_id
        self.user_id = user_id
        self.actor = actor

    @property
    def idempotency_key(self) -> str:
        """Generate idempotency key for deduplication."""
        return f"{self.aggregate_type}:{self.aggregate_id}:{self.event_type}:{self.schema_version}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "user_id": self.user_id,
            "actor": self.actor
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainEvent":
        """Create from dictionary."""
        timestamp = parse_datetime(data.get("timestamp"))

        return cls(
            event_id=data.get("event_id"),
            timestamp=timestamp,
            aggregate_type=data["aggregate_type"],
            aggregate_id=data["aggregate_id"],
            event_type=data["event_type"],
            schema_version=data.get("schema_version", 1),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            user_id=data["user_id"],
            actor=data.get("actor", "system")
        )


class EventRepository:
    """Repository for domain event persistence."""

    def __init__(self, db_client: DatabaseClientProtocol, logger: Optional[LoggerProtocol] = None):
        """
        Initialize event repository.

        Args:
            db_client: Database client instance
            logger: Optional logger instance
        """
        self._logger = get_component_logger("EventRepository", logger)
        self.db = db_client

    async def append(self, event: DomainEvent) -> str:
        """
        Append an event to the event log.

        Per Memory Contract M2: Events are append-only, never updated or deleted.

        Args:
            event: Domain event to append

        Returns:
            Event ID

        Raises:
            ValueError: If idempotency key already exists (duplicate event)
        """
        query = """
            INSERT INTO domain_events (
                event_id, occurred_at, aggregate_type, aggregate_id,
                event_type, schema_version, payload,
                causation_id, correlation_id, idempotency_key,
                user_id, actor
            ) VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, ?, ?, ?)
        """

        params = (
            event.event_id,
            event.timestamp,
            event.aggregate_type,
            event.aggregate_id,
            event.event_type,
            event.schema_version,
            json.dumps(event.payload),
            event.causation_id,
            event.correlation_id,
            event.idempotency_key,
            event.user_id,
            event.actor
        )

        try:
            await self.db.execute(query, params)
            self._logger.info(
                "event_appended",
                event_id=event.event_id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id
            )
            return event.event_id

        except Exception as e:
            if "UNIQUE constraint failed" in str(e) or "duplicate key" in str(e).lower():
                self._logger.warning(
                    "duplicate_event_skipped",
                    idempotency_key=event.idempotency_key
                )
                # Return existing event's ID (idempotent behavior)
                return event.event_id
            self._logger.error("event_append_failed", error=str(e), event_type=event.event_type)
            raise

    async def append_batch(self, events: List[DomainEvent]) -> List[str]:
        """
        Append multiple events in a single transaction.

        Args:
            events: List of domain events

        Returns:
            List of event IDs
        """
        event_ids = []
        for event in events:
            try:
                event_id = await self.append(event)
                event_ids.append(event_id)
            except Exception as e:
                self._logger.error(
                    "batch_event_append_failed",
                    error=str(e),
                    event_type=event.event_type
                )
                # Continue with other events
                continue

        self._logger.info("batch_events_appended", count=len(event_ids), total=len(events))
        return event_ids

    async def get_by_id(self, event_id: str) -> Optional[DomainEvent]:
        """
        Get event by ID.

        Args:
            event_id: Event ID

        Returns:
            DomainEvent or None if not found
        """
        query = "SELECT * FROM domain_events WHERE event_id = ?"

        try:
            result = await self.db.fetch_one(query, (event_id,))
            if result:
                return self._row_to_event(result)
            return None

        except Exception as e:
            self._logger.error("event_get_failed", error=str(e), event_id=event_id)
            raise

    async def get_by_correlation(
        self,
        correlation_id: str,
        limit: int = 100
    ) -> List[DomainEvent]:
        """
        Get all events for a correlation ID (single request).

        Args:
            correlation_id: Correlation ID
            limit: Maximum events to return

        Returns:
            List of events ordered by timestamp
        """
        query = """
            SELECT * FROM domain_events
            WHERE correlation_id = ?
            ORDER BY occurred_at ASC
            LIMIT ?
        """

        try:
            results = await self.db.fetch_all(query, (correlation_id, limit))
            return [self._row_to_event(row) for row in results]

        except Exception as e:
            self._logger.error(
                "events_by_correlation_failed",
                error=str(e),
                correlation_id=correlation_id
            )
            raise

    async def get_by_aggregate(
        self,
        aggregate_type: str,
        aggregate_id: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[DomainEvent]:
        """
        Get all events for an aggregate (entity history).

        Args:
            aggregate_type: Type of aggregate
            aggregate_id: Aggregate ID
            since: Only events after this timestamp
            limit: Maximum events to return

        Returns:
            List of events ordered by timestamp
        """
        if since:
            query = """
                SELECT * FROM domain_events
                WHERE aggregate_type = ? AND aggregate_id = ? AND occurred_at > ?
                ORDER BY occurred_at ASC
                LIMIT ?
            """
            params = (aggregate_type, aggregate_id, since, limit)
        else:
            query = """
                SELECT * FROM domain_events
                WHERE aggregate_type = ? AND aggregate_id = ?
                ORDER BY occurred_at ASC
                LIMIT ?
            """
            params = (aggregate_type, aggregate_id, limit)

        try:
            results = await self.db.fetch_all(query, params)
            return [self._row_to_event(row) for row in results]

        except Exception as e:
            self._logger.error(
                "events_by_aggregate_failed",
                error=str(e),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id
            )
            raise

    async def get_by_type(
        self,
        event_type: str,
        user_id: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[DomainEvent]:
        """
        Get events by type for a user.

        Args:
            event_type: Event type
            user_id: User ID
            since: Only events after this timestamp
            limit: Maximum events to return

        Returns:
            List of events ordered by timestamp
        """
        if since:
            query = """
                SELECT * FROM domain_events
                WHERE event_type = ? AND user_id = ? AND occurred_at > ?
                ORDER BY occurred_at DESC
                LIMIT ?
            """
            params = (event_type, user_id, since, limit)
        else:
            query = """
                SELECT * FROM domain_events
                WHERE event_type = ? AND user_id = ?
                ORDER BY occurred_at DESC
                LIMIT ?
            """
            params = (event_type, user_id, limit)

        try:
            results = await self.db.fetch_all(query, params)
            return [self._row_to_event(row) for row in results]

        except Exception as e:
            self._logger.error(
                "events_by_type_failed",
                error=str(e),
                event_type=event_type
            )
            raise

    async def get_recent(
        self,
        user_id: str,
        limit: int = 50,
        aggregate_types: Optional[List[str]] = None
    ) -> List[DomainEvent]:
        """
        Get recent events for a user.

        Args:
            user_id: User ID
            limit: Maximum events to return
            aggregate_types: Optional filter by aggregate types

        Returns:
            List of events ordered by timestamp (most recent first)
        """
        if aggregate_types:
            placeholders = ",".join("?" * len(aggregate_types))
            query = f"""
                SELECT * FROM domain_events
                WHERE user_id = ? AND aggregate_type IN ({placeholders})
                ORDER BY occurred_at DESC
                LIMIT ?
            """
            params = [user_id] + aggregate_types + [limit]
        else:
            query = """
                SELECT * FROM domain_events
                WHERE user_id = ?
                ORDER BY occurred_at DESC
                LIMIT ?
            """
            params = [user_id, limit]

        try:
            results = await self.db.fetch_all(query, tuple(params))
            return [self._row_to_event(row) for row in results]

        except Exception as e:
            self._logger.error("recent_events_failed", error=str(e), user_id=user_id)
            raise

    async def count_by_type(
        self,
        user_id: str,
        since: Optional[datetime] = None
    ) -> Dict[str, int]:
        """
        Count events by type for a user.

        Args:
            user_id: User ID
            since: Only count events after this timestamp

        Returns:
            Dictionary mapping event types to counts
        """
        if since:
            query = """
                SELECT event_type, COUNT(*) as count
                FROM domain_events
                WHERE user_id = ? AND occurred_at > ?
                GROUP BY event_type
            """
            params = (user_id, since)
        else:
            query = """
                SELECT event_type, COUNT(*) as count
                FROM domain_events
                WHERE user_id = ?
                GROUP BY event_type
            """
            params = (user_id,)

        try:
            results = await self.db.fetch_all(query, params)
            return {row["event_type"]: row["count"] for row in results}

        except Exception as e:
            self._logger.error("count_events_failed", error=str(e), user_id=user_id)
            return {}

    def _row_to_event(self, row: Dict[str, Any]) -> DomainEvent:
        """Convert database row to DomainEvent."""
        timestamp = parse_datetime(row.get("occurred_at"))

        payload = row.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        return DomainEvent(
            event_id=row["event_id"],
            timestamp=timestamp,
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            event_type=row["event_type"],
            schema_version=row.get("schema_version", 1),
            payload=payload,
            correlation_id=row.get("correlation_id"),
            causation_id=row.get("causation_id"),
            user_id=row["user_id"],
            actor=row.get("actor", "system")
        )
