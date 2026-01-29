"""LLM Providers Module.

Available adapters (loaded lazily via factory):
- MockProvider: Testing (always available)
- OpenAIHTTPProvider: Direct HTTP (always available)
- LiteLLMProvider: LiteLLM (optional, pip install jeeves-infra[llm])

Use create_llm_provider() from jeeves_infra.llm.factory to get providers.
"""

from .base import LLMProvider, TokenChunk
from .mock import MockProvider

__all__ = [
    "LLMProvider",
    "TokenChunk",
    "MockProvider",
]
