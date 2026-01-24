"""Tests for OpenAI Chat Completions adapter."""

import pytest

from airframe.adapters.openai_chat import OpenAIChatAdapter, _categorize_exception, _parse_sse_lines
from airframe.endpoints import EndpointSpec, BackendKind
from airframe.airframe_types import InferenceRequest, Message, ErrorCategory


class DummyTimeoutError(Exception):
    pass


class DummyConnectError(Exception):
    pass


def test_categorize_timeout():
    err = _categorize_exception(DummyTimeoutError("timeout"))
    assert err.category == ErrorCategory.TIMEOUT


def test_categorize_connect():
    err = _categorize_exception(DummyConnectError("connection failed"))
    assert err.category == ErrorCategory.CONNECTION


def test_categorize_generic():
    err = _categorize_exception(ValueError("something"))
    assert err.category == ErrorCategory.BACKEND


def test_parse_sse_lines_basic():
    lines = ['data: {"id": "1"}', 'data: {"id": "2"}', 'data: [DONE]']
    payloads = list(_parse_sse_lines(lines))
    assert payloads == ['{"id": "1"}', '{"id": "2"}']


def test_parse_sse_lines_empty():
    lines = ['', '', 'data: {"x": 1}', '']
    payloads = list(_parse_sse_lines(lines))
    assert payloads == ['{"x": 1}']


def test_parse_sse_lines_no_prefix():
    lines = ['{"raw": true}']
    payloads = list(_parse_sse_lines(lines))
    assert payloads == ['{"raw": true}']


def test_build_payload_basic():
    adapter = OpenAIChatAdapter()
    request = InferenceRequest(
        messages=[Message(role="user", content="Hello")],
        model="gpt-4",
        temperature=0.7,
        max_tokens=100,
        stream=True,
    )
    payload = adapter._build_payload(request)

    assert payload["messages"] == [{"role": "user", "content": "Hello"}]
    assert payload["model"] == "gpt-4"
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == 100
    assert payload["stream"] is True


def test_build_payload_no_model():
    adapter = OpenAIChatAdapter()
    request = InferenceRequest(
        messages=[Message(role="user", content="Hi")],
        stream=False,
    )
    payload = adapter._build_payload(request)

    assert "model" not in payload
    assert payload["stream"] is False


def test_build_payload_with_tools():
    from airframe.airframe_types import ToolSpec

    adapter = OpenAIChatAdapter()
    request = InferenceRequest(
        messages=[Message(role="user", content="Call a function")],
        tools=[
            ToolSpec(
                name="get_weather",
                description="Get current weather",
                parameters={"type": "object", "properties": {"city": {"type": "string"}}},
            )
        ],
        stream=True,
    )
    payload = adapter._build_payload(request)

    assert "tools" in payload
    assert len(payload["tools"]) == 1
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["function"]["name"] == "get_weather"


def test_build_payload_extra_params():
    adapter = OpenAIChatAdapter()
    request = InferenceRequest(
        messages=[Message(role="user", content="Test")],
        stream=True,
        extra_params={"top_p": 0.9, "presence_penalty": 0.5},
    )
    payload = adapter._build_payload(request)

    assert payload["top_p"] == 0.9
    assert payload["presence_penalty"] == 0.5


def test_adapter_init_defaults():
    adapter = OpenAIChatAdapter()
    assert adapter.timeout == 120.0
    assert adapter.max_retries == 3


def test_adapter_init_custom():
    adapter = OpenAIChatAdapter(timeout=60.0, max_retries=5)
    assert adapter.timeout == 60.0
    assert adapter.max_retries == 5
