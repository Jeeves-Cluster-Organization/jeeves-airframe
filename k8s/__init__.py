try:
    import kubernetes  # noqa: F401
except Exception as exc:  # pragma: no cover - environment-dependent
    raise ImportError(
        "kubernetes client not installed; install with airframe[k8s]"
    ) from exc

from .registry import K8sRegistry

__all__ = ["K8sRegistry"]
