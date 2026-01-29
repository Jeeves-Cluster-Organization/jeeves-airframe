"""Jeeves Infrastructure Runtime - Agent and pipeline execution.

This module contains the runtime components for executing agents
and pipelines. Types are from jeeves_core (Python bindings to Go types).

Usage:
    from jeeves_infra.runtime import Agent, PipelineRunner
    from jeeves_infra.runtime import create_pipeline_runner, create_envelope
"""

from jeeves_infra.runtime.agents import (
    # Protocols
    LLMProvider,
    ToolExecutor,
    Logger,
    Persistence,
    PromptRegistry,
    EventContext,
    # Type aliases
    LLMProviderFactory,
    PreProcessHook,
    PostProcessHook,
    MockHandler,
    # Classes
    AgentFeatures,
    Agent,
    PipelineRunner,
    OptionalCheckpoint,
    # Factories
    create_pipeline_runner,
    create_envelope,
)

__all__ = [
    # Protocols
    "LLMProvider",
    "ToolExecutor",
    "Logger",
    "Persistence",
    "PromptRegistry",
    "EventContext",
    # Type aliases
    "LLMProviderFactory",
    "PreProcessHook",
    "PostProcessHook",
    "MockHandler",
    # Classes
    "AgentFeatures",
    "Agent",
    "PipelineRunner",
    "OptionalCheckpoint",
    # Factories
    "create_pipeline_runner",
    "create_envelope",
]
