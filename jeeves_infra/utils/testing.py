"""Shared testing utilities used across jeeves packages.

Provides common test helper functions to avoid duplication across
avionics, mission_system, and other test suites.

Usage:
    from jeeves_infra.utils.testing import is_running_in_docker, parse_postgres_url
"""

import os
from typing import Dict


def is_running_in_docker() -> bool:
    """Check if we're running inside a Docker container.

    Detection methods:
    1. POSTGRES_HOST environment variable set to 'postgres' (compose network)
    2. /.dockerenv file exists
    3. Current working directory is /app (common container workdir)
    4. /proc/1/cgroup contains 'docker' or 'containerd'

    Returns:
        True if running in Docker, False otherwise
    """
    if os.environ.get("POSTGRES_HOST") == "postgres":
        return True
    if os.path.exists("/.dockerenv"):
        return True
    if os.getcwd() == "/app":
        return True
    try:
        with open("/proc/1/cgroup", "r") as f:
            content = f.read()
            return "docker" in content or "containerd" in content
    except (FileNotFoundError, PermissionError):
        pass
    return False


def parse_postgres_url(url: str) -> Dict[str, str]:
    """Parse PostgreSQL URL into components for environment variables.

    Handles both standard and asyncpg URL formats.

    Args:
        url: PostgreSQL URL like postgresql+asyncpg://user:pass@host:port/db

    Returns:
        Dict with POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DATABASE,
        POSTGRES_USER, POSTGRES_PASSWORD

    Example:
        url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        env = parse_postgres_url(url)
        # env = {
        #     "POSTGRES_HOST": "localhost",
        #     "POSTGRES_PORT": "5432",
        #     "POSTGRES_DATABASE": "testdb",
        #     "POSTGRES_USER": "user",
        #     "POSTGRES_PASSWORD": "pass",
        # }
    """
    from urllib.parse import urlparse

    # Normalize URL format for parsing
    normalized = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(normalized)

    return {
        "POSTGRES_HOST": parsed.hostname or "localhost",
        "POSTGRES_PORT": str(parsed.port or 5432),
        "POSTGRES_DATABASE": parsed.path.lstrip("/") if parsed.path else "test",
        "POSTGRES_USER": parsed.username or "postgres",
        "POSTGRES_PASSWORD": parsed.password or "",
    }


__all__ = [
    "is_running_in_docker",
    "parse_postgres_url",
]
