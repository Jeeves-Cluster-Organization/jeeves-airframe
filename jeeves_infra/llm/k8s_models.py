"""
Minimal K8s ConfigMap → LiteLLM Router integration.

Reads LiteLLM model_list from a Kubernetes ConfigMap and provides a Router.
This is the only K8s-specific code needed for LLM orchestration.

Usage:
    registry = K8sLLMRegistry(configmap_name="llm-models", namespace="jeeves")
    router = registry.get_router()
    response = await router.acompletion(model="claude", messages=[...])

ConfigMap format (native LiteLLM model_list):
    data:
      models: |
        [
          {"model_name": "claude", "litellm_params": {"model": "claude-3-sonnet-20240229"}},
          {"model_name": "local", "litellm_params": {"model": "openai/llama", "api_base": "http://llama:8080/v1"}}
        ]
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Callable, List, Optional

try:
    from litellm import Router
except ImportError:
    Router = None  # type: ignore


@dataclass
class WatchHandle:
    """Cancel handle for ConfigMap watch loop."""
    _task: asyncio.Task

    def cancel(self) -> None:
        """Cancel the watch loop."""
        self._task.cancel()


class K8sLLMRegistry:
    """
    Reads LiteLLM model_list from K8s ConfigMap, returns a Router.

    This replaces the entire airframe library with ~80 lines that just
    feed LiteLLM's battle-tested Router.
    """

    def __init__(
        self,
        configmap_name: str,
        namespace: str = "default",
        key: str = "models",
        poll_interval: float = 15.0,
    ):
        """
        Initialize K8s LLM registry.

        Args:
            configmap_name: Name of the ConfigMap containing model definitions
            namespace: Kubernetes namespace
            key: Key in ConfigMap data containing the JSON model list
            poll_interval: Seconds between ConfigMap polls (default: 15s)
        """
        if Router is None:
            raise ImportError("litellm is required: pip install litellm")

        self._configmap_name = configmap_name
        self._namespace = namespace
        self._key = key
        self._poll_interval = poll_interval
        self._client = self._create_client()
        self._last_hash: Optional[str] = None
        self._router: Optional[Router] = None

    def get_router(self) -> Router:
        """
        Get current LiteLLM Router. Refreshes from ConfigMap if needed.

        Returns:
            Configured LiteLLM Router instance
        """
        if self._router is None:
            self._refresh()
        return self._router

    def watch(self, on_change: Optional[Callable[[Router], None]] = None) -> WatchHandle:
        """
        Poll ConfigMap, rebuild Router on changes.

        Args:
            on_change: Optional callback invoked when Router is updated

        Returns:
            WatchHandle to cancel the watch loop
        """
        async def poll():
            while True:
                if self._refresh():
                    if on_change and self._router:
                        on_change(self._router)
                await asyncio.sleep(self._poll_interval)

        task = asyncio.create_task(poll())
        return WatchHandle(task)

    def _refresh(self) -> bool:
        """
        Refresh from ConfigMap. Returns True if router was updated.
        """
        raw = self._read_configmap()
        if raw is None:
            return False

        raw_hash = hashlib.sha256(raw.encode()).hexdigest()
        if raw_hash == self._last_hash:
            return False

        model_list = self._parse(raw)
        if model_list is None:
            return False

        self._router = Router(model_list=model_list)
        self._last_hash = raw_hash
        return True

    def _read_configmap(self) -> Optional[str]:
        """Read raw JSON string from ConfigMap."""
        try:
            cm = self._client.read_namespaced_config_map(
                self._configmap_name,
                self._namespace
            )
            return (cm.data or {}).get(self._key)
        except Exception:
            return None

    def _parse(self, raw: str) -> Optional[List[dict]]:
        """Parse model list from JSON or YAML."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                import yaml
                return yaml.safe_load(raw)
            except Exception:
                return None

    def _create_client(self):
        """Create Kubernetes API client."""
        from kubernetes import client, config
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        return client.CoreV1Api()


# Convenience function for simple usage
def create_router_from_configmap(
    configmap_name: str,
    namespace: str = "default",
    key: str = "models",
) -> Router:
    """
    One-liner to create a LiteLLM Router from a K8s ConfigMap.

    Args:
        configmap_name: Name of the ConfigMap
        namespace: Kubernetes namespace
        key: Key containing the model list JSON

    Returns:
        Configured LiteLLM Router
    """
    registry = K8sLLMRegistry(configmap_name, namespace, key)
    return registry.get_router()
