"""
Tool Metrics Repository for L7 System Introspection.

Tracks tool execution metrics for:
- Performance monitoring (latency, throughput)
- Error rate tracking
- Success pattern analysis
- Health status determination

Constitutional Alignment:
- M2: Append-only event storage for metrics
- M5: Always uses database client abstraction
- L7: System introspection layer
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import json

from shared import uuid_str, uuid_read, get_component_logger, parse_datetime
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


class ToolMetric:
    """Represents a single tool execution metric event."""

    def __init__(
        self,
        metric_id: Optional[str] = None,
        tool_name: str = "",
        user_id: str = "",
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        status: str = "success",  # success, error, timeout
        execution_time_ms: int = 0,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        parameters_hash: Optional[str] = None,  # For duplicate detection
        input_size: int = 0,  # Size of input parameters
        output_size: int = 0,  # Size of output result
        metadata: Optional[Dict[str, Any]] = None,
        recorded_at: Optional[datetime] = None
    ):
        """
        Initialize a tool metric.

        Args:
            metric_id: Unique metric identifier
            tool_name: Name of the tool executed
            user_id: User who triggered the execution
            session_id: Session context
            request_id: Request context
            status: Execution status (success, error, timeout)
            execution_time_ms: Execution time in milliseconds
            error_type: Type of error if failed
            error_message: Error message if failed
            parameters_hash: Hash of parameters for duplicate detection
            input_size: Size of input in bytes/chars
            output_size: Size of output in bytes/chars
            metadata: Additional context
            recorded_at: When the metric was recorded
        """
        self.metric_id = metric_id or str(uuid4())
        self.tool_name = tool_name
        self.user_id = user_id
        self.session_id = session_id
        self.request_id = request_id
        self.status = status
        self.execution_time_ms = execution_time_ms
        self.error_type = error_type
        self.error_message = error_message
        self.parameters_hash = parameters_hash
        self.input_size = input_size
        self.output_size = output_size
        self.metadata = metadata or {}
        self.recorded_at = recorded_at or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metric_id": self.metric_id,
            "tool_name": self.tool_name,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "parameters_hash": self.parameters_hash,
            "input_size": self.input_size,
            "output_size": self.output_size,
            "metadata": self.metadata,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolMetric":
        """Create from dictionary."""
        recorded_at = parse_datetime(data.get("recorded_at"))

        return cls(
            metric_id=data.get("metric_id"),
            tool_name=data.get("tool_name", ""),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id"),
            request_id=data.get("request_id"),
            status=data.get("status", "success"),
            execution_time_ms=data.get("execution_time_ms", 0),
            error_type=data.get("error_type"),
            error_message=data.get("error_message"),
            parameters_hash=data.get("parameters_hash"),
            input_size=data.get("input_size", 0),
            output_size=data.get("output_size", 0),
            metadata=data.get("metadata"),
            recorded_at=recorded_at
        )


class ToolMetricsRepository:
    """
    Repository for tool execution metrics.

    Provides append-only storage for tool metrics with aggregation queries.
    """

    # Note: This SQL should match postgres_schema.sql
    # The authoritative schema is in postgres_schema.sql
    CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS tool_metrics (
            metric_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tool_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            session_id UUID,
            request_id UUID,
            status TEXT NOT NULL DEFAULT 'success',
            execution_time_ms INTEGER DEFAULT 0,
            error_type TEXT,
            error_message TEXT,
            parameters_hash TEXT,
            input_size INTEGER DEFAULT 0,
            output_size INTEGER DEFAULT 0,
            metadata TEXT,
            recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """

    CREATE_INDICES_SQL = [
        "CREATE INDEX IF NOT EXISTS idx_tool_metrics_tool ON tool_metrics(tool_name)",
        "CREATE INDEX IF NOT EXISTS idx_tool_metrics_status ON tool_metrics(status)",
        "CREATE INDEX IF NOT EXISTS idx_tool_metrics_recorded ON tool_metrics(recorded_at)",
        "CREATE INDEX IF NOT EXISTS idx_tool_metrics_tool_status ON tool_metrics(tool_name, status)"
    ]

    def __init__(self, db: DatabaseClientProtocol, logger: Optional[LoggerProtocol] = None):
        """Initialize repository."""
        self._logger = get_component_logger("ToolMetricsRepository", logger)
        self.db = db

    async def ensure_table(self) -> None:
        """Ensure the tool_metrics table exists."""
        await self.db.execute(self.CREATE_TABLE_SQL)
        for index_sql in self.CREATE_INDICES_SQL:
            await self.db.execute(index_sql)

    async def record(self, metric: ToolMetric) -> ToolMetric:
        """
        Record a tool metric.

        Args:
            metric: ToolMetric to record

        Returns:
            Recorded metric
        """
        query = """
            INSERT INTO tool_metrics
            (metric_id, tool_name, user_id, session_id, request_id, status,
             execution_time_ms, error_type, error_message, parameters_hash,
             input_size, output_size, metadata, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            metric.metric_id,
            metric.tool_name,
            metric.user_id,
            metric.session_id,
            metric.request_id,
            metric.status,
            metric.execution_time_ms,
            metric.error_type,
            metric.error_message,
            metric.parameters_hash,
            metric.input_size,
            metric.output_size,
            json.dumps(metric.metadata) if metric.metadata else None,
            metric.recorded_at  # Pass datetime directly (PostgreSQL-compatible)
        )

        await self.db.execute(query, params)

        self._logger.debug(
            "tool_metric_recorded",
            tool_name=metric.tool_name,
            status=metric.status,
            execution_time_ms=metric.execution_time_ms
        )

        return metric

    async def get_tool_stats(
        self,
        tool_name: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated statistics for a tool.

        Args:
            tool_name: Tool to get stats for
            since: Start time (default: 24 hours ago)
            until: End time (default: now)

        Returns:
            Dictionary with aggregated statistics
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
        if until is None:
            until = datetime.now(timezone.utc)

        query = """
            SELECT
                COUNT(*) as total_calls,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeout_count,
                AVG(execution_time_ms) as avg_time_ms,
                MIN(execution_time_ms) as min_time_ms,
                MAX(execution_time_ms) as max_time_ms,
                SUM(input_size) as total_input_bytes,
                SUM(output_size) as total_output_bytes
            FROM tool_metrics
            WHERE tool_name = ?
              AND recorded_at >= ?
              AND recorded_at <= ?
        """

        row = await self.db.fetch_one(query, (tool_name, since, until))

        if not row or row["total_calls"] == 0:
            return {
                "tool_name": tool_name,
                "total_calls": 0,
                "success_rate": 0.0,
                "avg_time_ms": 0,
                "period": {
                    "since": since.isoformat(),
                    "until": until.isoformat()
                }
            }

        total = row["total_calls"]
        success = row["success_count"] or 0

        return {
            "tool_name": tool_name,
            "total_calls": total,
            "success_count": success,
            "error_count": row["error_count"] or 0,
            "timeout_count": row["timeout_count"] or 0,
            "success_rate": (success / total) if total > 0 else 0.0,
            "avg_time_ms": round(row["avg_time_ms"] or 0, 2),
            "min_time_ms": row["min_time_ms"] or 0,
            "max_time_ms": row["max_time_ms"] or 0,
            "total_input_bytes": row["total_input_bytes"] or 0,
            "total_output_bytes": row["total_output_bytes"] or 0,
            "period": {
                "since": since.isoformat(),
                "until": until.isoformat()
            }
        }

    async def get_recent_errors(
        self,
        tool_name: Optional[str] = None,
        limit: int = 10
    ) -> List[ToolMetric]:
        """
        Get recent error metrics.

        Args:
            tool_name: Filter by tool (optional)
            limit: Maximum results

        Returns:
            List of error metrics
        """
        if tool_name:
            query = """
                SELECT * FROM tool_metrics
                WHERE tool_name = ? AND status != 'success'
                ORDER BY recorded_at DESC
                LIMIT ?
            """
            rows = await self.db.fetch_all(query, (tool_name, limit))
        else:
            query = """
                SELECT * FROM tool_metrics
                WHERE status != 'success'
                ORDER BY recorded_at DESC
                LIMIT ?
            """
            rows = await self.db.fetch_all(query, (limit,))

        return [self._row_to_metric(row) for row in rows]

    async def get_all_tool_names(self) -> List[str]:
        """
        Get list of all tools with metrics.

        Returns:
            List of tool names
        """
        query = """
            SELECT DISTINCT tool_name FROM tool_metrics
            ORDER BY tool_name
        """
        rows = await self.db.fetch_all(query)
        return [row["tool_name"] for row in rows]

    async def get_slow_executions(
        self,
        threshold_ms: int = 5000,
        limit: int = 20
    ) -> List[ToolMetric]:
        """
        Get tool executions slower than threshold.

        Args:
            threshold_ms: Time threshold in milliseconds
            limit: Maximum results

        Returns:
            List of slow execution metrics
        """
        query = """
            SELECT * FROM tool_metrics
            WHERE execution_time_ms >= ?
            ORDER BY execution_time_ms DESC
            LIMIT ?
        """
        rows = await self.db.fetch_all(query, (threshold_ms, limit))
        return [self._row_to_metric(row) for row in rows]

    async def get_recent_executions(
        self,
        tool_name: str,
        limit: int = 100
    ) -> List[ToolMetric]:
        """
        Get recent executions for a specific tool.

        Args:
            tool_name: Name of the tool
            limit: Maximum results

        Returns:
            List of recent metrics ordered by recorded_at DESC
        """
        query = """
            SELECT * FROM tool_metrics
            WHERE tool_name = ?
            ORDER BY recorded_at DESC
            LIMIT ?
        """
        rows = await self.db.fetch_all(query, (tool_name, limit))
        return [self._row_to_metric(row) for row in rows]

    async def cleanup_old_metrics(
        self,
        older_than_days: int = 30
    ) -> int:
        """
        Clean up old metrics (for storage management).

        Args:
            older_than_days: Delete metrics older than this

        Returns:
            Number of rows deleted (approximate)
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        query = """
            DELETE FROM tool_metrics
            WHERE recorded_at < ?
        """

        await self.db.execute(query, (cutoff,))

        self._logger.info(
            "tool_metrics_cleaned",
            older_than_days=older_than_days
        )

        return 0

    def _row_to_metric(self, row: Dict[str, Any]) -> ToolMetric:
        """Convert database row to ToolMetric.

        Uses centralized uuid_str from common/uuid_utils for UUID conversion.
        """
        metadata = row.get("metadata")
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}

        recorded_at = parse_datetime(row.get("recorded_at"))

        return ToolMetric(
            metric_id=uuid_read(row["metric_id"]),
            tool_name=row["tool_name"],
            user_id=uuid_read(row["user_id"]),
            session_id=uuid_read(row.get("session_id")),
            request_id=uuid_read(row.get("request_id")),
            status=row.get("status", "success"),
            execution_time_ms=row.get("execution_time_ms", 0),
            error_type=row.get("error_type"),
            error_message=row.get("error_message"),
            parameters_hash=row.get("parameters_hash"),
            input_size=row.get("input_size", 0),
            output_size=row.get("output_size", 0),
            metadata=metadata,
            recorded_at=recorded_at
        )
