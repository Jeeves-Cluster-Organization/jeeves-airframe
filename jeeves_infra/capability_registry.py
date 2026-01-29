"""Capability LLM Configuration Registry.

Provides a registry for capability-owned agent LLM configurations.
Capabilities register their agent configurations at startup, and
infrastructure queries the registry instead of having hardcoded agent names.

Constitutional Reference:
    - Infrastructure provides transport, not business logic
    - Capability Constitution R6: Domain Config Ownership
    - docs/CONSTITUTION.md: Layer separation enforcement

Usage:
    # At capability startup (in jeeves-capability-my-capability)
    from jeeves_infra.capability_registry import get_capability_registry
    from jeeves_infra.protocols import AgentLLMConfig

    registry = get_capability_registry()
    registry.register("my_capability", "my_agent", AgentLLMConfig(
        agent_name="my_agent",
        model="qwen2.5-7b-instruct-q4_k_m",
        temperature=0.3,
    ))

    # In infrastructure (factory.py)
    config = registry.get_agent_config("my_agent")
    if config:
        base_url = config.server_url or default_url
"""

import os
from typing import Dict, List, Optional, TYPE_CHECKING

from jeeves_infra.protocols import (
    AgentLLMConfig,
    DomainLLMRegistryProtocol,
    LoggerProtocol,
)
from jeeves_infra.logging import get_component_logger

if TYPE_CHECKING:
    pass


class DomainLLMRegistry:
    """Registry for capability-owned agent LLM configurations.

    Implements DomainLLMRegistryProtocol.

    This registry allows capabilities to own their agent configurations
    while infrastructure remains capability-agnostic. The registry supports
    environment variable overrides for backward compatibility during migration.

    Env Var Override Pattern:
        {AGENT_NAME}_MODEL -> config.model
        {AGENT_NAME}_TEMPERATURE -> config.temperature
        {AGENT_NAME}_SERVER_URL -> config.server_url
        {AGENT_NAME}_LLM_PROVIDER -> config.provider
    """

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        """Initialize the registry.

        Args:
            logger: Optional logger instance (ADR-001 DI)
        """
        self._logger = get_component_logger("capability_registry", logger)
        self._configs: Dict[str, AgentLLMConfig] = {}
        self._capability_agents: Dict[str, List[str]] = {}

    def register(
        self,
        capability_id: str,
        agent_name: str,
        config: AgentLLMConfig
    ) -> None:
        """Register an agent's LLM configuration.

        Args:
            capability_id: Identifier for the capability (e.g., "my_capability")
            agent_name: Name of the agent (e.g., "my_agent")
            config: LLM configuration for the agent
        """
        # Apply environment variable overrides
        config = self._apply_env_overrides(agent_name, config)

        self._configs[agent_name] = config

        if capability_id not in self._capability_agents:
            self._capability_agents[capability_id] = []
        if agent_name not in self._capability_agents[capability_id]:
            self._capability_agents[capability_id].append(agent_name)

        self._logger.info(
            "agent_config_registered",
            capability_id=capability_id,
            agent_name=agent_name,
            model=config.model,
            temperature=config.temperature,
            server_url=config.server_url,
            provider=config.provider,
        )

    def _apply_env_overrides(
        self,
        agent_name: str,
        config: AgentLLMConfig
    ) -> AgentLLMConfig:
        """Apply environment variable overrides to config.

        Supports backward compatibility with existing env var patterns.

        Args:
            agent_name: Name of the agent
            config: Base configuration

        Returns:
            Configuration with env var overrides applied
        """
        prefix = agent_name.upper()

        # Model override
        model_env = os.getenv(f"{prefix}_MODEL")
        if model_env:
            config = AgentLLMConfig(
                agent_name=config.agent_name,
                model=model_env,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                server_url=config.server_url,
                provider=config.provider,
                timeout_seconds=config.timeout_seconds,
                context_window=config.context_window,
            )

        # Temperature override
        temp_env = os.getenv(f"{prefix}_TEMPERATURE")
        if temp_env:
            try:
                config = AgentLLMConfig(
                    agent_name=config.agent_name,
                    model=config.model,
                    temperature=float(temp_env),
                    max_tokens=config.max_tokens,
                    server_url=config.server_url,
                    provider=config.provider,
                    timeout_seconds=config.timeout_seconds,
                    context_window=config.context_window,
                )
            except ValueError:
                self._logger.warning(
                    "invalid_temperature_env_var",
                    agent_name=agent_name,
                    value=temp_env,
                )

        # Server URL override
        url_env = os.getenv(f"LLAMASERVER_{prefix}_URL")
        if url_env:
            config = AgentLLMConfig(
                agent_name=config.agent_name,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                server_url=url_env,
                provider=config.provider,
                timeout_seconds=config.timeout_seconds,
                context_window=config.context_window,
            )

        # Provider override
        provider_env = os.getenv(f"{prefix}_LLM_PROVIDER")
        if provider_env:
            config = AgentLLMConfig(
                agent_name=config.agent_name,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                server_url=config.server_url,
                provider=provider_env,
                timeout_seconds=config.timeout_seconds,
                context_window=config.context_window,
            )

        return config

    def get_agent_config(self, agent_name: str) -> Optional[AgentLLMConfig]:
        """Get configuration for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            AgentLLMConfig if registered, None otherwise
        """
        return self._configs.get(agent_name)

    def list_agents(self) -> List[str]:
        """List all registered agent names.

        Returns:
            List of agent names across all capabilities
        """
        return list(self._configs.keys())

    def get_capability_agents(self, capability_id: str) -> List[AgentLLMConfig]:
        """Get all agent configurations for a capability.

        Args:
            capability_id: Identifier for the capability

        Returns:
            List of AgentLLMConfig for the capability
        """
        agent_names = self._capability_agents.get(capability_id, [])
        return [self._configs[name] for name in agent_names if name in self._configs]

    def clear(self) -> None:
        """Clear all registered configurations.

        Primarily for testing purposes.
        """
        self._configs.clear()
        self._capability_agents.clear()
        self._logger.info("capability_registry_cleared")


# =============================================================================
# GLOBAL REGISTRY (Lazy Initialization)
# =============================================================================

_registry: Optional[DomainLLMRegistry] = None


def get_capability_registry() -> DomainLLMRegistry:
    """Get the global capability registry instance.

    Creates a new instance lazily if none exists.
    Prefer dependency injection over this global getter for testability.

    Returns:
        Global DomainLLMRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = DomainLLMRegistry()
    return _registry


def set_capability_registry(registry: DomainLLMRegistry) -> None:
    """Set the global capability registry instance.

    Use at bootstrap time to inject a pre-configured registry.
    Primarily for testing purposes.

    Args:
        registry: Registry instance to use as global
    """
    global _registry
    _registry = registry


def reset_capability_registry() -> None:
    """Reset the global capability registry instance.

    Forces re-creation on next get_capability_registry() call.
    Primarily for testing purposes.
    """
    global _registry
    _registry = None


# Type assertion for protocol compliance
def _assert_protocol_compliance() -> None:
    """Static assertion that DomainLLMRegistry implements the protocol."""
    registry: DomainLLMRegistryProtocol = DomainLLMRegistry()
    _ = registry  # Suppress unused variable warning
