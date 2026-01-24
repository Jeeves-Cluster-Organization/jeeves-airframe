import asyncio
import os

import pytest

from airframe.adapters.llama_server import LlamaServerAdapter
from airframe.endpoints import EndpointSpec, BackendKind
from airframe.airframe_types import InferenceRequest, Message, StreamEventType


pytestmark = pytest.mark.skipif(
    os.getenv("AIRFRAME_INTEGRATION") != "1",
    reason="Set AIRFRAME_INTEGRATION=1 to run against a real llama-server",
)


@pytest.mark.asyncio
async def test_llama_server_streams_and_finishes():
    host = os.getenv("LLAMASERVER_HOST", "http://localhost:8080")
    endpoint = EndpointSpec(
        name="llama",
        base_url=host,
        backend_kind=BackendKind.LLAMA_SERVER,
        api_type=os.getenv("LLAMASERVER_API_TYPE", "native"),
    )

    adapter = LlamaServerAdapter(timeout=30, max_retries=1)
    req = InferenceRequest(
        messages=[Message(role="user", content="Say 'hello' and stop.")],
        stream=True,
        max_tokens=16,
    )

    tokens = []
    done = False

    async def run():
        nonlocal done
        async for event in adapter.stream_infer(endpoint, req):
            if event.type == StreamEventType.TOKEN:
                tokens.append(event.content or "")
            if event.type == StreamEventType.DONE:
                done = True
                break

    await asyncio.wait_for(run(), timeout=30)
    assert done
    assert tokens
