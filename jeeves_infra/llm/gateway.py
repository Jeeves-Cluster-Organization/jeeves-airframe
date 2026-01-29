"""Unified LLM Gateway with cost tracking and provider fallback.

The gateway provides a single entry point for all LLM calls with:
- Automatic cost tracking per request
- Provider fallback on failures
- Request/response metadata collection
- Performance monitoring (latency, tokens/sec)
- Resource tracking via KernelClient (Go kernel integration)
- Streaming support with token-by-token event emission

All agent LLM calls should route through this gateway when
feature_flags.use_llm_gateway is enabled.
"""

import time
from typing import Optional, List, Dict, Any, Callable, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from jeeves_infra.llm.factory import create_agent_provider
from jeeves_infra.capability_registry import get_capability_registry
from jeeves_infra.llm.cost_calculator import get_cost_calculator, CostMetrics
from jeeves_infra.llm.providers.base import TokenChunk
from jeeves_infra.settings import Settings
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol
from jeeves_infra.observability.metrics import record_llm_call, record_llm_tokens
from jeeves_infra.observability.tracing import get_tracer
from opentelemetry.trace import Status, StatusCode

if TYPE_CHECKING:
    from jeeves_infra.kernel_client import KernelClient

# Type alias for streaming event callback
# Callback signature: (chunk: StreamingChunk) -> None
# Called for each token chunk during streaming
StreamingEventCallback = Callable[["StreamingChunk"], None]


class QuotaExceededError(Exception):
    """Raised when resource quota is exceeded."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Quota exceeded: {reason}")


@dataclass
class StreamingChunk:
    """A chunk emitted during streaming generation.

    Used for real-time UI updates during LLM generation.
    """
    text: str
    """The text content of this chunk"""

    is_final: bool
    """True if this is the last chunk"""

    request_id: str
    """Unique request identifier for correlation"""

    agent_name: str
    """Name of the agent that requested generation"""

    provider: str
    """Provider generating the response"""

    model: str
    """Model generating the response"""

    cumulative_tokens: int
    """Running total of tokens generated so far"""

    timestamp: datetime
    """Timestamp of this chunk"""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "text": self.text,
            "is_final": self.is_final,
            "request_id": self.request_id,
            "agent_name": self.agent_name,
            "provider": self.provider,
            "model": self.model,
            "cumulative_tokens": self.cumulative_tokens,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class LLMResponse:
    """Response from LLM with metadata."""

    text: str
    """Generated text response"""

    tool_calls: List[Dict[str, Any]]
    """Parsed tool calls from response"""

    tokens_used: int
    """Total tokens (prompt + completion)"""

    prompt_tokens: int
    """Input tokens"""

    completion_tokens: int
    """Output tokens"""

    latency_ms: float
    """Response time in milliseconds"""

    provider: str
    """Provider that handled the request (llamaserver, openai, anthropic)"""

    model: str
    """Model used for generation"""

    cost_usd: float
    """Cost in USD for this request"""

    timestamp: datetime
    """Request timestamp"""

    metadata: Dict[str, Any]
    """Additional metadata"""

    streamed: bool = False
    """Whether response was streamed"""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


# Module-level tracer
tracer = get_tracer(__name__)


class LLMGateway:
    """Unified gateway for all LLM interactions.

    Routes requests through appropriate providers with automatic fallback,
    cost tracking, and performance monitoring.

    Resource Tracking:
    - Integrates with Go kernel via KernelClient for quota enforcement
    - Reports token usage after each LLM call
    - Raises QuotaExceededError when limits are hit

    Streaming Support:
    - Use complete_stream() for token-by-token streaming
    - Set streaming_callback for real-time event emission
    - Streaming events include request correlation IDs

    Example:
        gateway = LLMGateway(settings)
        response = await gateway.complete(
            prompt="Analyze this task",
            system="You are a helpful assistant",
            agent_name="planner"
        )
        # Cost available in response.cost_usd

    With kernel resource tracking:
        gateway = LLMGateway(settings, kernel_client=kernel_client)
        gateway.set_pid("request-123")  # Set current process ID
        response = await gateway.complete(...)  # Automatically tracks usage

    With streaming:
        async for chunk in gateway.complete_stream(prompt="...", agent_name="planner"):
            print(chunk.text, end="", flush=True)
    """

    def __init__(
        self,
        settings: Settings,
        fallback_providers: Optional[List[str]] = None,
        logger: Optional[LoggerProtocol] = None,
        kernel_client: Optional["KernelClient"] = None,
        streaming_callback: Optional[StreamingEventCallback] = None,
    ):
        """Initialize gateway.

        Args:
            settings: Application settings
            fallback_providers: Ordered list of providers to try on failure.
                              If None, uses only primary provider.
                              Example: ["llamaserver", "openai"] tries OpenAI if llama-server fails
            logger: Logger for DI (uses context logger if not provided)
            kernel_client: Optional KernelClient for resource tracking (Go kernel integration).
                          When set, token usage is reported to kernel after each LLM call.
            streaming_callback: Optional callback for streaming events.
                              Called for each token chunk during streaming generation.
        """
        self._logger = logger or get_current_logger()
        self.settings = settings
        self.fallback_providers = fallback_providers or []
        self.cost_calculator = get_cost_calculator()
        self._kernel_client = kernel_client
        self._current_pid: Optional[str] = None
        self._streaming_callback = streaming_callback

        # Statistics
        self.total_requests = 0
        self.total_cost_usd = 0.0
        self.total_tokens = 0
        self.provider_stats: Dict[str, Dict[str, Any]] = {}

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        agent_name: str = "unknown",
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate LLM completion with automatic fallback and cost tracking.

        Args:
            prompt: User/task prompt
            system: System prompt (optional)
            model: Specific model to use (optional, uses agent default)
            agent_name: Name of calling agent for logging/tracking
            tools: Available tools for function calling
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with text, metadata, and cost information

        Raises:
            Exception: If all providers fail
        """
        start_time = time.time()
        request_id = f"{agent_name}_{int(start_time * 1000)}"

        # Determine provider from settings
        provider_name = self._get_provider_for_agent(agent_name)

        # Try primary provider
        try:
            response = await self._call_provider(
                provider_name=provider_name,
                agent_name=agent_name,
                prompt=prompt,
                system=system,
                model=model,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                request_id=request_id,
                start_time=start_time
            )

            await self._update_stats(response)
            return response

        except Exception as primary_error:
            self._logger.warning(
                "primary_provider_failed",
                provider=provider_name,
                agent=agent_name,
                error=str(primary_error),
                request_id=request_id
            )

            # Try fallback providers
            for fallback_provider in self.fallback_providers:
                if fallback_provider == provider_name:
                    continue  # Skip if same as primary

                try:
                    self._logger.info(
                        "attempting_fallback",
                        fallback_provider=fallback_provider,
                        agent=agent_name,
                        request_id=request_id
                    )

                    response = await self._call_provider(
                        provider_name=fallback_provider,
                        agent_name=agent_name,
                        prompt=prompt,
                        system=system,
                        model=model,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        request_id=request_id,
                        start_time=start_time
                    )

                    await self._update_stats(response)
                    self._logger.info(
                        "fallback_succeeded",
                        fallback_provider=fallback_provider,
                        agent=agent_name,
                        request_id=request_id
                    )
                    return response

                except Exception as fallback_error:
                    self._logger.warning(
                        "fallback_provider_failed",
                        provider=fallback_provider,
                        agent=agent_name,
                        error=str(fallback_error),
                        request_id=request_id
                    )
                    continue

            # All providers failed
            raise Exception(
                f"All LLM providers failed for {agent_name}. "
                f"Primary: {provider_name}, Fallbacks: {self.fallback_providers}"
            ) from primary_error

    async def _call_provider(
        self,
        provider_name: str,
        agent_name: str,
        prompt: str,
        system: Optional[str],
        model: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: Optional[int],
        request_id: str,
        start_time: float
    ) -> LLMResponse:
        """Call a specific provider and return standardized response."""

        # Create tracing span
        with tracer.start_as_current_span(
            "llm.provider.call",
            attributes={
                "jeeves.llm.provider": provider_name,
                "jeeves.llm.model": model or "default",
                "jeeves.agent.name": agent_name,
                "jeeves.request.id": request_id,
            }
        ) as span:
            return await self._call_provider_with_span(
                span, provider_name, agent_name, prompt, system, model,
                tools, temperature, max_tokens, request_id, start_time
            )

    async def _call_provider_with_span(
        self,
        span,
        provider_name: str,
        agent_name: str,
        prompt: str,
        system: Optional[str],
        model: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        temperature: float,
        max_tokens: Optional[int],
        request_id: str,
        start_time: float
    ) -> LLMResponse:
        """Internal implementation with span for tracing."""

        # Create provider instance
        provider = create_agent_provider(
            settings=self.settings,
            agent_name=agent_name,
            override_provider=provider_name
        )

        # Compose prompt text (prepend system directive if provided)
        prompt_text = prompt
        if system:
            prompt_text = f"{system}\n\n{prompt}"

        # Map gateway params to provider-style options
        options: Dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        model_name = model or self._get_model_for_agent(agent_name)

        # Call provider using legacy interface
        try:
            llm_result = await provider.generate(
                model=model_name,
                prompt=prompt_text,
                options=options
            )
        except Exception as e:
            # Record error metrics
            latency_ms = (time.time() - start_time) * 1000
            record_llm_call(
                provider=provider_name,
                model=model_name,
                status="error",
                duration_seconds=latency_ms / 1000.0
            )
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Extract token counts (provider-specific)
        prompt_tokens = self._estimate_tokens(prompt_text)
        completion_tokens = self._estimate_tokens(llm_result)
        total_tokens = prompt_tokens + completion_tokens

        # Calculate cost
        model_used = model_name
        cost_metrics = self.cost_calculator.calculate_cost(
            provider=provider_name,
            model=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        # Record metrics
        record_llm_call(
            provider=provider_name,
            model=model_used,
            status="success",
            duration_seconds=latency_ms / 1000.0
        )
        record_llm_tokens(
            provider=provider_name,
            model=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        # Record span attributes
        span.set_attributes({
            "jeeves.llm.tokens.prompt": prompt_tokens,
            "jeeves.llm.tokens.completion": completion_tokens,
            "jeeves.llm.tokens.total": total_tokens,
            "jeeves.llm.cost_usd": cost_metrics.cost_usd,
            "jeeves.llm.latency_ms": latency_ms,
        })
        span.set_status(Status(StatusCode.OK))

        # Parse tool calls (if any)
        tool_calls = self._extract_tool_calls(llm_result)

        self._logger.info(
            "llm_request_completed",
            provider=provider_name,
            model=model_used,
            agent=agent_name,
            tokens=total_tokens,
            latency_ms=round(latency_ms, 2),
            cost_usd=cost_metrics.cost_usd,
            request_id=request_id
        )

        return LLMResponse(
            text=llm_result,
            tool_calls=tool_calls,
            tokens_used=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            provider=provider_name,
            model=model_used,
            cost_usd=cost_metrics.cost_usd,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "agent_name": agent_name,
                "request_id": request_id,
                "temperature": temperature,
            }
        )

    def _get_provider_for_agent(self, agent_name: str) -> str:
        """Get provider name for specific agent from settings."""
        # Check agent-specific override
        agent_provider_attr = f"{agent_name}_llm_provider"
        provider = getattr(self.settings, agent_provider_attr, None)

        if provider:
            return provider

        # Fall back to global provider
        return self.settings.llm_provider

    def _get_model_for_agent(self, agent_name: str) -> str:
        """Get model name for specific agent from capability registry."""
        registry = get_capability_registry()
        config = registry.get_agent_config(agent_name)
        if config:
            return config.model
        return self.settings.default_model

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars ≈ 1 token for English)."""
        return max(1, len(text) // 4)

    def _extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM response.

        Parses tool calls from JSON blocks in the response text.
        Supports formats:
        - {"tool": "name", "parameters": {...}}
        - {"steps": [{"tool": "name", "parameters": {...}}, ...]}

        Per Constitution P2 (Reliability): Returns empty list on parse failure,
        does not guess or fabricate tool calls.
        """
        import json
        import re

        tool_calls: List[Dict[str, Any]] = []

        if not text or not text.strip():
            return tool_calls

        # Try to find JSON blocks in the text
        # Look for {...} patterns that might contain tool calls
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)

        for match in matches:
            try:
                parsed = json.loads(match)

                # Format 1: Direct tool call {"tool": "...", "parameters": {...}}
                if isinstance(parsed, dict) and "tool" in parsed:
                    tool_calls.append({
                        "tool": parsed.get("tool"),
                        "parameters": parsed.get("parameters", {}),
                    })

                # Format 2: Steps array {"steps": [{"tool": "...", ...}]}
                elif isinstance(parsed, dict) and "steps" in parsed:
                    steps = parsed.get("steps", [])
                    if isinstance(steps, list):
                        for step in steps:
                            if isinstance(step, dict) and "tool" in step:
                                tool_calls.append({
                                    "tool": step.get("tool"),
                                    "parameters": step.get("parameters", {}),
                                })

            except (json.JSONDecodeError, TypeError):
                # Per P2: Don't guess, just skip malformed JSON
                continue

        return tool_calls

    async def _update_stats(self, response: LLMResponse) -> None:
        """Update gateway statistics and report to kernel.

        Args:
            response: LLM response with token counts

        Raises:
            QuotaExceededError: If kernel reports quota exceeded
        """
        self.total_requests += 1
        self.total_cost_usd += response.cost_usd
        self.total_tokens += response.tokens_used

        # Per-provider stats
        if response.provider not in self.provider_stats:
            self.provider_stats[response.provider] = {
                "requests": 0,
                "tokens": 0,
                "cost_usd": 0.0,
                "total_latency_ms": 0.0
            }

        stats = self.provider_stats[response.provider]
        stats["requests"] += 1
        stats["tokens"] += response.tokens_used
        stats["cost_usd"] += response.cost_usd
        stats["total_latency_ms"] += response.latency_ms

        # Report to kernel if client and PID are set
        if self._kernel_client and self._current_pid:
            try:
                exceeded_reason = await self._kernel_client.record_llm_call(
                    pid=self._current_pid,
                    tokens_in=response.prompt_tokens,
                    tokens_out=response.completion_tokens,
                )
                if exceeded_reason:
                    self._logger.warning(
                        "llm_quota_exceeded",
                        pid=self._current_pid,
                        tokens_in=response.prompt_tokens,
                        tokens_out=response.completion_tokens,
                        reason=exceeded_reason,
                    )
                    raise QuotaExceededError(exceeded_reason)
            except QuotaExceededError:
                raise
            except Exception as e:
                # Log but don't fail the request if kernel reporting fails
                self._logger.warning(
                    "kernel_reporting_failed",
                    pid=self._current_pid,
                    error=str(e),
                )

    def set_pid(self, pid: Optional[str]) -> None:
        """Set the current process ID for resource tracking.

        Call this before making LLM calls to enable per-request
        resource tracking through the kernel.

        Args:
            pid: Process ID (envelope_id) or None to disable tracking
        """
        self._current_pid = pid

    def set_kernel_client(self, client: Optional["KernelClient"]) -> None:
        """Set or update the kernel client.

        Args:
            client: KernelClient instance or None to disable kernel integration
        """
        self._kernel_client = client

    def get_stats(self) -> Dict[str, Any]:
        """Get gateway statistics.

        Returns:
            Dictionary with request counts, costs, and performance metrics
        """
        stats = {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "by_provider": {}
        }

        for provider, prov_stats in self.provider_stats.items():
            avg_latency = (
                prov_stats["total_latency_ms"] / prov_stats["requests"]
                if prov_stats["requests"] > 0
                else 0
            )

            stats["by_provider"][provider] = {
                "requests": prov_stats["requests"],
                "tokens": prov_stats["tokens"],
                "cost_usd": round(prov_stats["cost_usd"], 6),
                "avg_latency_ms": round(avg_latency, 2)
            }

        return stats

    def set_streaming_callback(self, callback: Optional[StreamingEventCallback]) -> None:
        """Set the streaming event callback.

        Allows dynamic configuration of streaming event handling.

        Args:
            callback: Callback function or None to disable streaming events
        """
        self._streaming_callback = callback

    async def complete_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        agent_name: str = "unknown",
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamingChunk]:
        """Generate LLM completion with streaming output.

        Yields StreamingChunk objects as tokens are generated.
        Also invokes streaming_callback if configured.

        Args:
            prompt: User/task prompt
            system: System prompt (optional)
            model: Specific model to use (optional, uses agent default)
            agent_name: Name of calling agent for logging/tracking
            tools: Available tools for function calling (not supported in streaming)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate

        Yields:
            StreamingChunk with text and metadata

        Note:
            Tool parsing is performed on the final accumulated response,
            not on individual chunks.
        """
        start_time = time.time()
        request_id = f"{agent_name}_{int(start_time * 1000)}"

        provider_name = self._get_provider_for_agent(agent_name)
        model_name = model or self._get_model_for_agent(agent_name)

        # Create provider instance
        provider = create_agent_provider(
            settings=self.settings,
            agent_name=agent_name,
            override_provider=provider_name
        )

        # Compose prompt
        prompt_text = prompt
        if system:
            prompt_text = f"{system}\n\n{prompt}"

        options: Dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        self._logger.info(
            "llm_stream_started",
            provider=provider_name,
            model=model_name,
            agent=agent_name,
            request_id=request_id,
        )

        # Stream tokens
        accumulated_text = ""
        cumulative_tokens = 0

        try:
            async for token_chunk in provider.generate_stream(
                model=model_name,
                prompt=prompt_text,
                options=options
            ):
                accumulated_text += token_chunk.text
                cumulative_tokens += token_chunk.token_count

                streaming_chunk = StreamingChunk(
                    text=token_chunk.text,
                    is_final=token_chunk.is_final,
                    request_id=request_id,
                    agent_name=agent_name,
                    provider=provider_name,
                    model=model_name,
                    cumulative_tokens=cumulative_tokens,
                    timestamp=datetime.now(timezone.utc),
                )

                # Invoke callback if set
                if self._streaming_callback:
                    try:
                        self._streaming_callback(streaming_chunk)
                    except Exception as callback_error:
                        self._logger.warning(
                            "streaming_callback_error",
                            error=str(callback_error),
                            request_id=request_id,
                        )

                yield streaming_chunk

            # Calculate final metrics
            latency_ms = (time.time() - start_time) * 1000
            prompt_tokens = self._estimate_tokens(prompt_text)
            completion_tokens = cumulative_tokens or self._estimate_tokens(accumulated_text)

            # Calculate cost
            cost_metrics = self.cost_calculator.calculate_cost(
                provider=provider_name,
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )

            # Create response for stats tracking
            response = LLMResponse(
                text=accumulated_text,
                tool_calls=self._extract_tool_calls(accumulated_text),
                tokens_used=prompt_tokens + completion_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                provider=provider_name,
                model=model_name,
                cost_usd=cost_metrics.cost_usd,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "agent_name": agent_name,
                    "request_id": request_id,
                    "temperature": temperature,
                    "streaming": True,
                },
                streamed=True,
            )

            await self._update_stats(response)

            self._logger.info(
                "llm_stream_completed",
                provider=provider_name,
                model=model_name,
                agent=agent_name,
                tokens=response.tokens_used,
                latency_ms=round(latency_ms, 2),
                cost_usd=cost_metrics.cost_usd,
                request_id=request_id,
            )

        except Exception as e:
            self._logger.error(
                "llm_stream_failed",
                provider=provider_name,
                model=model_name,
                agent=agent_name,
                error=str(e),
                request_id=request_id,
            )
            raise

    async def complete_stream_to_response(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        agent_name: str = "unknown",
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate LLM completion with streaming, returning final LLMResponse.

        Streams internally (invoking callbacks) but returns a complete response.
        Useful when you want streaming events but also need the final response object.

        Args:
            Same as complete_stream()

        Returns:
            LLMResponse with complete text and metadata
        """
        start_time = time.time()
        request_id = f"{agent_name}_{int(start_time * 1000)}"
        provider_name = self._get_provider_for_agent(agent_name)
        model_name = model or self._get_model_for_agent(agent_name)

        accumulated_text = ""
        cumulative_tokens = 0

        async for chunk in self.complete_stream(
            prompt=prompt,
            system=system,
            model=model,
            agent_name=agent_name,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            accumulated_text += chunk.text
            cumulative_tokens = chunk.cumulative_tokens

        latency_ms = (time.time() - start_time) * 1000
        prompt_tokens = self._estimate_tokens(prompt)
        completion_tokens = cumulative_tokens or self._estimate_tokens(accumulated_text)

        cost_metrics = self.cost_calculator.calculate_cost(
            provider=provider_name,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        return LLMResponse(
            text=accumulated_text,
            tool_calls=self._extract_tool_calls(accumulated_text),
            tokens_used=prompt_tokens + completion_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            provider=provider_name,
            model=model_name,
            cost_usd=cost_metrics.cost_usd,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "agent_name": agent_name,
                "request_id": request_id,
                "temperature": temperature,
                "streaming": True,
            },
            streamed=True,
        )


__all__ = [
    "LLMGateway",
    "LLMResponse",
    "StreamingChunk",
    "QuotaExceededError",
]
