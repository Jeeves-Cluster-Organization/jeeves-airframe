import asyncio

import pytest

from airframe.adapters.llama_server import LlamaServerAdapter
from airframe.airframe_types import StreamEventType


class FakeResponse:
    def __init__(self, lines):
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line


@pytest.mark.asyncio
async def test_stream_done_emitted_once():
    adapter = LlamaServerAdapter()
    lines = [
        'data: {"content":"Hi"}',
        'data: {"content":"","stop": true}',
        'data: {"content":"ignored"}',
    ]
    events = []
    async for ev in adapter._stream_sse(FakeResponse(lines)):
        events.append(ev)

    done_events = [e for e in events if e.type == StreamEventType.DONE]
    assert len(done_events) == 1
    assert any(e.type == StreamEventType.TOKEN for e in events)
