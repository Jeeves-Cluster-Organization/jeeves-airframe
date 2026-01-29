"""Service Availability Detection for Tests.

Provides centralized service detection for test skip logic:
- PostgreSQL availability
- llama-server availability
- API availability

Services are checked via actual connectivity - no environment magic.
Configure hosts via env vars: POSTGRES_HOST, LLAMASERVER_HOST, API_HOST.

Constitutional Compliance:
- P6: Testable - environment-aware test execution
- M4: Observability - clear service status reporting

Usage:
    from mission_system.tests.config.services import (
        is_postgres_available,
        is_llama_server_available,
        is_api_available,
        are_all_services_available,
    )

    # In marker skip logic:
    if not are_all_services_available():
        pytest.skip("Docker services not available")
"""

import os
import socket
import urllib.request
import urllib.error
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from mission_system.tests.config.environment import (
    TEST_POSTGRES_HOST,
    TEST_POSTGRES_PORT,
    TEST_POSTGRES_USER,
    TEST_POSTGRES_PASSWORD,
    TEST_POSTGRES_DATABASE,
)


@dataclass
class ServiceStatus:
    """Status of a service check."""
    available: bool
    host: str
    port: int
    error: Optional[str] = None


# ============================================================
# Service Hosts (from env vars with defaults)
# ============================================================

def _get_postgres_host() -> str:
    """Get PostgreSQL host from env var or default."""
    return TEST_POSTGRES_HOST


def _get_llama_server_host() -> str:
    """Get llama-server host from env var or default."""
    env_host = os.getenv("LLAMASERVER_HOST", "localhost")
    # Extract host from URL if needed
    if env_host.startswith("http"):
        return env_host.replace("http://", "").replace("https://", "").split(":")[0]
    return env_host.split(":")[0]


def _get_api_host() -> str:
    """Get API host from env var or default."""
    env_host = os.getenv("API_HOST", "localhost")
    # Extract host from URL if needed
    if env_host.startswith("http"):
        host_part = env_host.replace("http://", "").replace("https://", "")
        return host_part.split(":")[0]
    return env_host.split(":")[0]


# ============================================================
# Service Availability Checks
# ============================================================

def is_postgres_available(timeout: float = 2.0) -> bool:
    """Check if PostgreSQL is available.

    Uses socket connection to test TCP connectivity, then
    optionally tests actual psycopg2 connection.

    Args:
        timeout: Connection timeout in seconds

    Returns:
        True if PostgreSQL is reachable
    """
    host = _get_postgres_host()
    port = TEST_POSTGRES_PORT

    # Quick TCP check first
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        if result != 0:
            return False
    except (socket.error, OSError):
        return False

    # Try actual database connection
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=TEST_POSTGRES_USER,
            password=TEST_POSTGRES_PASSWORD,
            database=TEST_POSTGRES_DATABASE,
            connect_timeout=int(timeout)
        )
        conn.close()
        return True
    except ImportError:
        # psycopg2 not available, TCP check passed
        return True
    except Exception:
        return False


def is_llama_server_available(timeout: float = 2.0) -> bool:
    """Check if llama-server is available via /health endpoint.

    Args:
        timeout: Request timeout in seconds

    Returns:
        True if llama-server health check passes
    """
    host = _get_llama_server_host()
    port = 8080
    url = f"http://{host}:{port}/health"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def is_api_available(timeout: float = 2.0) -> bool:
    """Check if the API service is available via /health endpoint.

    Args:
        timeout: Request timeout in seconds

    Returns:
        True if API health check passes
    """
    host = _get_api_host()
    port = 8000
    url = f"http://{host}:{port}/health"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def are_all_services_available(timeout: float = 2.0) -> bool:
    """Check if all Docker services are available.

    This is the composite check for @pytest.mark.requires_services.

    Args:
        timeout: Timeout for each service check

    Returns:
        True if PostgreSQL AND llama-server are available
    """
    return (
        is_postgres_available(timeout) and
        is_llama_server_available(timeout)
    )


# ============================================================
# Cached Status (for expensive checks)
# ============================================================

@lru_cache(maxsize=1)
def get_cached_service_status() -> dict:
    """Get cached service availability status.

    Useful for pytest_collection_modifyitems where we check many items.
    Cache is cleared per test session.

    Returns:
        Dict with service availability flags
    """
    return {
        "postgres": is_postgres_available(),
        "llama_server": is_llama_server_available(),
        "api": is_api_available(),
        "all_services": are_all_services_available(),
    }


def clear_service_cache() -> None:
    """Clear the service status cache.

    Call this at the start of a test session or when services change.
    """
    get_cached_service_status.cache_clear()


# ============================================================
# Status Reporting
# ============================================================

def get_service_status_report() -> str:
    """Generate human-readable service status report.

    Useful for test setup diagnostics.

    Returns:
        Multi-line status report string
    """
    status = get_cached_service_status()

    lines = [
        "Service Status Report",
        "=" * 40,
        f"PostgreSQL ({_get_postgres_host()}:{TEST_POSTGRES_PORT}): {'✓' if status['postgres'] else '✗'}",
        f"llama-server ({_get_llama_server_host()}:8080): {'✓' if status['llama_server'] else '✗'}",
        f"API ({_get_api_host()}:8000): {'✓' if status['api'] else '✗'}",
        "-" * 40,
        f"All services available: {'✓' if status['all_services'] else '✗'}",
    ]
    return "\n".join(lines)
