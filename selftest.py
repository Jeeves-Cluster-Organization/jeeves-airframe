from __future__ import annotations

from importlib import metadata


def _version(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except Exception:
        return "unknown"


def run_selftest() -> bool:
    """
    Lightweight import/dep check; no network calls.
    """
    ok = True
    try:
        import httpx  # noqa: F401
        print(f"airframe selftest: httpx {_version('httpx')}")
    except Exception as exc:
        print(f"airframe selftest: missing httpx ({exc})")
        return False

    try:
        from airframe.client import AirframeClient  # noqa: F401
        from airframe.registry import StaticRegistry  # noqa: F401
        from airframe.types import InferenceRequest  # noqa: F401
        print("airframe selftest: core imports ok")
    except Exception as exc:
        print(f"airframe selftest: import failed ({exc})")
        return False

    # Optional K8s deps
    try:
        import kubernetes  # noqa: F401
        print(f"airframe selftest: kubernetes {_version('kubernetes')}")
        try:
            import yaml  # noqa: F401
            print(f"airframe selftest: PyYAML {_version('PyYAML')}")
        except Exception:
            print("airframe selftest: PyYAML not installed (ok)")
    except Exception:
        print("airframe selftest: k8s deps not installed (ok)")

    print("airframe selftest: ok")
    return ok


if __name__ == "__main__":
    run_selftest()
