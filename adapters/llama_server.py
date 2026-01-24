from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, Iterable, Optional

from airframe.adapters.base import BackendAdapter
from airframe.endpoints import EndpointSpec, BackendKind
from airframe.types import (
    AirframeError,
    ErrorCategory,
    InferenceRequest,
    InferenceStreamEvent,
    StreamEventType,
)

try:
    import httpx
except ImportError:  # pragma: no cover - runtime guard
    httpx = None


def _categorize_exception(exc: Exception) -> AirframeError:
    name = exc.__class__.__name__
    if "Timeout" in name:
        return AirframeError(ErrorCategory.TIMEOUT, str(exc))
    if "Network" in name or "Connect" in name:
        return AirframeError(ErrorCategory.CONNECTION, str(exc))
    return AirframeError(ErrorCategory.BACKEND, str(exc))


def _parse_sse_lines(lines: Iterable[str]) -> Iterable[str]:
    """
    Parse SSE lines (data: ...) into JSON strings.
    """
    for line in lines:
        if not line:
            continue
        if line.startswith("data: "):
            payload = line[len("data: ") :].strip()
        else:
            payload = line.strip()
        if payload == "[DONE]":
            break
        if payload:
            yield payload


class LlamaServerAdapter(BackendAdapter):
    def __init__(self, timeout: float = 120.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def stream_infer(
        self, endpoint: EndpointSpec, request: InferenceRequest
    ) -> AsyncIterator[InferenceStreamEvent]:
        if httpx is None:
            raise RuntimeError("httpx is required for LlamaServerAdapter")

        base_url = endpoint.base_url.rstrip("/")
        api_type = (endpoint.api_type or "native").lower()
        path = "/v1/completions" if api_type == "openai" else "/completion"

        payload: Dict[str, Any] = self._build_payload(api_type, request)

        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            headers={"Content-Type": "application/json"},
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
                        text = data.get("content") or data.get("choices", [{}])[0].get(
                            "text", ""
                        )
                        yield InferenceStreamEvent(
                            type=StreamEventType.MESSAGE,
                            content=text,
                            raw=data,
                            finish_reason=data.get("stop_type")
                            or data.get("choices", [{}])[0].get("finish_reason"),
                            usage=data.get("usage"),
                        )
                        yield InferenceStreamEvent(type=StreamEventType.DONE)
                        return
                except Exception as exc:  # broad catch to attach backend info
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

    def _build_payload(self, api_type: str, request: InferenceRequest) -> Dict[str, Any]:
        if api_type == "openai":
            return {
                "prompt": "\n".join([m.content for m in request.messages]),
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stream": request.stream,
            }
        # native llama.cpp completion
        return {
            "prompt": "\n".join([m.content for m in request.messages]),
            "n_predict": request.max_tokens or 512,
            "temperature": request.temperature or 0.7,
            "stop": [],
            "stream": request.stream,
            "cache_prompt": True,
        }

    async def _stream_sse(self, response: "httpx.Response") -> AsyncIterator[InferenceStreamEvent]:
        async for line in response.aiter_lines():
            for payload in _parse_sse_lines([line]):
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError as exc:
                    err = AirframeError(ErrorCategory.PARSE, str(exc), raw_backend=payload)
                    yield InferenceStreamEvent(type=StreamEventType.ERROR, error=err, raw=payload)
                    continue

                content = data.get("content") or data.get("choices", [{}])[0].get("text")
                is_final = data.get("stop", False) or data.get("done", False)
                finish_reason = data.get("stop_type") or data.get("choices", [{}])[0].get(
                    "finish_reason"
                )

                if content:
                    yield InferenceStreamEvent(type=StreamEventType.TOKEN, content=content, raw=data)
                if is_final or finish_reason:
                    yield InferenceStreamEvent(
                        type=StreamEventType.DONE, finish_reason=finish_reason, raw=data
                    )
                    return
