"""LLM Provider Base Class.

Split from provider.py per Module Bloat Audit (2025-12-09).
Constitutional Reference: Infrastructure R1 (Adapter Pattern)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional


@dataclass
class TokenChunk:
    """A chunk of streamed tokens from an LLM.

    Represents incremental output during streaming generation.
    """
    text: str
    """The text content of this chunk"""

    is_final: bool = False
    """True if this is the last chunk in the stream"""

    token_count: int = 0
    """Estimated tokens in this chunk (0 if unknown)"""

    metadata: Optional[Dict[str, Any]] = None
    """Provider-specific metadata"""


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All providers must implement the generate method which takes a model name,
    prompt, and options dict, and returns the generated text asynchronously.

    Providers may optionally implement generate_stream for streaming support.
    """

    @abstractmethod
    async def generate(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate text from a prompt.

        Args:
            model: Model identifier (e.g., "gpt-4", "llama3.1:8b")
            prompt: Input prompt text
            options: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            Generated text string

        Raises:
            Exception: If generation fails
        """
        pass

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[TokenChunk]:
        """Generate text from a prompt with streaming output.

        Default implementation falls back to non-streaming generate().
        Providers should override this for true streaming support.

        Args:
            model: Model identifier (e.g., "gpt-4", "llama3.1:8b")
            prompt: Input prompt text
            options: Provider-specific options (temperature, max_tokens, etc.)

        Yields:
            TokenChunk objects containing incremental text

        Raises:
            Exception: If generation fails
        """
        # Default fallback: call generate() and yield entire result
        result = await self.generate(model, prompt, options)
        yield TokenChunk(
            text=result,
            is_final=True,
            token_count=len(result) // 4,  # Rough estimate
        )

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is available and responding.

        Returns:
            True if provider is healthy, False otherwise
        """
        pass

    @property
    def supports_streaming(self) -> bool:
        """Check if this provider supports true streaming.

        Returns:
            True if provider has native streaming support
        """
        # Subclasses with native streaming should override this
        return False


__all__ = ["LLMProvider", "TokenChunk"]
