"""Jeeves Memory Module - Memory services (L1-L7) for the Jeeves system.

Provides:
- Event sourcing and domain events (L2)
- Semantic chunking and search (L3)
- Session state management (L4)
- Tool health governance (L7)
- CommBus handler registration

Constitutional Reference:
- Memory Module CONSTITUTION: Memory types and protocols in protocols
"""

from memory_module.handlers import register_memory_handlers, reset_cached_services

__all__ = [
    "register_memory_handlers",
    "reset_cached_services",
]
