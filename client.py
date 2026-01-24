from __future__ import annotations

from typing import AsyncIterator, Dict

from airframe.adapters.base import BackendAdapter
from airframe.adapters.llama_server import LlamaServerAdapter
from airframe.adapters.openai_chat import OpenAIChatAdapter
from airframe.endpoints import BackendKind, EndpointSpec
from airframe.registry import EndpointRegistry
from airframe.types import InferenceRequest, InferenceStreamEvent, AirframeError, ErrorCategory, StreamEventType


class AirframeClient:
    def __init__(
        self,
        registry: EndpointRegistry,
        adapter_overrides: Dict[BackendKind, BackendAdapter] | None = None,
    ):
        self.registry = registry
        self.adapters: Dict[BackendKind, BackendAdapter] = {
            BackendKind.LLAMA_SERVER: LlamaServerAdapter(),
            BackendKind.OPENAI_CHAT: OpenAIChatAdapter(),
            BackendKind.ANTHROPIC_MESSAGES: OpenAIChatAdapter(),  # placeholder
        }
        if adapter_overrides:
            self.adapters.update(adapter_overrides)

    async def stream_infer(
        self, endpoint: EndpointSpec, request: InferenceRequest
    ) -> AsyncIterator[InferenceStreamEvent]:
        adapter = self.adapters.get(endpoint.backend_kind)
        if adapter is None:
            err = AirframeError(
                ErrorCategory.UNKNOWN, f"No adapter for backend {endpoint.backend_kind}"
            )
            yield InferenceStreamEvent(type=StreamEventType.ERROR, error=err)
            return
        async for event in adapter.stream_infer(endpoint, request):
            yield event
