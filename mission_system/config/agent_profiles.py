"""
Agent Profiles - Generic per-agent configuration types.

This module provides the generic configuration types for agent profiles.
Capabilities own their specific agent definitions and register them at startup.

Constitutional Reference:
    - Mission System Constitution: Provides generic config mechanisms
    - Capability Constitution R6: Domain Config Ownership

IMPORTANT: AGENT_PROFILES has been moved to capability layer.
    See: jeeves-capability-code-analyser/config/llm_config.py
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class LLMProfile:
    """LLM configuration for an agent role.

    Generic type - capabilities define specific values.
    """
    model_name: str = "qwen2.5-7b-instruct-q4_k_m"
    temperature: float = 0.3
    max_tokens: int = 2000
    context_window: int = 16384
    timeout_seconds: int = 120


@dataclass
class ThresholdProfile:
    """Confidence thresholds for an agent.

    Generic type - capabilities define specific values.
    """
    clarification_threshold: float = 0.7
    approval_threshold: float = 0.8
    high_confidence: float = 0.85
    medium_confidence: float = 0.75
    low_confidence: float = 0.6
    default_confidence: float = 0.5


@dataclass
class AgentProfile:
    """Complete configuration profile for an agent.

    Generic type - capabilities define specific profiles.

    Example:
        profile = AgentProfile(
            role="planner",
            llm=LLMProfile(temperature=0.3),
            thresholds=ThresholdProfile(clarification_threshold=0.7),
        )
    """
    role: str
    llm: Optional[LLMProfile] = None
    thresholds: ThresholdProfile = field(default_factory=ThresholdProfile)
    latency_budget_ms: int = 30000
    retry_limit: int = 2

    @property
    def has_llm(self) -> bool:
        return self.llm is not None


# =============================================================================
# GENERIC HELPER FUNCTIONS
# =============================================================================

def get_agent_profile(
    profiles: Dict[str, AgentProfile],
    role: str
) -> Optional[AgentProfile]:
    """Get profile for agent role from a profiles dict.

    Args:
        profiles: Dictionary of agent profiles
        role: Agent role name (e.g., "planner", "critic")

    Returns:
        AgentProfile or None if not found
    """
    return profiles.get(role)


def get_llm_profile(
    profiles: Dict[str, AgentProfile],
    role: str
) -> Optional[LLMProfile]:
    """Get LLM config for agent role from a profiles dict.

    Args:
        profiles: Dictionary of agent profiles
        role: Agent role name

    Returns:
        LLMProfile or None if agent has no LLM
    """
    profile = profiles.get(role)
    return profile.llm if profile else None


def get_thresholds(
    profiles: Dict[str, AgentProfile],
    role: str
) -> ThresholdProfile:
    """Get thresholds for agent role from a profiles dict.

    Args:
        profiles: Dictionary of agent profiles
        role: Agent role name

    Returns:
        ThresholdProfile (defaults if role not found)
    """
    profile = profiles.get(role)
    return profile.thresholds if profile else ThresholdProfile()


def get_latency_budget(
    profiles: Dict[str, AgentProfile],
    role: str
) -> int:
    """Get latency budget in ms for agent role from a profiles dict.

    Args:
        profiles: Dictionary of agent profiles
        role: Agent role name

    Returns:
        Latency budget in milliseconds
    """
    profile = profiles.get(role)
    return profile.latency_budget_ms if profile else 30000


__all__ = [
    "LLMProfile",
    "ThresholdProfile",
    "AgentProfile",
    "get_agent_profile",
    "get_llm_profile",
    "get_thresholds",
    "get_latency_budget",
]
