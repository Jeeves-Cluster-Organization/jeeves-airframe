"""Cost calculation for LLM API usage.

Tracks token usage and converts to USD cost based on provider pricing.
Supports multiple providers with extensible pricing models.
"""

from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class CostMetrics:
    """Cost and usage metrics for an LLM request."""

    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: datetime

    @property
    def tokens_per_dollar(self) -> float:
        """Calculate efficiency: tokens per dollar."""
        return self.total_tokens / self.cost_usd if self.cost_usd > 0 else 0


class CostCalculator:
    """Calculate costs for LLM API usage across providers.

    Pricing is based on per-token costs (as of 2024):
    - LlamaServer: Free (local llama.cpp server)
    - OpenAI GPT-4: $0.03/1K prompt, $0.06/1K completion
    - OpenAI GPT-3.5-turbo: $0.0015/1K prompt, $0.002/1K completion
    - Anthropic Claude Sonnet: $0.003/1K prompt, $0.015/1K completion
    - Anthropic Claude Haiku: $0.00025/1K prompt, $0.00125/1K completion

    Update pricing via environment variables or config if rates change.
    """

    # Pricing per 1K tokens (prompt, completion)
    PRICING: Dict[str, Dict[str, tuple[float, float]]] = {
        "llamaserver": {
            "default": (0.0, 0.0),  # Local = free
        },
        "llamacpp": {
            "default": (0.0, 0.0),  # Local = free
        },
        "openai": {
            "gpt-4": (0.03, 0.06),
            "gpt-4-turbo": (0.01, 0.03),
            "gpt-3.5-turbo": (0.0015, 0.002),
            "default": (0.0015, 0.002),  # Fallback to GPT-3.5 pricing
        },
        "anthropic": {
            "claude-3-opus": (0.015, 0.075),
            "claude-3-sonnet": (0.003, 0.015),
            "claude-3-haiku": (0.00025, 0.00125),
            "default": (0.003, 0.015),  # Fallback to Sonnet pricing
        },
    }

    def __init__(self, custom_pricing: Optional[Dict] = None):
        """Initialize calculator with optional custom pricing.

        Args:
            custom_pricing: Override default pricing. Format:
                {
                    "provider": {
                        "model": (prompt_cost_per_1k, completion_cost_per_1k)
                    }
                }
        """
        self.pricing = self.PRICING.copy()
        if custom_pricing:
            for provider, models in custom_pricing.items():
                if provider in self.pricing:
                    self.pricing[provider].update(models)
                else:
                    self.pricing[provider] = models

    def calculate_cost(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> CostMetrics:
        """Calculate cost for an LLM request.

        Args:
            provider: Provider name (llamaserver, openai, anthropic)
            model: Model name (gpt-4, claude-3-sonnet, etc.)
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens

        Returns:
            CostMetrics with usage and cost information
        """
        # Normalize provider and model names
        provider_lower = provider.lower()
        model_lower = model.lower()

        # Get pricing for provider
        if provider_lower not in self.pricing:
            # Unknown provider - assume free for safety
            prompt_cost_per_1k, completion_cost_per_1k = 0.0, 0.0
        else:
            provider_pricing = self.pricing[provider_lower]

            # Find model pricing (try exact match, then prefix match, then default)
            model_pricing = None

            # Exact match
            if model_lower in provider_pricing:
                model_pricing = provider_pricing[model_lower]
            else:
                # Prefix match (e.g., "gpt-4-0613" matches "gpt-4")
                for pricing_model, pricing in provider_pricing.items():
                    if model_lower.startswith(pricing_model):
                        model_pricing = pricing
                        break

            # Fallback to default
            if model_pricing is None:
                model_pricing = provider_pricing.get("default", (0.0, 0.0))

            prompt_cost_per_1k, completion_cost_per_1k = model_pricing

        # Calculate costs
        prompt_cost = (prompt_tokens / 1000.0) * prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000.0) * completion_cost_per_1k
        total_cost = prompt_cost + completion_cost

        return CostMetrics(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=round(total_cost, 6),  # Round to 6 decimals ($0.000001)
            timestamp=datetime.now(timezone.utc)
        )

    def estimate_cost(
        self,
        provider: str,
        model: str,
        text: str,
        estimated_tokens_per_char: float = 0.25
    ) -> float:
        """Estimate cost for text before sending to LLM.

        Rough estimation based on character count. Not accurate for actual billing.
        Use calculate_cost() with real token counts for precise tracking.

        Args:
            provider: Provider name
            model: Model name
            text: Input text to estimate
            estimated_tokens_per_char: Rough token-to-char ratio (default 0.25)

        Returns:
            Estimated cost in USD
        """
        estimated_tokens = int(len(text) * estimated_tokens_per_char)
        # Assume 2:1 completion ratio for estimation
        metrics = self.calculate_cost(
            provider=provider,
            model=model,
            prompt_tokens=estimated_tokens,
            completion_tokens=estimated_tokens // 2
        )
        return metrics.cost_usd

    def get_pricing(self, provider: str, model: str) -> tuple[float, float]:
        """Get pricing for a specific provider and model.

        Args:
            provider: Provider name
            model: Model name

        Returns:
            Tuple of (prompt_cost_per_1k, completion_cost_per_1k)
        """
        provider_lower = provider.lower()
        model_lower = model.lower()

        if provider_lower not in self.pricing:
            return (0.0, 0.0)

        provider_pricing = self.pricing[provider_lower]

        # Try exact match
        if model_lower in provider_pricing:
            return provider_pricing[model_lower]

        # Try prefix match
        for pricing_model, pricing in provider_pricing.items():
            if model_lower.startswith(pricing_model):
                return pricing

        # Return default
        return provider_pricing.get("default", (0.0, 0.0))


# Global calculator instance
_calculator = CostCalculator()


def get_cost_calculator() -> CostCalculator:
    """Get global cost calculator instance."""
    return _calculator


def calculate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int
) -> CostMetrics:
    """Convenience function for cost calculation using global instance."""
    return _calculator.calculate_cost(provider, model, prompt_tokens, completion_tokens)
