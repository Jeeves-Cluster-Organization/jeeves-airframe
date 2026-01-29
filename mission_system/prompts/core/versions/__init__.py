"""
Prompt versions for mission system agents.

Per Engineering Plan v4.2: No _v1 suffix - single version per agent.
Prompts are automatically registered when modules are imported.

Generic Pipeline Prompts:
- perception: Session state loading (PerceptionAgent)
- intent: Intent extraction and clarification (IntentAgent)
- planner: Plan generation and tool selection (PlannerAgent)
- traverser: Execution traversal (TraverserAgent)
- synthesizer: Understanding synthesis (SynthesizerAgent)
- critic: Response validation and hallucination detection (CriticAgent)
- integration: Final response building (IntegrationAgent)

Capability-specific prompts are registered via CapabilityResourceRegistry.
"""
