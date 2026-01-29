"""
Trace recorder service for agent decision tracing.

Provides:
- Centralized trace recording with feature flag check
- Span management for hierarchical tracing
- Automatic latency calculation
- Metrics collection
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
from contextlib import asynccontextmanager
import asyncio

from jeeves_infra.memory.repositories.trace_repository import TraceRepository, AgentTrace
from jeeves_infra.logging import get_component_logger
from jeeves_infra.protocols import LoggerProtocol, FeatureFlagsProtocol


class TraceRecorder:
    """
    Service for recording agent decision traces.

    Per Constitution P6: Every critical path must be observable.
    Per Memory Contract L2: Agent decisions have a traceable cause chain.

    Constitutional Reference:
        - Memory Module: Use protocol injection instead of direct imports
        - Respect layer boundaries (L1 infra → L0 core only)
    """

    def __init__(
        self,
        trace_repository: TraceRepository,
        feature_flags: Optional[FeatureFlagsProtocol] = None,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize trace recorder.

        Args:
            trace_repository: Repository for trace persistence
            feature_flags: Feature flags protocol for checking if tracing is enabled
            logger: Optional logger instance (ADR-001 DI)
        """
        self.repository = trace_repository
        self._logger = get_component_logger("trace_recorder", logger)
        self._feature_flags = feature_flags
        self._active_traces: Dict[str, AgentTrace] = {}

    @property
    def enabled(self) -> bool:
        """Check if agent tracing is enabled.

        If no feature flags were injected, defaults to enabled.
        """
        if self._feature_flags is None:
            return True
        return self._feature_flags.is_enabled("memory_agent_tracing")

    def start_trace(
        self,
        agent_name: str,
        stage: str,
        correlation_id: str,
        request_id: str,
        user_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        llm_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        prompt_version: Optional[str] = None,
        parent_span_id: Optional[str] = None
    ) -> AgentTrace:
        """
        Start a new trace for an agent operation.

        Args:
            agent_name: Name of the agent
            stage: Processing stage
            correlation_id: Request-level grouping
            request_id: Specific request ID
            user_id: User ID
            input_data: Input to the agent
            llm_model: LLM model being used
            llm_provider: LLM provider
            prompt_version: Prompt version
            parent_span_id: Parent span for nested traces

        Returns:
            AgentTrace object (use trace.trace_id to complete later)
        """
        trace = AgentTrace(
            agent_name=agent_name,
            stage=stage,
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=user_id,
            input_data=input_data,
            llm_model=llm_model,
            llm_provider=llm_provider,
            prompt_version=prompt_version,
            parent_span_id=parent_span_id
        )

        if self.enabled:
            self._active_traces[trace.trace_id] = trace
            self._logger.debug(
                "trace_started",
                trace_id=trace.trace_id,
                agent_name=agent_name,
                stage=stage
            )

        return trace

    async def complete_trace(
        self,
        trace: AgentTrace,
        output_data: Optional[Dict[str, Any]] = None,
        status: str = "success",
        confidence: Optional[float] = None,
        error_details: Optional[Dict[str, Any]] = None,
        token_count_input: Optional[int] = None,
        token_count_output: Optional[int] = None
    ) -> Optional[str]:
        """
        Complete a trace and save it.

        Args:
            trace: The trace to complete
            output_data: Output from the agent
            status: Final status ('success', 'error', 'retry', 'skipped')
            confidence: Confidence score
            error_details: Error details if failed
            token_count_input: Input tokens used
            token_count_output: Output tokens generated

        Returns:
            Trace ID if saved, None if disabled
        """
        if not self.enabled:
            return None

        # Complete the trace
        trace.complete(
            output_data=output_data,
            status=status,
            confidence=confidence,
            error_details=error_details
        )

        # Set token counts
        if token_count_input is not None:
            trace.token_count_input = token_count_input
        if token_count_output is not None:
            trace.token_count_output = token_count_output

        # Remove from active traces
        self._active_traces.pop(trace.trace_id, None)

        try:
            await self.repository.save(trace)
            self._logger.info(
                "trace_completed",
                trace_id=trace.trace_id,
                agent_name=trace.agent_name,
                status=status,
                latency_ms=trace.latency_ms
            )
            return trace.trace_id

        except Exception as e:
            self._logger.error(
                "trace_save_failed",
                error=str(e),
                trace_id=trace.trace_id
            )
            return None

    async def record(
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
        parent_span_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Record a complete trace in one call.

        Use this when you have all trace information upfront.

        Args:
            agent_name: Name of the agent
            stage: Processing stage
            correlation_id: Request-level grouping
            request_id: Specific request ID
            user_id: User ID
            input_data: Input to the agent
            output_data: Output from the agent
            llm_model: LLM model used
            llm_provider: LLM provider
            prompt_version: Prompt version
            latency_ms: Execution time
            token_count_input: Input tokens
            token_count_output: Output tokens
            confidence: Confidence score
            status: Final status
            error_details: Error details if failed
            parent_span_id: Parent span for nested traces

        Returns:
            Trace ID if saved, None if disabled
        """
        if not self.enabled:
            return None

        now = datetime.now(timezone.utc)
        started_at = now
        completed_at = now

        trace = AgentTrace(
            agent_name=agent_name,
            stage=stage,
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=user_id,
            input_data=input_data,
            output_data=output_data,
            llm_model=llm_model,
            llm_provider=llm_provider,
            prompt_version=prompt_version,
            latency_ms=latency_ms,
            token_count_input=token_count_input,
            token_count_output=token_count_output,
            confidence=confidence,
            status=status,
            error_details=error_details,
            parent_span_id=parent_span_id,
            started_at=started_at,
            completed_at=completed_at
        )

        try:
            await self.repository.save(trace)
            self._logger.debug(
                "trace_recorded",
                trace_id=trace.trace_id,
                agent_name=agent_name,
                status=status
            )
            return trace.trace_id

        except Exception as e:
            self._logger.error(
                "trace_record_failed",
                error=str(e),
                agent_name=agent_name
            )
            return None

    async def record_async(
        self,
        agent_name: str,
        stage: str,
        correlation_id: str,
        request_id: str,
        user_id: str,
        **kwargs
    ) -> None:
        """
        Record a trace asynchronously (fire-and-forget).

        Args:
            Same as record()
        """
        asyncio.create_task(
            self.record(
                agent_name=agent_name,
                stage=stage,
                correlation_id=correlation_id,
                request_id=request_id,
                user_id=user_id,
                **kwargs
            )
        )

    @asynccontextmanager
    async def trace_context(
        self,
        agent_name: str,
        stage: str,
        correlation_id: str,
        request_id: str,
        user_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        llm_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        prompt_version: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Context manager for automatic trace start/complete.

        Usage:
            async with recorder.trace_context(...) as trace:
                # Do agent work
                result = await agent.process()
                trace.output_data = result
                trace.confidence = 0.95

        Args:
            Same as start_trace()

        Yields:
            AgentTrace object that can be modified
        """
        trace = self.start_trace(
            agent_name=agent_name,
            stage=stage,
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=user_id,
            input_data=input_data,
            llm_model=llm_model,
            llm_provider=llm_provider,
            prompt_version=prompt_version,
            parent_span_id=parent_span_id
        )

        try:
            yield trace
            # If no error, save with success status
            await self.complete_trace(
                trace=trace,
                output_data=trace.output_data,
                status=trace.status if trace.status != "success" else "success",
                confidence=trace.confidence,
                token_count_input=trace.token_count_input,
                token_count_output=trace.token_count_output
            )
        except Exception as e:
            # On error, save with error status
            await self.complete_trace(
                trace=trace,
                status="error",
                error_details={
                    "type": type(e).__name__,
                    "message": str(e)
                }
            )
            raise

    async def get_traces_for_request(
        self,
        request_id: str
    ) -> List[AgentTrace]:
        """
        Get all traces for a request.

        Args:
            request_id: Request ID

        Returns:
            List of traces ordered by started_at
        """
        return await self.repository.get_by_request(request_id)

    async def get_traces_for_correlation(
        self,
        correlation_id: str
    ) -> List[AgentTrace]:
        """
        Get all traces for a correlation ID.

        Args:
            correlation_id: Correlation ID

        Returns:
            List of traces ordered by started_at
        """
        return await self.repository.get_by_correlation(correlation_id)

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
            Dictionary with metrics
        """
        return await self.repository.get_agent_metrics(agent_name, user_id, since)

    async def get_recent_errors(
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
            List of error traces
        """
        return await self.repository.get_error_traces(user_id, limit, agent_name)
