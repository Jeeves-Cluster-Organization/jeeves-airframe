"""Shared testing utilities used across jeeves packages.

Provides common test helper functions to avoid duplication across
jeeves_infra and capability test suites.

Usage:
    from jeeves_infra.utils.testing import is_running_in_docker, parse_database_url
"""

import os
from typing import Dict


def is_running_in_docker() -> bool:
    """Check if we're running inside a Docker container.

    Detection methods:
    1. DB_HOST environment variable set (compose network)
    2. /.dockerenv file exists
    3. Current working directory is /app (common container workdir)
    4. /proc/1/cgroup contains 'docker' or 'containerd'

    Returns:
        True if running in Docker, False otherwise
    """
    if os.environ.get("DB_HOST") in ("postgres", "db"):
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


def parse_database_url(url: str) -> Dict[str, str]:
    """Parse database URL into components for environment variables.

    Handles standard database URL formats.

    Args:
        url: Database URL like scheme://user:pass@host:port/db

    Returns:
        Dict with DB_HOST, DB_PORT, DB_DATABASE,
        DB_USER, DB_PASSWORD

    Example:
        url = "postgresql://user:pass@localhost:5432/testdb"
        env = parse_database_url(url)
        # env = {
        #     "DB_HOST": "localhost",
        #     "DB_PORT": "5432",
        #     "DB_DATABASE": "testdb",
        #     "DB_USER": "user",
        #     "DB_PASSWORD": "pass",
        # }
    """
    from urllib.parse import urlparse

    # Normalize URL format for parsing
    normalized = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(normalized)

    return {
        "DB_HOST": parsed.hostname or "localhost",
        "DB_PORT": str(parsed.port or 5432),
        "DB_DATABASE": parsed.path.lstrip("/") if parsed.path else "test",
        "DB_USER": parsed.username or "assistant",
        "DB_PASSWORD": parsed.password or "",
    }


__all__ = [
    "is_running_in_docker",
    "parse_database_url",
]
