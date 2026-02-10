"""
Vertical Registry - Minimal registration mechanism.

RULE 1: Core must not import verticals.
RULE 2: Verticals must not import memory/repositories.
RULE 3: Shared modules must not import agents.

Verticals register via explicit bootstrap, not import side-effects.
"""
from dataclasses import dataclass, field
from typing import Dict, Type, List, Callable, Any


@dataclass
class Vertical:
    """A vertical registers agents, tools, and context builders."""
    id: str
    agents: Dict[str, Type] = field(default_factory=dict)
    tools: List[Callable] = field(default_factory=list)
    context_builders: Dict[str, Callable] = field(default_factory=dict)


_verticals: Dict[str, Vertical] = {}


def register(vertical: Vertical) -> None:
    """Register a vertical with the core."""
    _verticals[vertical.id] = vertical


def get(vertical_id: str) -> Vertical:
    """Get a registered vertical by ID."""
    if vertical_id not in _verticals:
        raise KeyError(f"Vertical '{vertical_id}' not registered. Did you call bootstrap?")
    return _verticals[vertical_id]


def get_agent_class(vertical_id: str, agent_name: str) -> Type:
    """Get an agent class from a registered vertical."""
    vertical = get(vertical_id)
    if agent_name not in vertical.agents:
        raise KeyError(f"Agent '{agent_name}' not found in vertical '{vertical_id}'")
    return vertical.agents[agent_name]


def list_verticals() -> List[str]:
    """List all registered vertical IDs."""
    return list(_verticals.keys())


def is_registered(vertical_id: str) -> bool:
    """Check if a vertical is registered."""
    return vertical_id in _verticals
