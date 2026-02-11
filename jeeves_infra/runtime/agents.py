"""Agent PipelineRunner - Go-backed pipeline execution.

Architecture:
    Go (coreengine/)     - Envelope state, bounds checking, pipeline graph
    Python (this file)   - Agent execution, LLM calls, tool execution
    Bridge (client.py)   - JSON-over-stdio communication
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, AsyncIterator, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from jeeves_infra.protocols import Envelope, AgentConfig, PipelineConfig


# =============================================================================
# PROTOCOLS
# =============================================================================

class LLMProvider(Protocol):
    """Protocol for LLM providers."""
    async def complete(self, messages: List[Dict[str, str]], **kwargs) -> str:
        ...


class ToolExecutor(Protocol):
    """Protocol for tool execution."""
    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        ...


class Logger(Protocol):
    """Protocol for structured logging."""
    def info(self, event: str, **kwargs) -> None: ...
    def warn(self, event: str, **kwargs) -> None: ...
    def error(self, event: str, **kwargs) -> None: ...
    def bind(self, **kwargs) -> "Logger": ...


class Persistence(Protocol):
    """Protocol for state persistence."""
    async def save_state(self, thread_id: str, state: Dict[str, Any]) -> None: ...
    async def load_state(self, thread_id: str) -> Optional[Dict[str, Any]]: ...


class PromptRegistry(Protocol):
    """Protocol for prompt retrieval."""
    def get(self, key: str, **kwargs) -> str: ...


class EventContext(Protocol):
    """Protocol for event emission."""
    async def emit_agent_started(self, agent_name: str) -> None: ...
    async def emit_agent_completed(self, agent_name: str, status: str, **kwargs) -> None: ...


# =============================================================================
# TYPE ALIASES
# =============================================================================

LLMProviderFactory = Callable[[str], LLMProvider]
PreProcessHook = Callable[["Envelope", Optional["Agent"]], "Envelope"]
PostProcessHook = Callable[["Envelope", Dict[str, Any], Optional["Agent"]], "Envelope"]
MockHandler = Callable[["Envelope"], Dict[str, Any]]


# =============================================================================
# AGENT CAPABILITY FLAGS
# =============================================================================

class AgentFeatures:
    """Agent capability flags."""
    LLM = "llm"
    TOOLS = "tools"
    POLICIES = "policies"


# =============================================================================
# UNIFIED AGENT
# =============================================================================

@dataclass
class Agent:
    """Unified agent driven by configuration.

    Agents are configuration-driven - no subclassing required.
    Behavior determined by config flags and hooks.
    """
    config: AgentConfig
    logger: Logger
    llm: Optional[LLMProvider] = None
    tools: Optional[ToolExecutor] = None
    prompt_registry: Optional[PromptRegistry] = None
    event_context: Optional[EventContext] = None
    use_mock: bool = False

    pre_process: Optional[PreProcessHook] = None
    post_process: Optional[PostProcessHook] = None
    mock_handler: Optional[MockHandler] = None

    @property
    def name(self) -> str:
        return self.config.name

    def set_event_context(self, ctx: EventContext) -> None:
        self.event_context = ctx

    async def process(self, envelope: Envelope) -> Envelope:
        """Process envelope through this agent."""
        self.logger.info(f"{self.name}_started", envelope_id=envelope.envelope_id)

        if self.event_context:
            await self.event_context.emit_agent_started(self.name)

        # Pre-process hook
        if self.pre_process:
            result = self.pre_process(envelope, self)
            envelope = await result if asyncio.iscoroutine(result) else result

        # Get output
        if self.use_mock and self.mock_handler:
            output = self.mock_handler(envelope)
        elif self.config.has_llm and self.llm:
            output = await self._call_llm(envelope)
        else:
            output = envelope.outputs.get(self.config.output_key, {})

        # Tool execution
        if self.config.has_tools and self.tools and output.get("tool_calls"):
            output = await self._execute_tools(envelope, output)

        # Debug log output structure for diagnostics
        output_keys = list(output.keys()) if isinstance(output, dict) else []
        self.logger.debug(
            f"{self.name}_output_received",
            envelope_id=envelope.envelope_id,
            output_keys=output_keys,
            output_type=type(output).__name__,
            has_response_key="response" in output_keys,
            has_final_response_key="final_response" in output_keys,
        )

        # Validate required output fields
        if self.config.required_output_fields and isinstance(output, dict):
            missing_fields = [f for f in self.config.required_output_fields if f not in output]
            if missing_fields:
                self.logger.warning(
                    f"{self.name}_missing_required_fields",
                    envelope_id=envelope.envelope_id,
                    missing_fields=missing_fields,
                    required_fields=self.config.required_output_fields,
                    actual_fields=output_keys,
                )

        # Post-process hook
        if self.post_process:
            result = self.post_process(envelope, output, self)
            envelope = await result if asyncio.iscoroutine(result) else result

        # Store output
        envelope.outputs[self.config.output_key] = output
        # Note: agent_hop_count and current_stage are now managed by the kernel orchestrator

        self.logger.info(f"{self.name}_completed", envelope_id=envelope.envelope_id)

        if self.event_context:
            await self.event_context.emit_agent_completed(self.name, status="success")

        return envelope

    async def _call_llm(self, envelope: Envelope) -> Dict[str, Any]:
        """Call LLM with prompt from registry."""
        if not self.prompt_registry:
            raise ValueError(f"Agent {self.name} requires prompt_registry")

        prompt_key = self.config.prompt_key or f"{envelope.metadata.get('pipeline', 'default')}.{self.name}"

        context = self._build_prompt_context(envelope)

        prompt = self.prompt_registry.get(prompt_key, context=context)

        # Build options dict for LLM provider
        options = {}
        if self.config.temperature is not None:
            options["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            options["num_predict"] = self.config.max_tokens  # llama-server uses num_predict

        # Call LLM provider's generate() method
        # model is empty string since llama-server loads a single model
        response = await self.llm.generate(model="", prompt=prompt, options=options)
        envelope.llm_call_count += 1

        # Use JSONRepairKit for robust parsing of LLM output
        # Handles: code fences, text + embedded JSON, trailing commas, single quotes, etc.
        # This ensures P1 (Accuracy First) by properly extracting structured output
        from jeeves_infra.utils import JSONRepairKit

        result = JSONRepairKit.parse_lenient(response)
        if result is not None:
            return result
        return {"response": response}

    async def _execute_tools(self, envelope: Envelope, output: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool calls from LLM output."""
        tool_calls = output.get("tool_calls", [])
        results = []

        for call in tool_calls:
            tool_name = call.get("name")
            params = call.get("params", {})

            if not self._can_access_tool(tool_name):
                results.append({"tool": tool_name, "error": f"Access denied for {self.name}"})
                continue

            try:
                result = await self.tools.execute(tool_name, params)
                results.append({"tool": tool_name, "result": result})
            except Exception as e:
                results.append({"tool": tool_name, "error": str(e)})

        output["tool_results"] = results
        return output

    def _can_access_tool(self, tool_name: str) -> bool:
        """Check tool access based on config."""
        access = self.config.tool_access
        if access == "all":
            return True
        if access == "none":
            return False
        if self.config.allowed_tools:
            return tool_name in self.config.allowed_tools
        return True

    async def stream(self, envelope: Envelope) -> AsyncIterator[Tuple[str, Any]]:
        """Streaming execution (token/event emission).

        Behavior depends on config:
        - token_stream=OFF: No token events
        - token_stream=DEBUG: Emit debug tokens (debug=True)
        - token_stream=AUTHORITATIVE: Emit authoritative tokens (debug=False)

        Yields:
            Tuple[str, Any]: (event_type, event_data) pairs
        """
        from jeeves_infra.protocols import PipelineEvent
        from jeeves_infra.protocols import TokenStreamMode

        self.logger.info(f"{self.name}_stream_started", envelope_id=envelope.envelope_id)

        # Pre-process hook
        if self.pre_process:
            result = self.pre_process(envelope, self)
            envelope = await result if asyncio.iscoroutine(result) else result

        # Determine if tokens should be authoritative
        is_authoritative = self.config.token_stream == TokenStreamMode.AUTHORITATIVE

        # Stream tokens if enabled
        if self.config.token_stream != TokenStreamMode.OFF and self.config.has_llm and self.llm:
            accumulated = ""
            async for token in self._call_llm_stream(envelope):
                accumulated += token
                # Emit token event
                event = PipelineEvent(
                    type="token",
                    stage=self.name,
                    data={"token": token},
                    debug=not is_authoritative  # Debug if not authoritative
                )
                yield ("token", event)

            # Finalize after streaming completes
            if is_authoritative:
                await self.finalize_stream(envelope, accumulated)
            else:
                # For debug mode, still call regular _call_llm for canonical output
                output = await self._call_llm(envelope)
                envelope.outputs[self.config.output_key] = output
        else:
            # No streaming - use regular process
            await self.process(envelope)

        # Note: agent_hop_count and current_stage are now managed by the kernel orchestrator
        self.logger.info(f"{self.name}_stream_completed", envelope_id=envelope.envelope_id)

    async def _call_llm_stream(self, envelope: Envelope) -> AsyncIterator[str]:
        """Stream authoritative tokens (for TEXT mode with AUTHORITATIVE tokens)."""
        from jeeves_infra.protocols import AgentOutputMode

        if self.config.output_mode != AgentOutputMode.TEXT:
            raise ValueError("_call_llm_stream() requires output_mode=TEXT")

        if not self.prompt_registry:
            raise ValueError(f"Agent {self.name} requires prompt_registry")

        # Use streaming prompt key if provided, otherwise append "_streaming"
        prompt_key = self.config.streaming_prompt_key
        if not prompt_key:
            base_key = self.config.prompt_key or f"{envelope.metadata.get('pipeline', 'default')}.{self.name}"
            prompt_key = f"{base_key}_streaming"

        # Build context (same as _call_llm)
        context = self._build_prompt_context(envelope)
        prompt = self.prompt_registry.get(prompt_key, context=context)

        # Build options
        options = {}
        if self.config.temperature is not None:
            options["temperature"] = self.config.temperature
        if self.config.max_tokens is not None:
            options["num_predict"] = self.config.max_tokens

        # Merge GenerationParams (K8s-style spec)
        if self.config.generation:
            options.update(self.config.generation.to_dict())

        # Stream tokens directly from LLM
        async for chunk in self.llm.generate_stream(model="", prompt=prompt, options=options):
            if chunk.text:
                yield chunk.text

        envelope.llm_call_count += 1

    def _build_prompt_context(self, envelope: Envelope) -> Dict[str, Any]:
        """Build context for prompt template interpolation.

        Context is built generically from:
        1. Base envelope fields (raw_input, user_id, session_id)
        2. All prior agent outputs (flattened — both raw and field-level)
        3. Envelope metadata (capability-provided overrides and defaults)

        Capabilities control prompt templates and agent outputs, so they
        align template placeholders with actual output keys. No hardcoded
        agent names or domain-specific defaults live here.
        """
        import os
        repo_path = os.environ.get("REPO_PATH", "/workspace")

        context: Dict[str, Any] = {
            "raw_input": envelope.raw_input,
            "user_input": envelope.raw_input,
            "user_id": envelope.user_id,
            "session_id": envelope.session_id,
            "user_query": envelope.raw_input,
            "repo_path": repo_path,
            "session_state": f"Session: {envelope.session_id}",
            "role_description": f"As the {self.name} agent in this pipeline stage.",
        }

        # Generically flatten all prior agent outputs into context.
        # Each output is available both as its raw key (e.g., context["planner"])
        # and, if it's a dict, its fields are promoted to top-level
        # (e.g., context["normalized_query"] from planner output).
        _base_keys = frozenset(context.keys())
        for output_key, output_value in envelope.outputs.items():
            context[output_key] = output_value
            if isinstance(output_value, dict):
                for field_key, field_value in output_value.items():
                    if field_key not in _base_keys:
                        context[field_key] = field_value

        # Metadata last — capabilities inject defaults and overrides here
        context.update(envelope.metadata)

        return context

    async def finalize_stream(self, envelope: Envelope, accumulated_text: str):
        """Write canonical output after streaming completes."""
        envelope.outputs[self.config.output_key] = {
            "response": accumulated_text,
            "citations": self._extract_citations(accumulated_text),
        }

    def _extract_citations(self, text: str) -> List[str]:
        """Extract inline citations from streaming response.

        Inline citations are v0 best-effort and display-only.
        Not for governance/verification.
        """
        import re
        # Match [Source Name] pattern
        pattern = r'\[([^\]]+)\]'
        matches = re.findall(pattern, text)
        # Deduplicate while preserving order
        seen = set()
        citations = []
        for match in matches:
            if match not in seen:
                seen.add(match)
                citations.append(match)
        return citations


# =============================================================================
# RUNTIME
# =============================================================================

@dataclass
class PipelineRunner:
    """Pipeline runtime - orchestrates agent execution.

    Uses Go for envelope state/bounds when available.
    Uses Python for agent execution, LLM, tools.
    """
    config: PipelineConfig
    llm_factory: Optional[LLMProviderFactory] = None
    tool_executor: Optional[ToolExecutor] = None
    logger: Optional[Logger] = None
    persistence: Optional[Persistence] = None
    prompt_registry: Optional[PromptRegistry] = None
    use_mock: bool = False

    agents: Dict[str, Agent] = field(default_factory=dict)
    event_context: Optional[EventContext] = None
    _initialized: bool = field(default=False)

    def __post_init__(self):
        if not self._initialized:
            self._build_agents()
            self._initialized = True

    def _build_agents(self):
        """Build agents from pipeline config."""
        for agent_config in self.config.agents:
            if agent_config.has_llm and not self.llm_factory:
                raise ValueError(
                    f"Agent '{agent_config.name}' requires LLM but no llm_factory provided "
                    f"to pipeline '{self.config.name}'"
                )

            llm = None
            if agent_config.has_llm and self.llm_factory and agent_config.model_role:
                llm = self.llm_factory(agent_config.model_role)

            tools = self.tool_executor if agent_config.has_tools else None

            agent = Agent(
                config=agent_config,
                logger=self.logger.bind(agent=agent_config.name) if self.logger else _NullLogger(),
                llm=llm,
                tools=tools,
                prompt_registry=self.prompt_registry,
                use_mock=self.use_mock,
                pre_process=getattr(agent_config, 'pre_process', None),
                post_process=getattr(agent_config, 'post_process', None),
                mock_handler=getattr(agent_config, 'mock_handler', None),
            )

            self.agents[agent_config.name] = agent

        if self.logger:
            self.logger.info("runtime_initialized", pipeline=self.config.name, agents=list(self.agents.keys()))

    def set_event_context(self, ctx: EventContext) -> None:
        self.event_context = ctx
        for agent in self.agents.values():
            agent.set_event_context(ctx)

    async def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        if not self.persistence:
            return None
        return await self.persistence.load_state(thread_id)

    def get_agent(self, name: str) -> Agent:
        """Get agent by name. Raises ValueError on miss."""
        if name not in self.agents:
            raise ValueError(
                f"Agent '{name}' not found in pipeline '{self.config.name}'. "
                f"Available: {list(self.agents.keys())}"
            )
        return self.agents[name]


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_pipeline_runner(
    config: PipelineConfig,
    llm_provider_factory: Optional[LLMProviderFactory] = None,
    tool_executor: Optional[ToolExecutor] = None,
    logger: Optional[Logger] = None,
    persistence: Optional[Persistence] = None,
    prompt_registry: Optional[PromptRegistry] = None,
    use_mock: bool = False,
) -> PipelineRunner:
    """Factory to create PipelineRunner from pipeline config."""
    return PipelineRunner(
        config=config,
        llm_factory=llm_provider_factory,
        tool_executor=tool_executor,
        logger=logger,
        persistence=persistence,
        prompt_registry=prompt_registry,
        use_mock=use_mock,
    )


class PipelineRegistry:
    """Dispatches to the right PipelineRunner by pipeline name.

    Eliminates agent name collisions across pipelines by scoping
    lookups to pipeline_name + agent_name.
    """

    def __init__(self):
        self._runners: Dict[str, PipelineRunner] = {}

    def register(self, pipeline_name: str, runner: PipelineRunner) -> None:
        """Register a runner under a pipeline name. Raises on duplicate."""
        if pipeline_name in self._runners:
            raise ValueError(f"Pipeline already registered: {pipeline_name}")
        self._runners[pipeline_name] = runner

    def get_runner(self, pipeline_name: str) -> PipelineRunner:
        """Get runner by pipeline name. Raises ValueError on miss."""
        if pipeline_name not in self._runners:
            raise ValueError(
                f"Unknown pipeline: {pipeline_name}. "
                f"Registered: {list(self._runners.keys())}"
            )
        return self._runners[pipeline_name]

    def get_agent(self, pipeline_name: str, agent_name: str) -> Agent:
        """Get agent from a specific pipeline. Raises ValueError on miss."""
        runner = self.get_runner(pipeline_name)
        agent = runner.agents.get(agent_name)
        if agent is None:
            raise ValueError(
                f"Agent '{agent_name}' not found in pipeline '{pipeline_name}'. "
                f"Available: {list(runner.agents.keys())}"
            )
        return agent

    def has_agent(self, pipeline_name: str, agent_name: str) -> bool:
        """Check if a pipeline has a specific agent (for LLM vs deterministic routing)."""
        runner = self._runners.get(pipeline_name)
        return runner is not None and agent_name in runner.agents

    def list_pipelines(self) -> list:
        return list(self._runners.keys())


def create_envelope(
    raw_input: str,
    request_context: "RequestContext",
    metadata: Optional[Dict[str, Any]] = None,
) -> "Envelope":
    """Factory to create Envelope."""
    import uuid
    from jeeves_infra.utils import utc_now
    from jeeves_infra.protocols import Envelope  # Runtime import to avoid circular dependency

    # Import RequestContext at runtime to avoid circular dependency
    from jeeves_infra.protocols import RequestContext as RC
    if not isinstance(request_context, RC):
        raise TypeError("request_context must be a RequestContext instance")

    return Envelope(
        request_context=request_context,
        envelope_id=str(uuid.uuid4()),
        request_id=request_context.request_id,
        user_id=request_context.user_id or "",
        session_id=request_context.session_id or "",
        raw_input=raw_input,
        received_at=utc_now(),
        metadata=metadata or {},
    )


# =============================================================================
# NULL LOGGER
# =============================================================================

class _NullLogger:
    def info(self, event: str, **kwargs) -> None: pass
    def warn(self, event: str, **kwargs) -> None: pass
    def error(self, event: str, **kwargs) -> None: pass
    def debug(self, event: str, **kwargs) -> None: pass
    def warning(self, event: str, **kwargs) -> None: pass
    def bind(self, **kwargs) -> "_NullLogger": return self


# =============================================================================
# OPTIONAL CHECKPOINT
# =============================================================================

@dataclass
class OptionalCheckpoint:
    """Checkpoint configuration for time-travel debugging."""
    enabled: bool = False
    checkpoint_id: Optional[str] = None
    stage_order: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
