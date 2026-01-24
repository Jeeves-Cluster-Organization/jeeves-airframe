import asyncio
import json
import importlib

import pytest

from airframe.endpoints import BackendKind


class FakeConfigMap:
    def __init__(self, data):
        self.data = data


class FakeCoreV1:
    def __init__(self, raw):
        self.raw = raw

    def read_namespaced_config_map(self, name, namespace):
        if self.raw is None:
            return FakeConfigMap({})
        return FakeConfigMap({"endpoints": self.raw})


@pytest.mark.asyncio
async def test_k8s_registry_parses_json_list():
    pytest.importorskip("kubernetes")
    from airframe.k8s.registry import K8sRegistry

    raw = json.dumps(
        [
            {
                "name": "local",
                "base_url": "http://localhost:8080",
                "backend_kind": "llama_server",
            }
        ]
    )
    reg = K8sRegistry(
        configmap_name="cm",
        namespace="ns",
        client=FakeCoreV1(raw),
    )

    endpoints = reg.list_endpoints()
    assert endpoints == []

    called = asyncio.Event()

    async def cb(snapshot):
        assert snapshot[0].name == "local"
        assert snapshot[0].backend_kind == BackendKind.LLAMA_SERVER
        called.set()

    handle = reg.watch(cb)
    await asyncio.wait_for(called.wait(), timeout=1.0)
    handle.cancel()


@pytest.mark.asyncio
async def test_k8s_registry_watch_change_only():
    pytest.importorskip("kubernetes")
    from airframe.k8s.registry import K8sRegistry

    raw = json.dumps(
        [
            {
                "name": "local",
                "base_url": "http://localhost:8080",
                "backend_kind": "llama_server",
            }
        ]
    )
    client = FakeCoreV1(raw)
    reg = K8sRegistry(
        configmap_name="cm",
        namespace="ns",
        poll_interval=0.05,
        client=client,
    )

    calls = 0

    async def cb(snapshot):
        nonlocal calls
        calls += 1

    handle = reg.watch(cb)
    await asyncio.sleep(0.12)
    assert calls >= 1

    # No change: should not spam
    prev_calls = calls
    await asyncio.sleep(0.12)
    assert calls == prev_calls

    # Change raw string -> emit again
    client.raw = json.dumps(
        [
            {
                "name": "local2",
                "base_url": "http://localhost:8081",
                "backend_kind": "llama_server",
            }
        ]
    )
    await asyncio.sleep(0.12)
    assert calls > prev_calls
    handle.cancel()


@pytest.mark.asyncio
async def test_k8s_registry_missing_key_sets_error_and_no_emit():
    pytest.importorskip("kubernetes")
    from airframe.k8s.registry import K8sRegistry

    client = FakeCoreV1(None)
    reg = K8sRegistry(
        configmap_name="cm",
        namespace="ns",
        poll_interval=0.05,
        client=client,
    )

    calls = 0

    async def cb(snapshot):
        nonlocal calls
        calls += 1

    handle = reg.watch(cb)
    await asyncio.sleep(0.12)
    assert calls == 0
    assert reg.last_error() is not None
    handle.cancel()


@pytest.mark.asyncio
async def test_k8s_registry_invalid_json_keeps_last_good():
    pytest.importorskip("kubernetes")
    from airframe.k8s.registry import K8sRegistry

    valid = json.dumps(
        [
            {
                "name": "local",
                "base_url": "http://localhost:8080",
                "backend_kind": "llama_server",
            }
        ]
    )
    client = FakeCoreV1(valid)
    reg = K8sRegistry(
        configmap_name="cm",
        namespace="ns",
        poll_interval=0.05,
        client=client,
    )

    snapshots = []

    async def cb(snapshot):
        snapshots.append(snapshot)

    handle = reg.watch(cb)
    await asyncio.sleep(0.12)
    assert snapshots
    assert snapshots[-1][0].name == "local"

    # Switch to invalid JSON; should not emit and should keep last-good snapshot.
    client.raw = "{invalid json"
    prev_calls = len(snapshots)
    await asyncio.sleep(0.12)
    assert len(snapshots) == prev_calls
    assert reg.last_error() is not None
    assert reg.list_endpoints()[0].name == "local"
    handle.cancel()


def test_k8s_import_error_when_missing_deps():
    try:
        import kubernetes  # noqa: F401
        has_k8s = True
    except Exception:
        has_k8s = False

    if has_k8s:
        mod = importlib.import_module("airframe.k8s")
        assert hasattr(mod, "K8sRegistry")
    else:
        with pytest.raises(ImportError):
            importlib.import_module("airframe.k8s")
