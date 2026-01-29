"""Configuration dataclasses for jeeves_infra.

This module provides typed configuration classes for:
- Kernel connection settings (KernelConfig)
- Resource limits (ResourceConfig)

Example usage:
    from jeeves_infra.config import KernelConfig, ResourceConfig

    # Load from environment
    kernel_config = KernelConfig.from_env()
    resource_config = ResourceConfig.from_env()

    # Or use defaults
    kernel_config = KernelConfig()
    resource_config = ResourceConfig.default()
"""

from jeeves_infra.config.kernel import KernelConfig
from jeeves_infra.config.resources import ResourceConfig

__all__ = [
    "KernelConfig",
    "ResourceConfig",
]
