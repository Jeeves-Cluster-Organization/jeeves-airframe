import asyncio

import pytest

from airframe.adapters.llama_server import LlamaServerAdapter


class InfiniteResponse:
    async def aiter_lines(self):
        while True:
            yield 'data: {"content":"x"}'
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_stream_cancellation_stops_promptly():
    adapter = LlamaServerAdapter()
    response = InfiniteResponse()

    first_token = asyncio.Event()

    async def consume():
        async for _ in adapter._stream_sse(response):
            first_token.set()
            await asyncio.sleep(10)  # keep running until cancelled

    task = asyncio.create_task(consume())
    await asyncio.wait_for(first_token.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
