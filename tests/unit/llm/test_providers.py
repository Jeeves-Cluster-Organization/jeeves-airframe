"""Unit tests for LLM providers.

Tests OpenAIHTTPProvider, LiteLLMProvider, and the factory module.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from jeeves_infra.llm.providers.base import LLMProvider, TokenChunk


# =============================================================================
# Helpers
# =============================================================================

def _make_mock_logger() -> MagicMock:
    """Create a mock that satisfies LoggerProtocol."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.bind = MagicMock(return_value=logger)
    return logger


def _openai_success_json() -> dict:
    """Standard OpenAI-compatible success response."""
    return {
        "choices": [
            {
                "message": {"content": "Hello world"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _make_httpx_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("POST", "http://test/v1/chat/completions"),
    )
    return resp


# =============================================================================
# TestOpenAIHTTPProvider
# =============================================================================

class TestOpenAIHTTPProvider:
    """Tests for OpenAIHTTPProvider."""

    def _make_provider(self, **overrides):
        from jeeves_infra.llm.providers.openai_http_provider import OpenAIHTTPProvider

        defaults = dict(
            model="test-model",
            api_base="http://localhost:8080/v1",
            api_key="sk-test-key",
            timeout=30.0,
            max_retries=2,
            logger=_make_mock_logger(),
        )
        defaults.update(overrides)
        return OpenAIHTTPProvider(**defaults)

    # ------------------------------------------------------------------
    # generate
    # ------------------------------------------------------------------

    async def test_generate_success(self):
        """Mock httpx.AsyncClient.post returning valid OpenAI response, verify text extraction."""
        provider = self._make_provider()

        mock_response = _make_httpx_response(200, _openai_success_json())

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await provider.generate("test-model", "Say hello")

        assert result == "Hello world"

    async def test_generate_retry_on_transient_error(self):
        """First call raises HTTPStatusError (500), second call succeeds."""
        provider = self._make_provider(max_retries=2)

        error_response = _make_httpx_response(500, {"error": "Internal server error"})
        success_response = _make_httpx_response(200, _openai_success_json())

        error = httpx.HTTPStatusError(
            "Server error",
            request=error_response.request,
            response=error_response,
        )

        mock_post = AsyncMock(side_effect=[error, success_response])

        with patch("httpx.AsyncClient.post", mock_post):
            result = await provider.generate("test-model", "Say hello")

        assert result == "Hello world"
        assert mock_post.call_count == 2

    async def test_generate_raises_after_max_retries(self):
        """All calls fail with HTTPStatusError; exception propagates after max_retries."""
        provider = self._make_provider(max_retries=2)

        error_response = _make_httpx_response(500, {"error": "Internal server error"})
        error = httpx.HTTPStatusError(
            "Server error",
            request=error_response.request,
            response=error_response,
        )

        # max_retries=2 means 3 total attempts (initial + 2 retries)
        mock_post = AsyncMock(side_effect=[error, error, error])

        with patch("httpx.AsyncClient.post", mock_post):
            with pytest.raises(httpx.HTTPStatusError):
                await provider.generate("test-model", "Say hello")

        assert mock_post.call_count == 3

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------

    async def test_health_check_healthy(self):
        """Mock GET /models returning 200 -> True."""
        provider = self._make_provider()

        mock_response = _make_httpx_response(200, {"data": []})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            healthy = await provider.health_check()

        assert healthy is True

    async def test_health_check_unhealthy(self):
        """Mock GET /models raising error -> False."""
        provider = self._make_provider()

        with patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            healthy = await provider.health_check()

        assert healthy is False

    # ------------------------------------------------------------------
    # _build_payload
    # ------------------------------------------------------------------

    def test_build_payload_basic(self):
        """Verify payload structure with model, messages, stream."""
        provider = self._make_provider(model="my-model")

        payload = provider._build_payload("Hello", {}, stream=False)

        assert payload["model"] == "my-model"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        assert payload["stream"] is False
        # No temperature or max_tokens when options empty
        assert "temperature" not in payload
        assert "max_tokens" not in payload

    def test_build_payload_with_options(self):
        """Verify temperature and max_tokens are passed through."""
        provider = self._make_provider()

        options = {"temperature": 0.7, "max_tokens": 256, "top_p": 0.9}
        payload = provider._build_payload("Hello", options, stream=True)

        assert payload["stream"] is True
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 256
        assert payload["top_p"] == 0.9

    # ------------------------------------------------------------------
    # _build_headers
    # ------------------------------------------------------------------

    def test_build_headers_with_api_key(self):
        """Verify Authorization header when api_key is set."""
        provider = self._make_provider(api_key="sk-secret")

        headers = provider._build_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer sk-secret"

    def test_build_headers_without_api_key(self):
        """Verify no Authorization header when api_key is None."""
        provider = self._make_provider(api_key=None)

        headers = provider._build_headers()

        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers

    # ------------------------------------------------------------------
    # supports_streaming
    # ------------------------------------------------------------------

    def test_supports_streaming(self):
        """Property returns True."""
        provider = self._make_provider()
        assert provider.supports_streaming is True


# =============================================================================
# TestLiteLLMProvider
# =============================================================================

class TestLiteLLMProvider:
    """Tests for LiteLLMProvider."""

    def _make_provider(self, **overrides):
        from jeeves_infra.llm.providers.litellm_provider import LiteLLMProvider

        defaults = dict(
            model="openai/test-model",
            api_base="http://localhost:8080/v1",
            api_key="sk-test",
            timeout=30.0,
            max_retries=2,
            logger=_make_mock_logger(),
        )
        defaults.update(overrides)
        return LiteLLMProvider(**defaults)

    def _make_litellm_response(self, content: str = "Hello world") -> MagicMock:
        """Build a mock that mimics litellm's ModelResponse."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        return mock_response

    # ------------------------------------------------------------------
    # generate
    # ------------------------------------------------------------------

    async def test_generate_success(self):
        """Mock litellm.acompletion returning valid response."""
        mock_response = self._make_litellm_response("Hello world")

        with patch(
            "jeeves_infra.llm.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            provider = self._make_provider()
            result = await provider.generate("openai/test-model", "Say hello")

        assert result == "Hello world"

    async def test_generate_extracts_content(self):
        """Verify correct extraction from response.choices[0].message.content."""
        custom_text = "The quick brown fox jumps over the lazy dog."
        mock_response = self._make_litellm_response(custom_text)

        with patch(
            "jeeves_infra.llm.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            provider = self._make_provider()
            result = await provider.generate("openai/test-model", "Tell me a sentence")

        assert result == custom_text

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------

    async def test_health_check_healthy(self):
        """Mock acompletion returning valid minimal response -> True."""
        mock_response = self._make_litellm_response("ok")

        with patch(
            "jeeves_infra.llm.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            provider = self._make_provider()
            healthy = await provider.health_check()

        assert healthy is True

    async def test_health_check_unhealthy(self):
        """Mock acompletion raising exception -> False."""
        with patch(
            "jeeves_infra.llm.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Endpoint unreachable"),
        ):
            provider = self._make_provider()
            healthy = await provider.health_check()

        assert healthy is False

    # ------------------------------------------------------------------
    # supports_streaming
    # ------------------------------------------------------------------

    async def test_supports_streaming(self):
        """Property returns True."""
        with patch(
            "jeeves_infra.llm.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
        ):
            provider = self._make_provider()

        assert provider.supports_streaming is True


# =============================================================================
# TestFactory
# =============================================================================

class TestFactory:
    """Tests for the LLM provider factory."""

    def _reset_registry(self):
        """Reset the module-level registry so tests are independent."""
        import jeeves_infra.llm.factory as factory_mod

        factory_mod._REGISTRY.clear()
        factory_mod._loaded = False

    def _make_settings(self, **attrs) -> MagicMock:
        """Build a minimal mock Settings object."""
        settings = MagicMock()
        settings.jeeves_llm_adapter = attrs.get("jeeves_llm_adapter", None)
        settings.jeeves_llm_model = attrs.get("jeeves_llm_model", None)
        settings.default_model = attrs.get("default_model", None)
        settings.jeeves_llm_base_url = attrs.get("jeeves_llm_base_url", None)
        settings.jeeves_llm_api_key = attrs.get("jeeves_llm_api_key", None)
        settings.llm_timeout = attrs.get("llm_timeout", 120)
        settings.llm_max_retries = attrs.get("llm_max_retries", 3)
        return settings

    def test_create_mock_provider(self, monkeypatch):
        """Set MOCK_LLM_ENABLED=true, verify MockProvider created."""
        self._reset_registry()
        monkeypatch.setenv("MOCK_LLM_ENABLED", "true")
        # Clear any adapter/model env vars that might interfere
        monkeypatch.delenv("JEEVES_LLM_ADAPTER", raising=False)
        monkeypatch.delenv("JEEVES_LLM_MODEL", raising=False)

        from jeeves_infra.llm.factory import create_llm_provider
        from jeeves_infra.llm.providers.mock import MockProvider

        settings = self._make_settings()
        provider = create_llm_provider(settings, agent_name="test")

        assert isinstance(provider, MockProvider)

    def test_get_available_adapters(self):
        """Verify returns at least ['mock', 'openai_http']."""
        self._reset_registry()

        from jeeves_infra.llm.factory import get_available_adapters

        adapters = get_available_adapters()

        assert "mock" in adapters
        assert "openai_http" in adapters

    def test_create_requires_model(self, monkeypatch):
        """Verify ValueError when no model configured."""
        self._reset_registry()
        monkeypatch.delenv("MOCK_LLM_ENABLED", raising=False)
        monkeypatch.delenv("JEEVES_LLM_ADAPTER", raising=False)
        monkeypatch.delenv("JEEVES_LLM_MODEL", raising=False)
        monkeypatch.delenv("JEEVES_LLM_BASE_URL", raising=False)
        monkeypatch.delenv("JEEVES_LLM_API_KEY", raising=False)
        monkeypatch.delenv("JEEVES_LLM_TIMEOUT", raising=False)
        monkeypatch.delenv("JEEVES_LLM_MAX_RETRIES", raising=False)

        from jeeves_infra.llm.factory import create_llm_provider

        # Settings with no model at all
        settings = self._make_settings(
            jeeves_llm_model=None,
            default_model=None,
        )

        with pytest.raises(ValueError, match="No LLM model configured"):
            create_llm_provider(settings, agent_name="test")
