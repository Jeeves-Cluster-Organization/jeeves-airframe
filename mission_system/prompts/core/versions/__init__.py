"""
Prompt versions — framework defaults only.

Domain-specific prompts (planner, critic, intent, confirmation) have been
removed from airframe. Capabilities register their own prompts via
CapabilityResourceRegistry and the @register_prompt decorator.

See: mission_system/prompts/core/registry.py for the registration mechanism.
"""
