"""
Centralized prompt management for Mission System.

Constitutional Alignment:
- P1 (NLP-First): Intent-based prompts, no pattern matching
- P5 (Deterministic Spine): Prompts are contracts at LLM boundaries
- P6 (Observable): Version tracking, usage logging

Layer Extraction Compliant:
    Capability-specific prompts are owned by capabilities and registered
    via register_capability() at startup. This module only imports generic prompts.

Usage:
    from mission_system.prompts.core.registry import PromptRegistry

    registry = PromptRegistry.get_instance()
    prompt = registry.get("planner.tool_selection", version="1.0")
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

# Import GENERIC prompt version modules to ensure they're registered
# Capability-specific prompts (e.g., code_analysis) are registered by capabilities
# via CapabilityResourceRegistry at application startup
try:
    from mission_system.prompts.core.versions import confirmation  # noqa: F401
except (ImportError, FileNotFoundError):
    pass  # Ignore import errors to prevent blocking other prompts

try:
    from mission_system.prompts.core.versions import intent  # noqa: F401
except (ImportError, FileNotFoundError):
    pass

try:
    from mission_system.prompts.core.versions import planner  # noqa: F401
except (ImportError, FileNotFoundError):
    pass

try:
    from mission_system.prompts.core.versions import critic  # noqa: F401
except (ImportError, FileNotFoundError):
    pass
