"""
Core prompt building blocks for agent pipelines.

This module provides shared prompt components that ensure consistency
across all agents per Constitutional Amendment X.

Blocks:
- identity_block: Agent identity and persona (capability-agnostic)
- style_block: Response voice and formatting rules
- role_invariants: Universal constraints for all agents
- safety_block: Safety guardrails (mode-aware)

Usage:
    from mission_system.prompts.core import IDENTITY_BLOCK, STYLE_BLOCK, ROLE_INVARIANTS, SAFETY_BLOCK
    # or
    from mission_system.prompts.core.blocks import IDENTITY_BLOCK

    prompt = f'''
    {IDENTITY_BLOCK}

    **Your Role:** Planner Agent

    {STYLE_BLOCK}

    {ROLE_INVARIANTS}

    {SAFETY_BLOCK}
    '''

    # For capability-aware blocks:
    from mission_system.prompts.core.blocks import get_identity_block, get_safety_block

    prompt = f'''
    {get_identity_block("My Capability Agent")}
    {get_safety_block(is_readonly=False)}
    '''
"""

from .identity_block import IDENTITY_BLOCK, get_identity_block
from .style_block import STYLE_BLOCK
from .role_invariants import ROLE_INVARIANTS
from .safety_block import SAFETY_BLOCK, get_safety_block

__all__ = [
    "IDENTITY_BLOCK",
    "get_identity_block",
    "STYLE_BLOCK",
    "ROLE_INVARIANTS",
    "SAFETY_BLOCK",
    "get_safety_block",
]
