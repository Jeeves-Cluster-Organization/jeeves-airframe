"""
Trace repository for agent decision audit logging.

Provides:
- Agent trace persistence
- Trace retrieval by correlation, request, or agent
- Performance metrics aggregation
- Span hierarchy support
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
import json

from jeeves_infra.logging import get_component_logger
from jeeves_infra.utils.datetime import parse_datetime
from jeeves_infra.protocols import LoggerProtocol, DatabaseClientProtocol


class AgentTrace:
    """Represents an agent's decision trace."""

    def __init__(
        self,
        agent_name: str,
        stage: str,
        correlation_id: str,
        request_id: str,
        user_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        llm_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        prompt_version: Optional[str] = None,
        latency_ms: Optional[int] = None,
        token_count_input: Optional[int] = None,
        token_count_output: Optional[int] = None,
        confidence: Optional[float] = None,
        status: str = "success",
        error_details: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None
    ):
        """
        Initialize an agent trace.

        Args:
            agent_name: Name of the agent ('planner', 'executor', etc.)
            stage: Processing stage ('planning', 'execution', etc.)
            correlation_id: Request-level grouping
            request_id: Specific request ID
            user_id: User ID
            input_data: Structured input to the agent
            output_data: Structured output from the agent
            llm_model: LLM model used (if applicable)
            llm_provider: LLM provider (if applicable)
            prompt_version: Prompt version used
            latency_ms: Execution time in milliseconds
            token_count_input: Input tokens (if LLM used)
            token_count_output: Output tokens (if LLM used)
            confidence: Agent's confidence score (0.0-1.0)
            status: Execution status ('success', 'error', 'retry', 'skipped')
            error_details: Error context if status='error'
            trace_id: Unique trace ID
            span_id: Span ID for distributed tracing
            parent_span_id: Parent span ID (for nested spans)
            started_at: When execution started
            completed_at: When execution completed
        """
        self.trace_id = trace_id or str(uuid4())
        self.span_id = span_id or str(uuid4())
        self.parent_span_id = parent_span_id
        self.agent_name = agent_name
        self.stage = stage
        self.input_data = input_data
        self.output_data = output_data
        self.llm_model = llm_model
        self.llm_provider = llm_provider
        self.prompt_version = prompt_version
        self.latency_ms = latency_ms
        self.token_count_input = token_count_input
        self.token_count_output = token_count_output
        self.confidence = confidence
        self.status = status
        self.error_details = error_details
        self.correlation_id = correlation_id
        self.request_id = request_id
        self.user_id = user_id
        self.started_at = started_at or datetime.now(timezone.utc)
        self.completed_at = completed_at

    def complete(
        self,
        output_data: Optional[Dict[str, Any]] = None,
        status: str = "success",
        confidence: Optional[float] = None,
        error_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Mark the trace as complete.

        Args:
            output_data: Output from the agent
            status: Final status
            confidence: Confidence score
            error_details: Error details if failed
        """
        self.completed_at = datetime.now(timezone.utc)
        if output_data is not None:
            self.output_data = output_data
        self.status = status
        if confidence is not None:
            self.confidence = confidence
        if error_details is not None:
            self.error_details = error_details

        # Calculate latency
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            self.latency_ms = int(delta.total_seconds() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "agent_name": self.agent_name,
            "stage": self.stage,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "llm_model": self.llm_model,
            "llm_provider": self.llm_provider,
            "prompt_version": self.prompt_version,
            "latency_ms": self.latency_ms,
            "token_count_input": self.token_count_input,
            "token_count_output": self.token_count_output,
            "confidence": self.confidence,
            "status": self.status,
            "error_details": self.error_details,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTrace":
        """Create from dictionary."""
        started_at = parse_datetime(data.get("started_at"))
        completed_at = parse_datetime(data.get("completed_at"))

        return cls(
            trace_id=data.get("trace_id"),
            span_id=data.get("span_id"),
            parent_span_id=data.get("parent_span_id"),
            agent_name=data["agent_name"],
            stage=data["stage"],
            input_data=data.get("input_data"),
            output_data=data.get("output_data"),
            llm_model=data.get("llm_model"),
            llm_provider=data.get("llm_provider"),
            prompt_version=data.get("prompt_version"),
            latency_ms=data.get("latency_ms"),
            token_count_input=data.get("token_count_input"),
            token_count_output=data.get("token_count_output"),
            confidence=data.get("confidence"),
            status=data.get("status", "success"),
            error_details=data.get("error_details"),
            correlation_id=data["correlation_id"],
            request_id=data["request_id"],
            user_id=data["user_id"],
            started_at=started_at,
            completed_at=completed_at
        )


class TraceRepository:
    """Repository for agent trace persistence."""

    def __init__(self, db_client: DatabaseClientProtocol, logger: Optional[LoggerProtocol] = None):
        """
        Initialize trace repository.

        Args:
            db_client: Database client instance
            logger: Optional logger instance
        """
        self._logger = get_component_logger("TraceRepository", logger)
        self.db = db_client

    async def save(self, trace: AgentTrace) -> str:
        """
        Save an agent trace.

        Args:
            trace: Agent trace to save

        Returns:
            Trace ID
        """
        query = """
            INSERT INTO agent_traces (
                trace_id, span_id, parent_span_id,
                agent_name, stage, input_json, output_json,
                llm_model, llm_provider, prompt_version,
                latency_ms, token_count_input, token_count_output,
                confidence, status, error_details,
                correlation_id, request_id, user_id,
                started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            trace.trace_id,
            trace.span_id,
            trace.parent_span_id,
            trace.agent_name,
            trace.stage,
            json.dumps(trace.input_data) if trace.input_data else None,
            json.dumps(trace.output_data) if trace.output_data else None,
            trace.llm_model,
            trace.llm_provider,
            trace.prompt_version,
            trace.latency_ms,
            trace.token_count_input,
            trace.token_count_output,
            trace.confidence,
            trace.status,
            json.dumps(trace.error_details) if trace.error_details else None,
            trace.correlation_id,
            trace.request_id,
            trace.user_id,
            trace.started_at,
            trace.completed_at
        )

        try:
            await self.db.execute(query, params)
            self._logger.info(
                "trace_saved",
                trace_id=trace.trace_id,
                agent_name=trace.agent_name,
                status=trace.status
            )
            return trace.trace_id

        except Exception as e:
            self._logger.error("trace_save_failed", error=str(e), trace_id=trace.trace_id)
            raise

    async def update(self, trace: AgentTrace) -> bool:
        """
        Update an existing trace (e.g., when completing).

        Args:
            trace: Updated trace

        Returns:
            True if updated successfully
        """
        query = """
            UPDATE agent_traces SET
                output_json = ?,
                latency_ms = ?,
                token_count_input = ?,
                token_count_output = ?,
                confidence = ?,
                status = ?,
                error_details = ?,
                completed_at = ?
            WHERE trace_id = ?
        """

        params = (
            json.dumps(trace.output_data) if trace.output_data else None,
            trace.latency_ms,
            trace.token_count_input,
            trace.token_count_output,
            trace.confidence,
            trace.status,
            json.dumps(trace.error_details) if trace.error_details else None,
            trace.completed_at,
            trace.trace_id
        )

        try:
            await self.db.execute(query, params)
            self._logger.debug("trace_updated", trace_id=trace.trace_id)
            return True

        except Exception as e:
            self._logger.error("trace_update_failed", error=str(e), trace_id=trace.trace_id)
            return False

    async def get_by_id(self, trace_id: str) -> Optional[AgentTrace]:
        """
        Get trace by ID.

        Args:
            trace_id: Trace ID

        Returns:
            AgentTrace or None if not found
        """
        query = "SELECT * FROM agent_traces WHERE trace_id = ?"

        try:
            result = await self.db.fetch_one(query, (trace_id,))
            if result:
                return self._row_to_trace(result)
            return None

        except Exception as e:
            self._logger.error("trace_get_failed", error=str(e), trace_id=trace_id)
            raise

    async def get_by_correlation(
        self,
        correlation_id: str,
        limit: int = 100
    ) -> List[AgentTrace]:
        """
        Get all traces for a correlation ID.

        Args:
            correlation_id: Correlation ID
            limit: Maximum traces to return

        Returns:
            List of traces ordered by started_at
        """
        query = """
            SELECT * FROM agent_traces
            WHERE correlation_id = ?
            ORDER BY started_at ASC
            LIMIT ?
        """

        try:
            results = await self.db.fetch_all(query, (correlation_id, limit))
            return [self._row_to_trace(row) for row in results]

        except Exception as e:
            self._logger.error(
                "traces_by_correlation_failed",
                error=str(e),
                correlation_id=correlation_id
            )
            raise

    async def get_by_request(
        self,
        request_id: str,
        limit: int = 100
    ) -> List[AgentTrace]:
        """
        Get all traces for a request ID.

        Args:
            request_id: Request ID
            limit: Maximum traces to return

        Returns:
            List of traces ordered by started_at
        """
        query = """
            SELECT * FROM agent_traces
            WHERE request_id = ?
            ORDER BY started_at ASC
            LIMIT ?
        """

        try:
            results = await self.db.fetch_all(query, (request_id, limit))
            return [self._row_to_trace(row) for row in results]

        except Exception as e:
            self._logger.error(
                "traces_by_request_failed",
                error=str(e),
                request_id=request_id
            )
            raise

    async def get_by_agent(
        self,
        agent_name: str,
        user_id: str,
        since: Optional[datetime] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[AgentTrace]:
        """
        Get traces by agent name.

        Args:
            agent_name: Agent name
            user_id: User ID
            since: Only traces after this timestamp
            status: Optional status filter
            limit: Maximum traces to return

        Returns:
            List of traces ordered by started_at (most recent first)
        """
        conditions = ["agent_name = ?", "user_id = ?"]
        params: List[Any] = [agent_name, user_id]

        if since:
            conditions.append("started_at > ?")
            params.append(since)

        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT * FROM agent_traces
            WHERE {where_clause}
            ORDER BY started_at DESC
            LIMIT ?
        """
        params.append(limit)

        try:
            results = await self.db.fetch_all(query, tuple(params))
            return [self._row_to_trace(row) for row in results]

        except Exception as e:
            self._logger.error(
                "traces_by_agent_failed",
                error=str(e),
                agent_name=agent_name
            )
            raise

    async def get_agent_metrics(
        self,
        agent_name: str,
        user_id: str,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get aggregate metrics for an agent.

        Args:
            agent_name: Agent name
            user_id: User ID
            since: Only count traces after this timestamp

        Returns:
            Dictionary with metrics (count, success_rate, avg_latency, etc.)
        """
        if since:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
                    AVG(latency_ms) as avg_latency_ms,
                    AVG(confidence) as avg_confidence,
                    SUM(token_count_input) as total_input_tokens,
                    SUM(token_count_output) as total_output_tokens
                FROM agent_traces
                WHERE agent_name = ? AND user_id = ? AND started_at > ?
            """
            params = (agent_name, user_id, since)
        else:
            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
                    AVG(latency_ms) as avg_latency_ms,
                    AVG(confidence) as avg_confidence,
                    SUM(token_count_input) as total_input_tokens,
                    SUM(token_count_output) as total_output_tokens
                FROM agent_traces
                WHERE agent_name = ? AND user_id = ?
            """
            params = (agent_name, user_id)

        try:
            result = await self.db.fetch_one(query, params)
            if result:
                total = result["total"] or 0
                success_count = result["success_count"] or 0
                return {
                    "agent_name": agent_name,
                    "total_traces": total,
                    "success_count": success_count,
                    "error_count": result["error_count"] or 0,
                    "success_rate": success_count / total if total > 0 else 0.0,
                    "avg_latency_ms": result["avg_latency_ms"],
                    "avg_confidence": result["avg_confidence"],
                    "total_input_tokens": result["total_input_tokens"] or 0,
                    "total_output_tokens": result["total_output_tokens"] or 0
                }
            return {"agent_name": agent_name, "total_traces": 0}

        except Exception as e:
            self._logger.error(
                "agent_metrics_failed",
                error=str(e),
                agent_name=agent_name
            )
            return {"agent_name": agent_name, "error": str(e)}

    async def get_error_traces(
        self,
        user_id: str,
        limit: int = 50,
        agent_name: Optional[str] = None
    ) -> List[AgentTrace]:
        """
        Get recent error traces for debugging.

        Args:
            user_id: User ID
            limit: Maximum traces to return
            agent_name: Optional agent filter

        Returns:
            List of error traces ordered by started_at (most recent first)
        """
        if agent_name:
            query = """
                SELECT * FROM agent_traces
                WHERE user_id = ? AND status = 'error' AND agent_name = ?
                ORDER BY started_at DESC
                LIMIT ?
            """
            params = (user_id, agent_name, limit)
        else:
            query = """
                SELECT * FROM agent_traces
                WHERE user_id = ? AND status = 'error'
                ORDER BY started_at DESC
                LIMIT ?
            """
            params = (user_id, limit)

        try:
            results = await self.db.fetch_all(query, params)
            return [self._row_to_trace(row) for row in results]

        except Exception as e:
            self._logger.error("error_traces_failed", error=str(e), user_id=user_id)
            raise

    def _row_to_trace(self, row: Dict[str, Any]) -> AgentTrace:
        """Convert database row to AgentTrace."""
        started_at = parse_datetime(row.get("started_at"))
        completed_at = parse_datetime(row.get("completed_at"))

        input_data = row.get("input_json")
        if isinstance(input_data, str):
            input_data = json.loads(input_data)

        output_data = row.get("output_json")
        if isinstance(output_data, str):
            output_data = json.loads(output_data)

        error_details = row.get("error_details")
        if isinstance(error_details, str):
            error_details = json.loads(error_details)

        return AgentTrace(
            trace_id=row["trace_id"],
            span_id=row["span_id"],
            parent_span_id=row.get("parent_span_id"),
            agent_name=row["agent_name"],
            stage=row["stage"],
            input_data=input_data,
            output_data=output_data,
            llm_model=row.get("llm_model"),
            llm_provider=row.get("llm_provider"),
            prompt_version=row.get("prompt_version"),
            latency_ms=row.get("latency_ms"),
            token_count_input=row.get("token_count_input"),
            token_count_output=row.get("token_count_output"),
            confidence=row.get("confidence"),
            status=row.get("status", "success"),
            error_details=error_details,
            correlation_id=row["correlation_id"],
            request_id=row["request_id"],
            user_id=row["user_id"],
            started_at=started_at,
            completed_at=completed_at
        )
