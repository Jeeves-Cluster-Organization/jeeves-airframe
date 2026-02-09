"""
Centralized prompt management for Mission System.

Provides PromptRegistry for versioned prompt templates and shared prompt blocks.
Capabilities register their own prompts via @register_prompt at startup.
"""

from mission_system.prompts.core.registry import PromptRegistry, PromptVersion, register_prompt
from mission_system.prompts.core.blocks import (
    IDENTITY_BLOCK,
    get_identity_block,
    STYLE_BLOCK,
    ROLE_INVARIANTS,
    SAFETY_BLOCK,
    get_safety_block,
)

__all__ = [
    "PromptRegistry",
    "PromptVersion",
    "register_prompt",
    "IDENTITY_BLOCK",
    "get_identity_block",
    "STYLE_BLOCK",
    "ROLE_INVARIANTS",
    "SAFETY_BLOCK",
    "get_safety_block",
]
