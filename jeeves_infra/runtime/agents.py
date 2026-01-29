"""Agent PipelineRunner - Go-backed pipeline execution.

Architecture:
    Go (coreengine/)     - Envelope state, bounds checking, pipeline graph
    Python (this file)   - Agent execution, LLM calls, tool execution
    Bridge (client.py)   - JSON-over-stdio communication
"""
from __future__ import annotations

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
            envelope = self.pre_process(envelope, self)

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
            envelope = self.post_process(envelope, output, self)

        # Store output
        envelope.outputs[self.config.output_key] = output
        envelope.agent_hop_count += 1

        # Route to next stage
        next_stage = self._determine_next_stage(output)
        envelope.current_stage = next_stage

        self.logger.info(f"{self.name}_completed", envelope_id=envelope.envelope_id, next_stage=next_stage)

        if self.event_context:
            await self.event_context.emit_agent_completed(self.name, status="success")

        return envelope

    async def _call_llm(self, envelope: Envelope) -> Dict[str, Any]:
        """Call LLM with prompt from registry."""
        if not self.prompt_registry:
            raise ValueError(f"Agent {self.name} requires prompt_registry")

        prompt_key = self.config.prompt_key or f"{envelope.metadata.get('pipeline', 'default')}.{self.name}"

        # Build context dict from envelope for prompt template interpolation
        import os
        repo_path = os.environ.get("REPO_PATH", "/workspace")
        context = {
            "raw_input": envelope.raw_input,
            "user_input": envelope.raw_input,  # Alias for compatibility
            "user_id": envelope.user_id,
            "session_id": envelope.session_id,
            "system_identity": "You are a code analysis assistant.",
            "role_description": f"As the {self.name} agent, you process information and pass results to the next stage.",
            "normalized_input": envelope.raw_input,  # Default, may be overridden by perception output
            "context_summary": "",
            "detected_languages": "[]",
            "capabilities_summary": "Code search, file reading, symbol lookup, dependency analysis",
            "user_query": envelope.raw_input,
            "repo_path": repo_path,
            "session_state": f"Session: {envelope.session_id}",
            # Provide safe defaults for common prompt placeholders
            "intent": "",
            "goals": "[]",
            "scope_path": "",
            "exploration_summary": "",
            "available_tools": "",
            "bounds_description": "",
            "max_files": 50,
            "max_tokens": 100000,
            "files_explored": 0,
            "tokens_used": 0,
            "remaining_files": 50,
            "remaining_tokens": 100000,
            "retry_feedback": "",
            "execution_results": "",
            "relevant_snippets": "",
            "verdict": "",
            "suggested_response": "",
            "pipeline_overview": "7-agent code analysis pipeline",
            "files_examined": "[]",
        }

        # Include all agent outputs as nested dicts (e.g., context["intent"] = {...})
        context.update(envelope.outputs)

        # Extract commonly needed fields from nested outputs
        # This allows prompts to use both {intent} (dict) and flattened fields
        if "perception" in envelope.outputs:
            perception = envelope.outputs["perception"]
            if isinstance(perception, dict):
                context["normalized_input"] = perception.get("normalized_query", context["normalized_input"])
                context["scope_path"] = perception.get("scope", "")

        if "intent" in envelope.outputs:
            intent_output = envelope.outputs["intent"]
            if isinstance(intent_output, dict):
                # Extract tool_suite classification (new architecture)
                # Fallback to "intent" field for backwards compatibility
                tool_suite = intent_output.get("tool_suite") or intent_output.get("intent", "")
                context["tool_suite"] = tool_suite
                context["intent"] = tool_suite  # Backwards compatibility alias
                # Extract goals (list or string representation)
                goals = intent_output.get("goals", [])
                context["goals"] = str(goals) if isinstance(goals, list) else goals
                # Extract search targets (Amendment XXII v2 - Two-Tool Architecture)
                search_targets = intent_output.get("search_targets", [])
                if search_targets:
                    context["search_targets"] = ", ".join(f'"{t}"' for t in search_targets)
                else:
                    context["search_targets"] = "none extracted - use keywords from query"

        if "plan" in envelope.outputs:
            plan_output = envelope.outputs["plan"]
            if isinstance(plan_output, dict):
                context["execution_results"] = str(plan_output.get("steps", ""))

        if "execution" in envelope.outputs:
            exec_output = envelope.outputs["execution"]
            if isinstance(exec_output, dict):
                context["execution_results"] = str(exec_output.get("results", ""))
                context["relevant_snippets"] = str(exec_output.get("snippets", ""))

        if "critic" in envelope.outputs:
            critic_output = envelope.outputs["critic"]
            if isinstance(critic_output, dict):
                context["verdict"] = critic_output.get("verdict", "")
                context["suggested_response"] = critic_output.get("suggested_response", "")

        # Include metadata last (can override extracted fields if needed)
        context.update(envelope.metadata)

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

    def _determine_next_stage(self, output: Dict[str, Any]) -> str:
        """Determine next stage based on routing rules."""
        for rule in self.config.routing_rules:
            if output.get(rule.condition) == rule.value:
                return rule.target

        if output.get("error") and self.config.error_next:
            return self.config.error_next

        return self.config.default_next or "end"

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
            envelope = self.pre_process(envelope, self)

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

        envelope.agent_hop_count += 1
        next_stage = self._determine_next_stage(envelope.outputs.get(self.config.output_key, {}))
        envelope.current_stage = next_stage

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
        """Build context for prompt template interpolation."""
        import os
        repo_path = os.environ.get("REPO_PATH", "/workspace")
        context = {
            "raw_input": envelope.raw_input,
            "user_input": envelope.raw_input,
            "user_id": envelope.user_id,
            "session_id": envelope.session_id,
            "system_identity": "You are a code analysis assistant.",
            "role_description": f"As the {self.name} agent, you process information and pass results to the next stage.",
            "normalized_input": envelope.raw_input,
            "context_summary": "",
            "detected_languages": "[]",
            "capabilities_summary": "Code search, file reading, symbol lookup, dependency analysis",
            "user_query": envelope.raw_input,
            "repo_path": repo_path,
            "session_state": f"Session: {envelope.session_id}",
            # Safe defaults for common placeholders
            "intent": "",
            "goals": "[]",
            "scope_path": "",
            "exploration_summary": "",
            "available_tools": "",
            "bounds_description": "",
            "max_files": 50,
            "max_tokens": 100000,
            "files_explored": 0,
            "tokens_used": 0,
            "remaining_files": 50,
            "remaining_tokens": 100000,
            "retry_feedback": "",
            "execution_results": "",
            "relevant_snippets": "",
            "verdict": "",
            "suggested_response": "",
            "pipeline_overview": "7-agent code analysis pipeline",
            "files_examined": "[]",
        }

        # Include all agent outputs
        context.update(envelope.outputs)

        # Extract commonly needed fields from nested outputs
        if "perception" in envelope.outputs:
            perception = envelope.outputs["perception"]
            if isinstance(perception, dict):
                context["normalized_input"] = perception.get("normalized_query", context["normalized_input"])
                context["scope_path"] = perception.get("scope", "")

        if "intent" in envelope.outputs:
            intent_output = envelope.outputs["intent"]
            if isinstance(intent_output, dict):
                # Extract tool_suite classification (new architecture)
                # Fallback to "intent" field for backwards compatibility
                tool_suite = intent_output.get("tool_suite") or intent_output.get("intent", "")
                context["tool_suite"] = tool_suite
                context["intent"] = tool_suite  # Backwards compatibility alias
                goals = intent_output.get("goals", [])
                context["goals"] = str(goals) if isinstance(goals, list) else goals
                search_targets = intent_output.get("search_targets", [])
                if search_targets:
                    context["search_targets"] = ", ".join(f'"{t}"' for t in search_targets)
                else:
                    context["search_targets"] = "none extracted - use keywords from query"

        # Include metadata last
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

    async def run(self, envelope: Envelope, thread_id: str = "") -> Envelope:
        """Execute pipeline on envelope."""
        envelope.max_iterations = self.config.max_iterations
        envelope.max_llm_calls = self.config.max_llm_calls
        envelope.max_agent_hops = self.config.max_agent_hops

        stage_order = [a.name for a in self.config.agents]
        envelope.stage_order = stage_order
        envelope.current_stage = stage_order[0] if stage_order else "end"

        if self.logger:
            self.logger.info("pipeline_started", envelope_id=envelope.envelope_id, stages=stage_order)

        while envelope.current_stage != "end" and not envelope.terminated:
            if not self._can_continue(envelope):
                if self.logger:
                    self.logger.warning("pipeline_bounds_exceeded", reason=envelope.terminal_reason)
                break

            if envelope.current_stage in ("clarification", "confirmation"):
                break

            agent = self.agents.get(envelope.current_stage)
            if not agent:
                envelope.terminated = True
                envelope.terminal_reason = f"Unknown stage: {envelope.current_stage}"
                break

            try:
                envelope = await agent.process(envelope)
            except Exception as e:
                if self.logger:
                    self.logger.error("agent_error", agent=agent.name, error=str(e))
                if agent.config.error_next:
                    envelope.current_stage = agent.config.error_next
                else:
                    envelope.terminated = True
                    envelope.terminal_reason = str(e)
                    break

            if self.persistence and thread_id:
                try:
                    await self.persistence.save_state(thread_id, envelope.to_dict())
                except Exception:
                    pass

        if self.logger:
            self.logger.info("pipeline_completed", envelope_id=envelope.envelope_id, terminated=envelope.terminated)

        return envelope

    async def run_streaming(self, envelope: Envelope, thread_id: str = "") -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
        """Execute pipeline with streaming outputs."""
        envelope.max_iterations = self.config.max_iterations
        envelope.max_llm_calls = self.config.max_llm_calls
        envelope.max_agent_hops = self.config.max_agent_hops

        stage_order = [a.name for a in self.config.agents]
        envelope.stage_order = stage_order
        envelope.current_stage = stage_order[0] if stage_order else "end"

        while envelope.current_stage != "end" and not envelope.terminated:
            if not self._can_continue(envelope):
                break

            if envelope.current_stage in ("clarification", "confirmation"):
                break

            agent = self.agents.get(envelope.current_stage)
            if not agent:
                envelope.terminated = True
                break

            stage_name = envelope.current_stage

            try:
                envelope = await agent.process(envelope)
            except Exception as e:
                envelope.terminated = True
                envelope.terminal_reason = str(e)
                break

            # Yield the output using the agent's output_key, not stage_name
            # Some agents have different output_key than their name (e.g., planner has output_key="plan")
            output_key = agent.config.output_key
            yield (stage_name, envelope.outputs.get(output_key, {}))

            if self.persistence and thread_id:
                try:
                    await self.persistence.save_state(thread_id, envelope.to_dict())
                except Exception:
                    pass

        yield ("__end__", {"terminated": envelope.terminated})

    async def resume(self, envelope: Envelope, thread_id: str = "") -> Envelope:
        """Resume after interrupt.

        Resume stages are determined by PipelineConfig, not hardcoded.
        This allows different capabilities to define their own resume behavior.
        """
        from jeeves_infra.protocols import InterruptKind

        # Handle unified interrupt mechanism
        if envelope.interrupt and envelope.interrupt.kind == InterruptKind.CLARIFICATION:
            envelope.interrupt_pending = False
            envelope.interrupt = None
            # Use config-defined resume stage (capability determines this)
            envelope.current_stage = self.config.get_clarification_resume_stage()

        if envelope.interrupt and envelope.interrupt.kind == InterruptKind.CONFIRMATION:
            envelope.interrupt_pending = False
            confirmation_response = envelope.interrupt.response
            envelope.interrupt = None
            if confirmation_response and confirmation_response.approved:
                # Use config-defined resume stage (capability determines this)
                envelope.current_stage = self.config.get_confirmation_resume_stage()
            else:
                envelope.terminated = True
                envelope.terminal_reason = "User denied"
                return envelope

        return await self.run(envelope, thread_id)

    async def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        if not self.persistence:
            return None
        return await self.persistence.load_state(thread_id)

    def _can_continue(self, envelope: Envelope) -> bool:
        """Check bounds."""
        if envelope.iteration >= envelope.max_iterations:
            envelope.terminal_reason = "max_iterations_exceeded"
            return False
        if envelope.llm_call_count >= envelope.max_llm_calls:
            envelope.terminal_reason = "max_llm_calls_exceeded"
            return False
        if envelope.agent_hop_count >= envelope.max_agent_hops:
            envelope.terminal_reason = "max_agent_hops_exceeded"
            return False
        return True

    def get_agent(self, name: str) -> Optional[Agent]:
        return self.agents.get(name)


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
        created_at=utc_now(),
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
