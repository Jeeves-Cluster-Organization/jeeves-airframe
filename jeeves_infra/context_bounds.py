"""
Context Bounds - Access via AppContext.

Per ADR-001 Decision 3: No global state.
Context bounds are accessed via AppContext.get_context_bounds().

Usage:
    from jeeves_infra.context import AppContext

    # AppContext is passed via DI
    def my_function(context: AppContext):
        bounds = context.get_context_bounds()
        max_tokens = bounds.max_context_tokens
"""

# This module is kept for backward compatibility of imports only.
# The actual ContextBounds type is in jeeves_core.types
from jeeves_infra.protocols import ContextBounds

__all__ = ["ContextBounds"]
