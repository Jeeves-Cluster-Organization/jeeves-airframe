"""
OpenAI Chat Completions adapter.

Supports OpenAI API and compatible endpoints (Azure OpenAI, vLLM, etc.).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, Iterable, Optional

from airframe.adapters.base import BackendAdapter
from airframe.endpoints import EndpointSpec
from airframe.types import (
    AirframeError,
    ErrorCategory,
    InferenceRequest,
    InferenceStreamEvent,
    StreamEventType,
)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


def _categorize_exception(exc: Exception) -> AirframeError:
    name = exc.__class__.__name__
    if "Timeout" in name:
        return AirframeError(ErrorCategory.TIMEOUT, str(exc))
    if "Network" in name or "Connect" in name:
        return AirframeError(ErrorCategory.CONNECTION, str(exc))
    return AirframeError(ErrorCategory.BACKEND, str(exc))


def _parse_sse_lines(lines: Iterable[str]) -> Iterable[str]:
    """Parse SSE lines (data: ...) into JSON strings."""
    for line in lines:
        if not line:
            continue
        if line.startswith("data: "):
            payload = line[len("data: "):].strip()
        else:
            payload = line.strip()
        if payload == "[DONE]":
            break
        if payload:
            yield payload


class OpenAIChatAdapter(BackendAdapter):
    """
    Adapter for OpenAI Chat Completions API.

    Supports:
    - OpenAI API (api.openai.com)
    - Azure OpenAI
    - OpenAI-compatible endpoints (vLLM, LocalAI, etc.)
    """

    def __init__(self, timeout: float = 120.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def stream_infer(
        self, endpoint: EndpointSpec, request: InferenceRequest
    ) -> AsyncIterator[InferenceStreamEvent]:
        if httpx is None:
            raise RuntimeError("httpx is required for OpenAIChatAdapter")

        base_url = endpoint.base_url.rstrip("/")
        path = "/v1/chat/completions"

        # Build headers
        headers = {"Content-Type": "application/json"}
        api_key = endpoint.metadata.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Azure OpenAI uses api-key header
        azure_key = endpoint.metadata.get("azure_api_key")
        if azure_key:
            headers["api-key"] = azure_key

        payload = self._build_payload(request)

        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            headers=headers,
        ) as client:
            last_error: Optional[Exception] = None
            for attempt in range(self.max_retries):
                try:
                    if request.stream:
                        async with client.stream("POST", path, json=payload) as resp:
                            if resp.status_code >= 400:
                                raw = await resp.aread()
                                err = AirframeError(
                                    ErrorCategory.BACKEND,
                                    f"HTTP {resp.status_code}",
                                    raw_backend=raw,
                                )
                                yield InferenceStreamEvent(type=StreamEventType.ERROR, error=err)
                                return
                            async for event in self._stream_sse(resp):
                                yield event
                            return
                    else:
                        resp = await client.post(path, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        # Extract content from chat completion response
                        choices = data.get("choices", [])
                        if choices:
                            message = choices[0].get("message", {})
                            text = message.get("content", "")
                            finish_reason = choices[0].get("finish_reason")
                        else:
                            text = ""
                            finish_reason = None

                        yield InferenceStreamEvent(
                            type=StreamEventType.MESSAGE,
                            content=text,
                            raw=data,
                            finish_reason=finish_reason,
                            usage=data.get("usage"),
                        )
                        yield InferenceStreamEvent(type=StreamEventType.DONE)
                        return

                except Exception as exc:
                    last_error = exc
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    err = _categorize_exception(exc)
                    yield InferenceStreamEvent(type=StreamEventType.ERROR, error=err, raw=str(exc))
                    return

            if last_error:
                err = _categorize_exception(last_error)
                yield InferenceStreamEvent(type=StreamEventType.ERROR, error=err, raw=str(last_error))

    def _build_payload(self, request: InferenceRequest) -> Dict[str, Any]:
        """Build OpenAI chat completions request payload."""
        messages = [
            {"role": m.role, "content": m.content}
            for m in request.messages
        ]

        payload: Dict[str, Any] = {
            "messages": messages,
            "stream": request.stream,
        }

        if request.model:
            payload["model"] = request.model

        if request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        # Add tools if provided
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.parameters or {},
                    },
                }
                for t in request.tools
            ]

        # Merge any extra params
        payload.update(request.extra_params)

        return payload

    async def _stream_sse(self, response: "httpx.Response") -> AsyncIterator[InferenceStreamEvent]:
        """Parse SSE stream from OpenAI chat completions."""
        async for line in response.aiter_lines():
            for payload in _parse_sse_lines([line]):
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError as exc:
                    err = AirframeError(ErrorCategory.PARSE, str(exc), raw_backend=payload)
                    yield InferenceStreamEvent(type=StreamEventType.ERROR, error=err, raw=payload)
                    continue

                choices = data.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})
                content = delta.get("content")
                finish_reason = choice.get("finish_reason")

                # Handle tool calls in delta
                tool_calls = delta.get("tool_calls")
                if tool_calls:
                    yield InferenceStreamEvent(
                        type=StreamEventType.TOOL_CALL,
                        content=json.dumps(tool_calls),
                        raw=data,
                    )

                if content:
                    yield InferenceStreamEvent(type=StreamEventType.TOKEN, content=content, raw=data)

                if finish_reason:
                    yield InferenceStreamEvent(
                        type=StreamEventType.DONE,
                        finish_reason=finish_reason,
                        raw=data,
                        usage=data.get("usage"),
                    )
                    return
