from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from airframe.endpoints import EndpointSpec
from airframe.types import InferenceRequest, InferenceStreamEvent


class BackendAdapter(ABC):
    @abstractmethod
    async def stream_infer(
        self, endpoint: EndpointSpec, request: InferenceRequest
    ) -> AsyncIterator[InferenceStreamEvent]:
        ...
