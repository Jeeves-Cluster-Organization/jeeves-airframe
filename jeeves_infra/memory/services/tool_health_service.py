"""
Tool Health Service for L7 System Introspection.

Monitors tool health and provides:
- Health status determination
- Performance degradation detection
- Error pattern analysis
- Circuit breaker recommendations

Constitutional Alignment:
- P5: Deterministic health checks with clear thresholds
- M5: Uses repository abstraction
- L7: System introspection layer
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from jeeves_infra.protocols import HealthStatus, DatabaseClientProtocol
from jeeves_infra.memory.repositories.tool_metrics_repository import (
    ToolMetricsRepository,
    ToolMetric
)
from shared import get_component_logger
from jeeves_infra.protocols import LoggerProtocol


@dataclass
class ToolHealthReport:
    """Health report for a tool."""
    tool_name: str
    status: HealthStatus
    success_rate: float
    avg_latency_ms: float
    total_calls: int
    recent_errors: int
    issues: List[str]
    recommendations: List[str]
    checked_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "total_calls": self.total_calls,
            "recent_errors": self.recent_errors,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "checked_at": self.checked_at.isoformat()
        }


@dataclass
class SystemHealthReport:
    """Overall system health report."""
    status: HealthStatus
    tool_reports: List[ToolHealthReport]
    summary: Dict[str, int]  # healthy, degraded, unhealthy counts
    checked_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "tool_reports": [r.to_dict() for r in self.tool_reports],
            "summary": self.summary,
            "checked_at": self.checked_at.isoformat()
        }


class ToolHealthService:
    """
    Service for monitoring tool health.

    Provides health checks, degradation detection, and recommendations.
    """

    # Health thresholds (configurable)
    SUCCESS_RATE_HEALTHY = 0.95  # >= 95% success = healthy
    SUCCESS_RATE_DEGRADED = 0.80  # >= 80% success = degraded
    # Below 80% = unhealthy

    LATENCY_HEALTHY_MS = 2000  # <= 2s avg = healthy
    LATENCY_DEGRADED_MS = 5000  # <= 5s avg = degraded
    # Above 5s = unhealthy

    MIN_CALLS_FOR_ASSESSMENT = 5  # Need at least 5 calls to assess health

    def __init__(
        self,
        db: DatabaseClientProtocol,
        repository: Optional[ToolMetricsRepository] = None,
        registered_tool_names: Optional[List[str]] = None,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize service.

        Args:
            db: Database client instance
            repository: Optional pre-configured repository
            registered_tool_names: Optional list of known tool names from registry

            logger: Optional logger instance (ADR-001 DI)
        """
        self.db = db
        self.repository = repository or ToolMetricsRepository(db)
        self._logger = get_component_logger("ToolHealthService", logger)
        # Store registered tool names for health display
        self._registered_tool_names: List[str] = registered_tool_names or []

    def set_registered_tools(self, tool_names: List[str]) -> None:
        """
        Set the list of registered tool names.

        Called after tool registry is populated to ensure health
        dashboard shows all available tools, not just executed ones.

        Args:
            tool_names: List of registered tool names
        """
        self._registered_tool_names = tool_names
        self._logger.info(
            "registered_tools_set",
            tool_count=len(tool_names),
            tools=tool_names[:10],  # Log first 10 for brevity
        )

    async def ensure_initialized(self) -> None:
        """Ensure the repository table exists."""
        await self.repository.ensure_table()

    async def record_execution(
        self,
        tool_name: str,
        user_id: str,
        status: str = "success",
        execution_time_ms: int = 0,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolMetric:
        """
        Record a tool execution metric.

        Args:
            tool_name: Name of the executed tool
            user_id: User who triggered execution
            status: Execution status (success, error, timeout)
            execution_time_ms: Execution time in milliseconds
            session_id: Session context
            request_id: Request context
            error_type: Type of error if failed
            error_message: Error message if failed
            metadata: Additional context

        Returns:
            Recorded metric
        """
        metric = ToolMetric(
            tool_name=tool_name,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            status=status,
            execution_time_ms=execution_time_ms,
            error_type=error_type,
            error_message=error_message,
            metadata=metadata
        )

        return await self.repository.record(metric)

    async def check_tool_health(
        self,
        tool_name: str,
        period_hours: int = 1
    ) -> ToolHealthReport:
        """
        Check health of a specific tool.

        Args:
            tool_name: Tool to check
            period_hours: Time period for analysis

        Returns:
            ToolHealthReport with status and recommendations
        """
        since = datetime.now(timezone.utc) - timedelta(hours=period_hours)
        stats = await self.repository.get_tool_stats(tool_name, since=since)

        total_calls = stats.get("total_calls", 0)
        success_rate = stats.get("success_rate", 0.0)
        avg_time_ms = stats.get("avg_time_ms", 0)
        error_count = stats.get("error_count", 0)

        issues: List[str] = []
        recommendations: List[str] = []

        # Determine health status
        if total_calls < self.MIN_CALLS_FOR_ASSESSMENT:
            status = HealthStatus.UNKNOWN
            issues.append(f"Insufficient data ({total_calls} calls)")
            recommendations.append("Need more usage data for accurate assessment")
        else:
            # Assess success rate
            if success_rate >= self.SUCCESS_RATE_HEALTHY:
                success_status = HealthStatus.HEALTHY
            elif success_rate >= self.SUCCESS_RATE_DEGRADED:
                success_status = HealthStatus.DEGRADED
                issues.append(f"Success rate is {success_rate*100:.1f}% (target: ≥{self.SUCCESS_RATE_HEALTHY*100}%)")
                recommendations.append("Investigate recent error patterns")
            else:
                success_status = HealthStatus.UNHEALTHY
                issues.append(f"Success rate is critically low: {success_rate*100:.1f}%")
                recommendations.append("Urgent: Investigate tool failures")

            # Assess latency
            if avg_time_ms <= self.LATENCY_HEALTHY_MS:
                latency_status = HealthStatus.HEALTHY
            elif avg_time_ms <= self.LATENCY_DEGRADED_MS:
                latency_status = HealthStatus.DEGRADED
                issues.append(f"Latency is {avg_time_ms:.0f}ms (target: ≤{self.LATENCY_HEALTHY_MS}ms)")
                recommendations.append("Consider caching or optimization")
            else:
                latency_status = HealthStatus.UNHEALTHY
                issues.append(f"Latency is critically high: {avg_time_ms:.0f}ms")
                recommendations.append("Urgent: Investigate performance bottlenecks")

            # Combined status (worst of the two)
            status_priority = {
                HealthStatus.HEALTHY: 0,
                HealthStatus.DEGRADED: 1,
                HealthStatus.UNHEALTHY: 2,
                HealthStatus.UNKNOWN: 3
            }
            status = max([success_status, latency_status], key=lambda s: status_priority[s])

        return ToolHealthReport(
            tool_name=tool_name,
            status=status,
            success_rate=success_rate,
            avg_latency_ms=avg_time_ms,
            total_calls=total_calls,
            recent_errors=error_count,
            issues=issues,
            recommendations=recommendations,
            checked_at=datetime.now(timezone.utc)
        )

    async def check_all_tools_health(
        self,
        period_hours: int = 1
    ) -> SystemHealthReport:
        """
        Check health of all tools.

        Merges registered tools with tools that have execution metrics.
        This ensures the health dashboard shows all available tools,
        not just those that have been executed.

        Args:
            period_hours: Time period for analysis

        Returns:
            SystemHealthReport with all tool statuses
        """
        # Get tools with metrics from database
        executed_tool_names = set(await self.repository.get_all_tool_names())

        # Merge with registered tool names (if set)
        all_tool_names = set(self._registered_tool_names) | executed_tool_names

        # If no tools at all, return empty report with clear message
        if not all_tool_names:
            self._logger.info(
                "no_tools_for_health_check",
                registered_count=len(self._registered_tool_names),
                executed_count=len(executed_tool_names),
            )
            return SystemHealthReport(
                status=HealthStatus.UNKNOWN,
                tool_reports=[],
                summary={"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0},
                checked_at=datetime.now(timezone.utc)
            )

        tool_reports = []
        summary = {
            "healthy": 0,
            "degraded": 0,
            "unhealthy": 0,
            "unknown": 0
        }

        # Sort tool names for consistent display
        for tool_name in sorted(all_tool_names):
            if tool_name in executed_tool_names:
                # Tool has execution history - check its health
                report = await self.check_tool_health(tool_name, period_hours)
            else:
                # Tool is registered but never executed - mark as unknown
                report = ToolHealthReport(
                    tool_name=tool_name,
                    status=HealthStatus.UNKNOWN,
                    success_rate=0.0,
                    avg_latency_ms=0.0,
                    total_calls=0,
                    recent_errors=0,
                    issues=["No execution history"],
                    recommendations=["Tool has not been executed yet"],
                    checked_at=datetime.now(timezone.utc)
                )
            tool_reports.append(report)
            summary[report.status.value] += 1

        # Determine overall system status
        if summary["unhealthy"] > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif summary["degraded"] > 0:
            overall_status = HealthStatus.DEGRADED
        elif summary["healthy"] > 0:
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN

        self._logger.debug(
            "health_check_complete",
            tool_count=len(tool_reports),
            summary=summary,
        )

        return SystemHealthReport(
            status=overall_status,
            tool_reports=tool_reports,
            summary=summary,
            checked_at=datetime.now(timezone.utc)
        )

    async def should_circuit_break(
        self,
        tool_name: str,
        error_threshold: int = 5,
        window_minutes: int = 5
    ) -> bool:
        """
        Check if circuit breaker should be triggered for a tool.

        Args:
            tool_name: Tool to check
            error_threshold: Number of errors to trigger
            window_minutes: Time window for error count

        Returns:
            True if circuit breaker should be triggered
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        stats = await self.repository.get_tool_stats(tool_name, since=since)

        error_count = (stats.get("error_count", 0) or 0) + (stats.get("timeout_count", 0) or 0)

        should_break = error_count >= error_threshold

        if should_break:
            self._logger.warning(
                "circuit_breaker_triggered",
                tool_name=tool_name,
                error_count=error_count,
                threshold=error_threshold,
                window_minutes=window_minutes
            )

        return should_break

    async def get_error_patterns(
        self,
        tool_name: str,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get error patterns for a tool.

        Args:
            tool_name: Tool to analyze
            limit: Maximum errors to analyze

        Returns:
            Dictionary with error pattern analysis
        """
        errors = await self.repository.get_recent_errors(tool_name, limit)

        if not errors:
            return {
                "tool_name": tool_name,
                "total_errors": 0,
                "patterns": []
            }

        # Group by error type
        error_types: Dict[str, int] = {}
        for error in errors:
            error_type = error.error_type or "unknown"
            error_types[error_type] = error_types.get(error_type, 0) + 1

        # Sort by frequency
        patterns = [
            {"error_type": k, "count": v}
            for k, v in sorted(error_types.items(), key=lambda x: -x[1])
        ]

        return {
            "tool_name": tool_name,
            "total_errors": len(errors),
            "patterns": patterns,
            "recent_messages": [e.error_message for e in errors[:5] if e.error_message]
        }

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Get a dashboard-friendly summary of tool health.

        Returns:
            Dictionary with dashboard data
        """
        system_report = await self.check_all_tools_health(period_hours=24)

        # Get slow executions
        slow_executions = await self.repository.get_slow_executions(
            threshold_ms=self.LATENCY_DEGRADED_MS,
            limit=10
        )

        return {
            "overall_status": system_report.status.value,
            "summary": system_report.summary,
            "tools_needing_attention": [
                r.to_dict() for r in system_report.tool_reports
                if r.status != HealthStatus.HEALTHY
            ],
            "slow_executions": [
                {
                    "tool_name": e.tool_name,
                    "execution_time_ms": e.execution_time_ms,
                    "recorded_at": e.recorded_at.isoformat() if e.recorded_at else None
                }
                for e in slow_executions
            ],
            "checked_at": system_report.checked_at.isoformat()
        }

    async def get_health_summary(self) -> Dict[str, Any]:
        """
        Get health summary formatted for gRPC service.

        Returns:
            Dictionary with per-tool health data suitable for
            the GovernanceService gRPC endpoint.
        """
        system_report = await self.check_all_tools_health(period_hours=24)

        # Build per-tool health dictionary
        tools = {}
        for report in system_report.tool_reports:
            tools[report.tool_name] = {
                "status": report.status.value,
                "success_rate": report.success_rate,
                "last_used": report.checked_at,
                "avg_latency_ms": report.avg_latency_ms,
                "total_calls": report.total_calls,
                "recent_errors": report.recent_errors,
            }

        return {
            "overall_status": system_report.status.value,
            "tools": tools,
            "checked_at": system_report.checked_at.isoformat()
        }

    async def get_tool_health(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get health info for a specific tool, formatted for gRPC.

        Per P2 (Reliability): Fetches actual execution data rather than estimating.
        Per P6 (Observable): Provides real timestamps for last success/failure.

        Args:
            tool_name: Name of the tool to check

        Returns:
            Dictionary with tool health data or None if tool not found
        """
        report = await self.check_tool_health(tool_name, period_hours=24)

        if report.status == HealthStatus.UNKNOWN and report.total_calls == 0:
            return None

        # Get recent executions for accurate last_success/last_failure
        recent = await self.repository.get_recent_executions(tool_name, limit=100)

        last_success = None
        last_failure = None
        last_error = None
        successful_calls = 0
        failed_calls = 0

        for metric in recent:
            if metric.status == "success":
                successful_calls += 1
                if last_success is None:
                    last_success = metric.recorded_at
            else:
                failed_calls += 1
                if last_failure is None:
                    last_failure = metric.recorded_at
                    last_error = metric.error_message

        return {
            "status": report.status.value,
            "total_calls": report.total_calls,
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "success_rate": report.success_rate,
            "avg_latency_ms": report.avg_latency_ms,
            "last_success": last_success,
            "last_failure": last_failure,
            "last_error": last_error,
        }
