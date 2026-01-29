"""Compatibility helpers for httpx TestClient usage.

FastAPI/Starlette's TestClient relies on the older ``httpx.Client(app=...)``
API, but httpx >=0.27 removed the ``app`` keyword.  This module patches
``httpx.Client`` at import time so the legacy keyword continues to work.

Import this module once during application startup (e.g. in api.server)
before creating any TestClient instances.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

import httpx

_PATCHED = False


def _patch_httpx_client_init() -> None:
    """Allow httpx.Client(app=...) for FastAPI's TestClient."""
    global _PATCHED

    if _PATCHED:
        return

    signature = inspect.signature(httpx.Client.__init__)
    if "app" in signature.parameters:
        _PATCHED = True
        return

    original_init: Callable[..., Any] = httpx.Client.__init__

    def patched_init(
        self: httpx.Client,
        *args: Any,
        app: Any | None = None,
        **kwargs: Any,
    ) -> None:
        if app is not None:
            # Provide ASGI transport automatically for backwards compatibility.
            if "transport" not in kwargs or kwargs["transport"] is None:
                kwargs["transport"] = httpx.ASGITransport(app=app)
            # Provide default base_url so relative requests work.
            kwargs.setdefault("base_url", "http://testserver")

        original_init(self, *args, **kwargs)

    httpx.Client.__init__ = patched_init  # type: ignore[assignment]
    _PATCHED = True


_patch_httpx_client_init()
