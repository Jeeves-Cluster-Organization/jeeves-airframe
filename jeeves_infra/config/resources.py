"""Resource limits configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceConfig:
    """Resource limits for process execution.

    These limits are enforced by the ResourceTracker and/or Go kernel.

    Attributes:
        max_llm_calls: Maximum LLM API calls per process
        max_tool_calls: Maximum tool invocations per process
        max_agent_hops: Maximum agent-to-agent transitions
        max_iterations: Maximum pipeline iterations
        timeout_seconds: Process execution timeout
    """

    max_llm_calls: int = 100
    max_tool_calls: int = 200
    max_agent_hops: int = 21
    max_iterations: int = 50
    timeout_seconds: int = 300

    @classmethod
    def default(cls) -> "ResourceConfig":
        """Create config with default limits."""
        return cls()

    @classmethod
    def from_env(cls) -> "ResourceConfig":
        """Load configuration from environment variables.

        Environment variables:
            RESOURCE_MAX_LLM_CALLS: Max LLM calls (default: 100)
            RESOURCE_MAX_TOOL_CALLS: Max tool calls (default: 200)
            RESOURCE_MAX_AGENT_HOPS: Max agent hops (default: 21)
            RESOURCE_MAX_ITERATIONS: Max iterations (default: 50)
            RESOURCE_TIMEOUT_SECONDS: Timeout (default: 300)

        Returns:
            ResourceConfig instance populated from environment
        """
        return cls(
            max_llm_calls=int(os.getenv("RESOURCE_MAX_LLM_CALLS", "100")),
            max_tool_calls=int(os.getenv("RESOURCE_MAX_TOOL_CALLS", "200")),
            max_agent_hops=int(os.getenv("RESOURCE_MAX_AGENT_HOPS", "21")),
            max_iterations=int(os.getenv("RESOURCE_MAX_ITERATIONS", "50")),
            timeout_seconds=int(os.getenv("RESOURCE_TIMEOUT_SECONDS", "300")),
        )

    @classmethod
    def unlimited(cls) -> "ResourceConfig":
        """Create config with very high limits.

        Useful for testing or development.
        """
        return cls(
            max_llm_calls=999999,
            max_tool_calls=999999,
            max_agent_hops=999999,
            max_iterations=999999,
            timeout_seconds=86400,  # 24 hours
        )

    def to_quota_dict(self) -> dict:
        """Convert to dictionary format for kernel quota.

        Returns:
            Dict compatible with kernel CreateProcess quota parameter
        """
        return {
            "max_llm_calls": self.max_llm_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_agent_hops": self.max_agent_hops,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
        }
