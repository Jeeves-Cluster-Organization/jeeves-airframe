"""Independent resource tracking for process execution.

This module provides ResourceTracker, which tracks resource usage
independent of the LLM Gateway. It can work with or without a
kernel_client connection.

Example usage:
    # With kernel (centralized tracking)
    tracker = ResourceTracker(kernel_client=client, config=resource_config)

    # Without kernel (local tracking)
    tracker = ResourceTracker(config=resource_config)

    # Record usage
    exceeded = await tracker.record_llm_call(pid="proc-1", tokens_in=100)
    if exceeded:
        raise QuotaExceededError(exceeded)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

from jeeves_infra.config.resources import ResourceConfig

if TYPE_CHECKING:
    from jeeves_infra.kernel_client import KernelClient, QuotaCheckResult

logger = logging.getLogger(__name__)


@dataclass
class ResourceUsage:
    """Local tracking of resource usage for a single process."""

    llm_calls: int = 0
    tool_calls: int = 0
    agent_hops: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    iterations: int = 0


@dataclass
class LocalQuotaResult:
    """Result of local quota check."""

    within_bounds: bool
    exceeded_reason: Optional[str] = None
    llm_calls_remaining: int = 0
    tool_calls_remaining: int = 0
    agent_hops_remaining: int = 0


class ResourceTracker:
    """Track resource usage independent of LLM Gateway.

    Works in two modes:
    1. With kernel_client: Reports to Go kernel for centralized tracking
    2. Without kernel_client: Local in-memory tracking with config limits

    The tracker provides a consistent interface regardless of mode,
    allowing graceful degradation when kernel is unavailable.
    """

    def __init__(
        self,
        kernel_client: Optional["KernelClient"] = None,
        config: Optional[ResourceConfig] = None,
    ):
        """Initialize ResourceTracker.

        Args:
            kernel_client: Optional kernel client for centralized tracking
            config: Resource limits configuration (uses defaults if not provided)
        """
        self._kernel = kernel_client
        self._config = config or ResourceConfig.default()
        self._local_usage: Dict[str, ResourceUsage] = {}

    @property
    def has_kernel(self) -> bool:
        """Check if kernel client is available."""
        return self._kernel is not None

    @property
    def config(self) -> ResourceConfig:
        """Get the resource configuration."""
        return self._config

    async def record_llm_call(
        self,
        pid: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> Optional[str]:
        """Record an LLM call for a process.

        Args:
            pid: Process ID
            tokens_in: Number of input tokens
            tokens_out: Number of output tokens

        Returns:
            Exceeded reason string if quota hit, None otherwise
        """
        if self._kernel:
            try:
                return await self._kernel.record_llm_call(pid, tokens_in, tokens_out)
            except Exception as e:
                logger.warning(f"Kernel record_llm_call failed, using local tracking: {e}")
                # Fall through to local tracking

        return self._local_record(
            pid,
            llm_calls=1,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    async def record_tool_call(self, pid: str) -> Optional[str]:
        """Record a tool call for a process.

        Args:
            pid: Process ID

        Returns:
            Exceeded reason string if quota hit, None otherwise
        """
        if self._kernel:
            try:
                return await self._kernel.record_tool_call(pid)
            except Exception as e:
                logger.warning(f"Kernel record_tool_call failed, using local tracking: {e}")

        return self._local_record(pid, tool_calls=1)

    async def record_agent_hop(self, pid: str) -> Optional[str]:
        """Record an agent hop for a process.

        Args:
            pid: Process ID

        Returns:
            Exceeded reason string if quota hit, None otherwise
        """
        if self._kernel:
            try:
                return await self._kernel.record_agent_hop(pid)
            except Exception as e:
                logger.warning(f"Kernel record_agent_hop failed, using local tracking: {e}")

        return self._local_record(pid, agent_hops=1)

    async def record_iteration(self, pid: str) -> Optional[str]:
        """Record a pipeline iteration for a process.

        Args:
            pid: Process ID

        Returns:
            Exceeded reason string if quota hit, None otherwise
        """
        # Kernel doesn't track iterations directly, use local
        return self._local_record(pid, iterations=1)

    async def check_quota(self, pid: str) -> LocalQuotaResult:
        """Check quota status for a process.

        Args:
            pid: Process ID

        Returns:
            QuotaCheckResult with bounds status
        """
        if self._kernel:
            try:
                result = await self._kernel.check_quota(pid)
                return LocalQuotaResult(
                    within_bounds=result.within_bounds,
                    exceeded_reason=result.exceeded_reason,
                    llm_calls_remaining=result.llm_calls_remaining,
                    tool_calls_remaining=result.tool_calls_remaining,
                    agent_hops_remaining=result.agent_hops_remaining,
                )
            except Exception as e:
                logger.warning(f"Kernel check_quota failed, using local check: {e}")

        return self._local_check(pid)

    def get_usage(self, pid: str) -> ResourceUsage:
        """Get current usage for a process (local tracking only).

        Args:
            pid: Process ID

        Returns:
            ResourceUsage for the process
        """
        return self._local_usage.get(pid, ResourceUsage())

    def reset(self, pid: str) -> None:
        """Reset usage tracking for a process.

        Args:
            pid: Process ID
        """
        if pid in self._local_usage:
            del self._local_usage[pid]

    def reset_all(self) -> None:
        """Reset all local usage tracking."""
        self._local_usage.clear()

    def _local_record(
        self,
        pid: str,
        llm_calls: int = 0,
        tool_calls: int = 0,
        agent_hops: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        iterations: int = 0,
    ) -> Optional[str]:
        """Record usage locally and check against limits.

        Returns:
            Exceeded reason if any limit hit, None otherwise
        """
        usage = self._local_usage.setdefault(pid, ResourceUsage())

        # Update counts
        usage.llm_calls += llm_calls
        usage.tool_calls += tool_calls
        usage.agent_hops += agent_hops
        usage.tokens_in += tokens_in
        usage.tokens_out += tokens_out
        usage.iterations += iterations

        # Check limits
        if usage.llm_calls > self._config.max_llm_calls:
            return f"max_llm_calls exceeded ({usage.llm_calls}/{self._config.max_llm_calls})"

        if usage.tool_calls > self._config.max_tool_calls:
            return f"max_tool_calls exceeded ({usage.tool_calls}/{self._config.max_tool_calls})"

        if usage.agent_hops > self._config.max_agent_hops:
            return f"max_agent_hops exceeded ({usage.agent_hops}/{self._config.max_agent_hops})"

        if usage.iterations > self._config.max_iterations:
            return f"max_iterations exceeded ({usage.iterations}/{self._config.max_iterations})"

        return None

    def _local_check(self, pid: str) -> LocalQuotaResult:
        """Check quota locally.

        Returns:
            LocalQuotaResult with remaining counts
        """
        usage = self._local_usage.get(pid, ResourceUsage())

        llm_remaining = self._config.max_llm_calls - usage.llm_calls
        tool_remaining = self._config.max_tool_calls - usage.tool_calls
        hops_remaining = self._config.max_agent_hops - usage.agent_hops

        exceeded_reason = None
        within_bounds = True

        if llm_remaining <= 0:
            exceeded_reason = "max_llm_calls exceeded"
            within_bounds = False
        elif tool_remaining <= 0:
            exceeded_reason = "max_tool_calls exceeded"
            within_bounds = False
        elif hops_remaining <= 0:
            exceeded_reason = "max_agent_hops exceeded"
            within_bounds = False

        return LocalQuotaResult(
            within_bounds=within_bounds,
            exceeded_reason=exceeded_reason,
            llm_calls_remaining=max(0, llm_remaining),
            tool_calls_remaining=max(0, tool_remaining),
            agent_hops_remaining=max(0, hops_remaining),
        )


__all__ = [
    "ResourceTracker",
    "ResourceUsage",
    "LocalQuotaResult",
]
