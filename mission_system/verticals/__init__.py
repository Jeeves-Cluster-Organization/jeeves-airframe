"""Verticals package - Registration mechanism for vertical services.

A vertical is a self-contained domain service (e.g., Code Analysis) that
registers its agents, tools, and context builders with the core.
"""

from mission_system.verticals.registry import (
    Vertical,
    register,
    get,
    get_agent_class,
    list_verticals,
    is_registered,
)

__all__ = [
    "Vertical",
    "register",
    "get",
    "get_agent_class",
    "list_verticals",
    "is_registered",
]
