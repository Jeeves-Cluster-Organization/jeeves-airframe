"""Test Endpoint Configuration.

Centralizes URL, port, and host configurations for tests.
All values have sensible defaults for local development.
Override via environment variables when needed.

Usage:
    from mission_system.tests.config.endpoints import TEST_LLAMASERVER_HOST, TEST_API_HOST

Constitutional Compliance:
- Amendment I: Repo Hygiene - Single source of truth for endpoints
- P6: Testable - Consistent configuration across all tests
"""

import os


# =============================================================================
# LlamaServer Configuration (Primary LLM Backend)
# =============================================================================

TEST_LLAMASERVER_HOST = os.getenv("LLAMASERVER_HOST", "http://localhost:8080")
TEST_LLAMASERVER_PORT = 8080
TEST_LLAMASERVER_MULTI_NODE_PORTS = [8080, 8081, 8082, 8083]


# =============================================================================
# API Server Configuration
# =============================================================================

TEST_API_HOST = os.getenv("API_HOST", "http://localhost:8000")
TEST_API_PORT = 8000
TEST_API_BASE_URL = f"{TEST_API_HOST}/api/v1"


# =============================================================================
# WebSocket Configuration
# =============================================================================

TEST_WEBSOCKET_URL = f"ws://{TEST_API_HOST.replace('http://', '').replace('https://', '')}/ws"


# =============================================================================
# Helper Functions
# =============================================================================

def get_llamaserver_url(port: int = TEST_LLAMASERVER_PORT) -> str:
    """Get llama-server URL for a specific port.

    Args:
        port: Port number (default: TEST_LLAMASERVER_PORT)

    Returns:
        Full llama-server URL with specified port
    """
    base_host = os.environ.get("LLAMASERVER_HOST", "localhost")
    # Remove protocol and port if present
    if "://" in base_host:
        base_host = base_host.split("://")[1]
    if ":" in base_host:
        base_host = base_host.rsplit(":", 1)[0]
    return f"http://{base_host}:{port}"


def get_api_url(endpoint: str = "") -> str:
    """Get full API URL for an endpoint.

    Args:
        endpoint: API endpoint path (e.g., "/requests", "/health")

    Returns:
        Full API URL with endpoint
    """
    base = TEST_API_BASE_URL.rstrip("/")
    if endpoint:
        endpoint = "/" + endpoint.lstrip("/")
    return f"{base}{endpoint}"
