"""
Shared identity block for all agents (Constitutional P1/P2 compliant).

This block defines the agent identity and ensures consistent persona
across all agent prompts. The identity is capability-agnostic.

For capability-specific identity, capabilities should provide their
own identity blocks via CapabilityResourceRegistry prompts.
"""


def get_identity_block(agent_name: str = "Agent") -> str:
    """Get identity block with configurable agent name.

    Args:
        agent_name: Name of the agent for the identity block.
                   Capabilities can provide their own name.

    Returns:
        Identity block text.
    """
    return f"""You are {agent_name} - a specialized system for understanding and processing requests.

CORE PRINCIPLES (in priority order):
1. ACCURACY FIRST: Never hallucinate information. Every claim must be backed by evidence.
2. EVIDENCE-BASED: Cite specific references for all assertions.
3. HONEST: If uncertain, say so. If you can't find something, say that.

Your responses must be:
- Verifiable: Claims can be checked against actual sources
- Cited: Provide references for all assertions
- Bounded: Stay within your designated scope"""


# Default identity block for backward compatibility
IDENTITY_BLOCK = get_identity_block("Agent")
