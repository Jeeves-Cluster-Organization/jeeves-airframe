"""
Safety guardrails (Constitutional P1 compliant).

These rules ensure safe operation across different capability modes.
The safety block adapts based on whether the capability is read-only
or has write permissions.
"""


def get_safety_block(is_readonly: bool = True) -> str:
    """Get safety block appropriate for capability mode.

    Args:
        is_readonly: Whether the capability is read-only (no modifications).
                    Defaults to True for safety.

    Returns:
        Safety block text appropriate for the capability mode.
    """
    if is_readonly:
        return """Safety Rules:
- All operations are READ-ONLY - you cannot modify files
- When uncertain, ask for clarification rather than guess
- Never claim code exists without having read it
- Respect context bounds to prevent runaway exploration
- If a query is too broad, suggest narrowing the scope
- Acknowledge when the codebase is too large to fully analyze"""
    else:
        return """Safety Rules:
- You may modify files when instructed - be careful and deliberate
- Always confirm destructive operations before executing
- When uncertain, ask for clarification rather than guess
- Never claim code exists without having read it
- Respect context bounds to prevent runaway exploration
- If a query is too broad, suggest narrowing the scope
- Acknowledge when the codebase is too large to fully analyze
- Create backups or use version control for significant changes"""


# Default block for backward compatibility (read-only mode)
SAFETY_BLOCK = get_safety_block(is_readonly=True)
