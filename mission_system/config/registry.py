"""Configuration Registry - Generic config injection for capabilities.

This module provides the ConfigRegistry implementation that capabilities use
to register and retrieve their configurations at runtime.

Architecture:
    - Capabilities OWN their config types (e.g., LanguageConfig in code-analyser)
    - Mission system provides the registry mechanism
    - Tools receive config via dependency injection, not globals

Usage:
    # At capability bootstrap (e.g., in code-analyser wiring.py)
    from config.language_config import LanguageConfig
    registry = ConfigRegistry()
    registry.register("language_config", LanguageConfig())

    # In tools (receive registry via dependency injection)
    def some_tool(registry: ConfigRegistryProtocol):
        config = registry.get("language_config")
        if config:
            extensions = config.code_extensions

Standard Keys:
    - "language_config": Language configuration for code analysis capability
    - Future: "agent_config", "tool_access_config", etc.
"""

from typing import Any, Dict, List, Optional


class ConfigRegistry:
    """Implementation of ConfigRegistryProtocol.

    Thread-safe configuration registry that capabilities use to register
    their configs at bootstrap time.

    Attributes:
        _configs: Internal storage mapping keys to config objects
    """

    def __init__(self) -> None:
        """Initialize an empty config registry."""
        self._configs: Dict[str, Any] = {}

    def register(self, key: str, config: Any) -> None:
        """Register a configuration by key.

        Args:
            key: Unique configuration key (e.g., "language_config")
            config: Configuration object (capability-defined type)

        Raises:
            ValueError: If key is empty
        """
        if not key:
            raise ValueError("Config key cannot be empty")
        self._configs[key] = config

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration by key.

        Args:
            key: Configuration key
            default: Default value if not found

        Returns:
            Configuration object or default
        """
        return self._configs.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a configuration is registered.

        Args:
            key: Configuration key

        Returns:
            True if registered
        """
        return key in self._configs

    def keys(self) -> List[str]:
        """List all registered configuration keys.

        Returns:
            List of registered keys
        """
        return list(self._configs.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Export all configs as dictionary.

        Returns:
            Dict mapping keys to configs (shallow copy)
        """
        return dict(self._configs)

    def __repr__(self) -> str:
        """String representation showing registered keys."""
        return f"ConfigRegistry(keys={self.keys()})"


# Standard config key constants
class ConfigKeys:
    """Standard configuration key constants.

    Using constants prevents typos and enables IDE autocomplete.
    """

    LANGUAGE_CONFIG = "language_config"
    # Future keys:
    # AGENT_CONFIG = "agent_config"
    # TOOL_ACCESS_CONFIG = "tool_access_config"
    # MEMORY_CONFIG = "memory_config"


# Global registry instance (for simple cases)
# Prefer dependency injection over this global
_global_registry: Optional[ConfigRegistry] = None


def get_config_registry() -> ConfigRegistry:
    """Get the global config registry instance.

    Creates a new registry if none exists.

    Note: Prefer dependency injection over this global getter.
    This is provided for backward compatibility and simple use cases.

    Returns:
        Global ConfigRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ConfigRegistry()
    return _global_registry


def set_config_registry(registry: ConfigRegistry) -> None:
    """Set the global config registry instance.

    Use at bootstrap time to inject a pre-configured registry.

    Args:
        registry: ConfigRegistry to use as global instance
    """
    global _global_registry
    _global_registry = registry


def reset_config_registry() -> None:
    """Reset the global config registry.

    Primarily for testing purposes.
    """
    global _global_registry
    _global_registry = None
