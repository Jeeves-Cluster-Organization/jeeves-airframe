"""
LiteLLM provider - unified provider for 100+ LLM backends.

Replaces all airframe adapters with direct LiteLLM calls.
LiteLLM handles: HTTP, retries, streaming, provider quirks.
This provider adds: cost tracking, logging, Avionics API translation.

Supports:
- OpenAI, Azure OpenAI, Anthropic, Cohere, etc. (cloud)
- llama.cpp, vLLM, Ollama, etc. (local via OpenAI-compatible API)
- AWS Bedrock, Google Vertex AI, etc. (cloud with special auth)

Usage:
    provider = LiteLLMProvider(model="claude-3-sonnet-20240229")
    response = await provider.generate(model="claude-3-sonnet", prompt="Hello")

    # For local llama-server:
    provider = LiteLLMProvider(
        model="openai/llama",
        api_base="http://localhost:8080/v1"
    )
"""

from typing import AsyncIterator, Dict, Any, Optional

from .base import LLMProvider, TokenChunk
from ..cost_calculator import get_cost_calculator
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol

try:
    from litellm import acompletion
except ImportError:
    acompletion = None  # type: ignore


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for unified access to 100+ backends.

    This is the recommended provider for all LLM interactions.
    It replaces the airframe-based adapters with battle-tested LiteLLM.

    Attributes:
        model: LiteLLM model string (e.g., "claude-3-sonnet-20240229", "openai/gpt-4")
        api_base: Optional API base URL for local/custom endpoints
        api_key: Optional API key (can also be set via environment)
        timeout: Request timeout in seconds
        max_retries: Number of retries on transient failures
    """

    def __init__(
        self,
        model: str,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
        max_retries: int = 3,
        logger: Optional[LoggerProtocol] = None,
        **extra_params,
    ):
        """
        Initialize LiteLLM provider.

        Args:
            model: LiteLLM model identifier. Examples:
                - "claude-3-sonnet-20240229" (Anthropic)
                - "gpt-4-turbo" (OpenAI)
                - "openai/llama" (local llama-server with OpenAI API)
                - "bedrock/anthropic.claude-3-sonnet" (AWS Bedrock)
            api_base: Base URL for OpenAI-compatible endpoints (local models)
            api_key: API key (optional, uses env vars if not provided)
            timeout: Request timeout in seconds (default: 120s)
            max_retries: Retry count for transient failures (default: 3)
            logger: Logger instance (uses context logger if not provided)
            **extra_params: Additional LiteLLM params (temperature, etc.)
        """
        if acompletion is None:
            raise ImportError("litellm is required: pip install litellm")

        self._logger = logger or get_current_logger()
        self._model = model
        self._api_base = api_base
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._extra_params = extra_params
        self._cost_calculator = get_cost_calculator()

        self._logger.info(
            "litellm_provider_initialized",
            model=model,
            api_base=api_base,
            timeout=timeout,
        )

    async def generate(
        self, model: str, prompt: str, options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate text completion via LiteLLM.

        Args:
            model: Model name (can override instance default)
            prompt: Input prompt text
            options: Generation options (temperature, max_tokens, etc.)

        Returns:
            Generated text string

        Raises:
            Exception: On LLM errors
        """
        opts = options or {}
        model_to_use = model or self._model

        # Build LiteLLM kwargs
        kwargs = self._build_kwargs(prompt, opts, stream=False)

        self._logger.debug(
            "litellm_generating",
            model=model_to_use,
            prompt_length=len(prompt),
            max_tokens=opts.get("max_tokens") or opts.get("num_predict"),
        )

        try:
            response = await acompletion(
                model=model_to_use,
                **kwargs,
            )

            # Extract text from response
            text = response.choices[0].message.content or ""

            # Extract usage for cost tracking
            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

            # Calculate cost
            cost_metrics = self._cost_calculator.calculate_cost(
                provider="litellm",
                model=model_to_use,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

            self._logger.info(
                "llm_generation_complete",
                provider="litellm",
                model=model_to_use,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_metrics.cost_usd,
            )

            return text

        except Exception as e:
            self._logger.error(
                "litellm_error",
                model=model_to_use,
                error=str(e),
            )
            raise

    async def generate_stream(
        self, model: str, prompt: str, options: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[TokenChunk]:
        """
        Generate text with streaming via LiteLLM.

        Args:
            model: Model name (can override instance default)
            prompt: Input prompt text
            options: Generation options (temperature, max_tokens, etc.)

        Yields:
            TokenChunk objects with incremental text
        """
        opts = options or {}
        model_to_use = model or self._model

        # Build LiteLLM kwargs
        kwargs = self._build_kwargs(prompt, opts, stream=True)

        self._logger.debug(
            "litellm_streaming",
            model=model_to_use,
            prompt_length=len(prompt),
        )

        try:
            response = await acompletion(
                model=model_to_use,
                **kwargs,
            )

            async for chunk in response:
                # Extract content from chunk
                choices = getattr(chunk, "choices", [])
                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                if not delta:
                    continue

                content = getattr(delta, "content", None)
                finish_reason = getattr(choices[0], "finish_reason", None)

                if content:
                    yield TokenChunk(
                        text=content,
                        is_final=False,
                        token_count=1,
                    )

                if finish_reason:
                    yield TokenChunk(text="", is_final=True, token_count=0)
                    return

            # Ensure we always emit final chunk
            yield TokenChunk(text="", is_final=True, token_count=0)

        except Exception as e:
            self._logger.error(
                "litellm_stream_error",
                model=model_to_use,
                error=str(e),
            )
            raise

    def _build_kwargs(
        self, prompt: str, options: Dict[str, Any], stream: bool
    ) -> Dict[str, Any]:
        """Build kwargs for litellm.acompletion."""
        kwargs: Dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "timeout": self._timeout,
            "num_retries": self._max_retries,
        }

        # API configuration
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._api_key:
            kwargs["api_key"] = self._api_key

        # Generation parameters
        if options.get("temperature") is not None:
            kwargs["temperature"] = options["temperature"]

        # Handle max_tokens (support both names)
        max_tokens = options.get("max_tokens") or options.get("num_predict")
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # Pass through extra params from init and options
        kwargs.update(self._extra_params)
        for key in ["top_p", "top_k", "stop", "presence_penalty", "frequency_penalty"]:
            if key in options:
                kwargs[key] = options[key]

        return kwargs

    @property
    def supports_streaming(self) -> bool:
        """LiteLLM supports streaming for most providers."""
        return True

    async def health_check(self) -> bool:
        """
        Check if the LLM endpoint is healthy.

        Makes a minimal request to verify connectivity.

        Returns:
            True if endpoint is responsive, False otherwise
        """
        try:
            kwargs = self._build_kwargs("Hi", {}, stream=False)
            kwargs["max_tokens"] = 1

            response = await acompletion(
                model=self._model,
                **kwargs,
            )
            return bool(response.choices)

        except Exception as e:
            self._logger.warning(
                "litellm_health_check_failed",
                model=self._model,
                error=str(e),
            )
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "provider": "litellm",
            "model": self._model,
            "api_base": self._api_base,
            "timeout": self._timeout,
            "max_retries": self._max_retries,
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"LiteLLMProvider(model={self._model}, api_base={self._api_base})"
