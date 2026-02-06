"""Governance API router - L7 system introspection endpoints.

Provides REST endpoints for tool health and system observability:
- GET /api/v1/governance/health - System health summary
- GET /api/v1/governance/tools/{tool_name} - Tool health report
- GET /api/v1/governance/dashboard - Governance dashboard
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

# Dependency injection placeholder
_tool_health_service = None


def get_tool_health_service():
    """Dependency injection for ToolHealthService."""
    if _tool_health_service is None:
        raise HTTPException(status_code=503, detail="Governance service not initialized")
    return _tool_health_service


def set_tool_health_service(service) -> None:
    """Set the tool health service instance (called during app startup)."""
    global _tool_health_service
    _tool_health_service = service
