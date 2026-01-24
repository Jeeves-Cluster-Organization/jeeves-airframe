from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Awaitable, Callable, List, Optional

from airframe.endpoints import BackendKind, EndpointSpec, HealthState, CapacityHints
from airframe.registry import EndpointRegistry, WatchHandle


class K8sRegistry(EndpointRegistry):
    """
    Read endpoints from a single ConfigMap.

    Schema (fixed):
      data[key] contains a JSON string representing:
        [
          {
            "name": "...",
            "base_url": "...",
            "backend_kind": "llama_server|openai_chat|anthropic_messages",
            "api_type": "native|openai",
            "tags": {...},
            "capacity": {"max_concurrency": 4, "tier": "A100-80GB"},
            "metadata": {...}
          },
          ...
        ]
    """

    def __init__(
        self,
        *,
        configmap_name: str,
        namespace: str,
        key: str = "endpoints",
        poll_interval: float = 15.0,
        client: Optional[object] = None,
    ):
        self._configmap_name = configmap_name
        self._namespace = namespace
        self._key = key
        self._poll_interval = poll_interval
        self._client = client or self._create_client()

        self._endpoints: List[EndpointSpec] = []
        self._health = {}
        self._last_hash: Optional[str] = None
        self._last_error: Optional[str] = None

    def list_endpoints(self) -> List[EndpointSpec]:
        return list(self._endpoints)

    def get_health(self, name: str) -> Optional[HealthState]:
        return self._health.get(name)

    def last_error(self) -> Optional[str]:
        return self._last_error

    def watch(
        self, callback: Callable[[List[EndpointSpec]], Awaitable[None]]
    ) -> WatchHandle:
        try:
            asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError("K8sRegistry.watch requires an active asyncio event loop") from exc

        async def poll():
            # Always emit once on start if possible
            await self._refresh_and_notify(callback, emit_if_changed=True, emit_on_start=True)
            while True:
                await asyncio.sleep(self._poll_interval)
                await self._refresh_and_notify(callback, emit_if_changed=True, emit_on_start=False)

        task = asyncio.create_task(poll())
        return WatchHandle(task)

    async def _refresh_and_notify(
        self,
        callback: Callable[[List[EndpointSpec]], Awaitable[None]],
        *,
        emit_if_changed: bool,
        emit_on_start: bool,
    ) -> None:
        raw = self._read_configmap_value()
        if raw is None:
            return

        raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if emit_if_changed and raw_hash == self._last_hash and not emit_on_start:
            return

        endpoints = self._parse_endpoints(raw)
        if endpoints is None:
            # Parsing failed; keep last-good snapshot and do not emit.
            return

        self._endpoints = endpoints
        self._last_hash = raw_hash
        await callback(self.list_endpoints())

    def _read_configmap_value(self) -> Optional[str]:
        try:
            cm = self._client.read_namespaced_config_map(self._configmap_name, self._namespace)
            data = getattr(cm, "data", None) or {}
            raw = data.get(self._key)
            if raw is None:
                self._last_error = f"ConfigMap missing key '{self._key}'"
                return None
            self._last_error = None
            return raw
        except Exception as exc:
            self._last_error = f"Failed to read ConfigMap: {exc}"
            return None

    def _parse_endpoints(self, raw: str) -> Optional[List[EndpointSpec]]:
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = self._maybe_parse_yaml(raw)
            if parsed is None:
                self._last_error = "ConfigMap value is not valid JSON (and YAML unavailable)"
                return None

        if not isinstance(parsed, list):
            self._last_error = "ConfigMap JSON must be a list of endpoints"
            return None

        endpoints: List[EndpointSpec] = []
        for item in parsed:
            try:
                endpoints.append(self._endpoint_from_dict(item))
            except Exception as exc:
                self._last_error = f"Invalid endpoint entry: {exc}"
                return None

        self._last_error = None
        return endpoints

    def _endpoint_from_dict(self, item: dict) -> EndpointSpec:
        backend_kind = BackendKind(item["backend_kind"])
        capacity = item.get("capacity") or {}
        return EndpointSpec(
            name=item["name"],
            base_url=item["base_url"],
            backend_kind=backend_kind,
            api_type=item.get("api_type"),
            tags=item.get("tags") or {},
            capacity=CapacityHints(
                max_concurrency=capacity.get("max_concurrency"),
                tier=capacity.get("tier"),
            ),
            metadata=item.get("metadata") or {},
        )

    def _maybe_parse_yaml(self, raw: str):
        try:
            import yaml  # type: ignore
        except Exception:
            return None
        try:
            return yaml.safe_load(raw)
        except Exception:
            return None

    def _create_client(self):
        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config
        except Exception as exc:
            raise ImportError("kubernetes client not installed; install with airframe[k8s]") from exc

        # Load in-cluster config if available; fallback to local kubeconfig
        try:
            k8s_config.load_incluster_config()
        except Exception:
            k8s_config.load_kube_config()

        return k8s_client.CoreV1Api()
