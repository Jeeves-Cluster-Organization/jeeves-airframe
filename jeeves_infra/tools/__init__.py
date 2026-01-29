"""
Avionics Tools Module - Canonical Tool Infrastructure.

Decision 1:A Implementation:
- ToolId: Typed enum for all tool identifiers
- ToolCatalog: Singleton registry for tool metadata
- ToolCategory, RiskLevel: Classification enums

This module provides the infrastructure layer for tools.
Capability-specific tool implementations are in the capability layer
(e.g., jeeves-capability-*/tools/).

Usage:
    from avionics.tools import (
        ToolId,
        ToolCatalog,
        ToolCategory,
        RiskLevel,
        tool_catalog,
        EXPOSED_TOOL_IDS,
    )

    # Check tool by typed ID
    if tool_catalog.has_tool_id(ToolId.LOCATE):
        entry = tool_catalog.get_entry(ToolId.LOCATE)

    # Generate Planner prompt
    prompt = tool_catalog.generate_planner_prompt(EXPOSED_TOOL_IDS)
"""

from jeeves_infra.tools.catalog import (
    # Enums
    ToolId,
    ToolCategory,
    RiskLevel,
    # Dataclasses
    ToolCatalogEntry,
    ToolDefinition,
    # Catalog
    ToolCatalog,
    tool_catalog,
    # Constants
    EXPOSED_TOOL_IDS,
    # Helpers
    resolve_tool_id,
    is_exposed_tool,
)


__all__ = [
    # Enums
    "ToolId",
    "ToolCategory",
    "RiskLevel",
    # Dataclasses
    "ToolCatalogEntry",
    "ToolDefinition",
    # Catalog
    "ToolCatalog",
    "tool_catalog",
    # Constants
    "EXPOSED_TOOL_IDS",
    # Helpers
    "resolve_tool_id",
    "is_exposed_tool",
]
