import asyncio
import types

import pytest

from airframe.adapters.llama_server import LlamaServerAdapter
from airframe.endpoints import EndpointSpec, BackendKind
from airframe.airframe_types import InferenceRequest, Message, ErrorCategory, StreamEventType


class MockTimeout:
    """Mock httpx.Timeout for testing."""
    def __init__(self, timeout=None, connect=None, read=None, write=None, pool=None):
        self.timeout = timeout
        self.connect = connect
        self.read = read
        self.write = write
        self.pool = pool


class ErrorStreamResponse:
    status_code = 500

    async def aread(self):
        return b"fail"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class ErrorClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, path, json):
        return ErrorStreamResponse()


@pytest.mark.asyncio
async def test_backend_http_error_emits_error_event(monkeypatch):
    # Patch httpx.AsyncClient inside adapter module
    import airframe.adapters.llama_server as ls

    monkeypatch.setattr(ls, "httpx", types.SimpleNamespace(AsyncClient=ErrorClient, Timeout=MockTimeout))

    adapter = LlamaServerAdapter(timeout=1, max_retries=1)
    endpoint = EndpointSpec(
        name="err",
        base_url="http://x",
        backend_kind=BackendKind.LLAMA_SERVER,
    )
    req = InferenceRequest(messages=[Message(role="user", content="hi")])

    events = []
    async for ev in adapter.stream_infer(endpoint, req):
        events.append(ev)

    assert events, "expected at least one event"
    assert events[0].type == StreamEventType.ERROR
    assert events[0].error.category == ErrorCategory.BACKEND
    assert events[0].error.raw_backend == b"fail"
