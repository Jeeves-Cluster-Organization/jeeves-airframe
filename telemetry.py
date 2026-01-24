from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator


@asynccontextmanager
async def span(name: str, **kwargs) -> AsyncIterator[None]:
    # Placeholder for OTEL span; emits nothing for now.
    yield


@contextmanager
def sync_span(name: str, **kwargs) -> Iterator[None]:
    yield
