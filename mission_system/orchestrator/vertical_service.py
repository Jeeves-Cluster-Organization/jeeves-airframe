"""Generic vertical orchestration - no vertical-specific code.

This module provides generic functions for running any registered vertical.
The orchestrator uses vertical_id to look up agents and context builders.

RULE 1: Core must not import verticals.
This file does NOT import from agents/code_analysis/ or tools/code_analysis/.
"""
from typing import Type, Dict, Any, Callable, Optional

from mission_system.verticals.registry import get, get_agent_class
from mission_system.adapters import get_logger


def run_stage(vertical_id: str, stage: str, envelope: Any) -> Any:
    """Run a stage for any registered vertical.

    Args:
        vertical_id: ID of the registered vertical (from CapabilityResourceRegistry)
        stage: Name of the stage/agent to run (e.g., "perception", "planner")
        envelope: The Envelope to process

    Returns:
        The agent's result
    """
    AgentCls = get_agent_class(vertical_id, stage)
    agent = AgentCls()
    return agent.process(envelope)


def get_vertical_agents(vertical_id: str) -> Dict[str, Type]:
    """Get all agents for a vertical.

    Args:
        vertical_id: ID of the registered vertical

    Returns:
        Dict mapping stage names to agent classes
    """
    return get(vertical_id).agents


def get_context_builder(vertical_id: str, stage: str) -> Optional[Callable]:
    """Get context builder for a stage.

    Args:
        vertical_id: ID of the registered vertical
        stage: Name of the stage (e.g., "perception", "intent")

    Returns:
        Context builder function or None if not found
    """
    vertical = get(vertical_id)
    return vertical.context_builders.get(stage)


def get_vertical_tools(vertical_id: str) -> list:
    """Get tools for a vertical.

    Args:
        vertical_id: ID of the registered vertical

    Returns:
        List of tool callables
    """
    return get(vertical_id).tools


def instantiate_agents(
    vertical_id: str,
    db: Any,
    use_mock: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Instantiate all agents for a vertical.

    This is a helper for services that need to create agent instances.

    Args:
        vertical_id: ID of the registered vertical
        db: Database client to pass to agents
        use_mock: Whether to use mock mode for LLM agents
        **kwargs: Additional kwargs passed to agent constructors

    Returns:
        Dict mapping stage names to agent instances
    """
    vertical = get(vertical_id)
    instances = {}

    for stage, AgentCls in vertical.agents.items():
        try:
            # Try to instantiate with common parameters
            instances[stage] = AgentCls(db=db, use_mock=use_mock, **kwargs)
        except TypeError:
            # Fall back to just db if use_mock not supported
            try:
                instances[stage] = AgentCls(db=db, **kwargs)
            except TypeError:
                # Final fallback - no args
                instances[stage] = AgentCls()

    return instances
