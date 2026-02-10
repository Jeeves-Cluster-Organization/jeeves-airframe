"""
Tool Catalog Infrastructure - Generic tool registry and definitions.

This module provides the generic infrastructure for tool registration
and execution. Capability-specific tool identifiers (ToolId enums) and
catalog entries are owned by each capability layer.

Provides:
- ToolCatalogEntry: Immutable metadata for each tool
- ToolCatalog: Registry implementing ToolRegistryProtocol
- ToolDefinition: Tool definition for ToolExecutor
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from jeeves_infra.protocols import RiskLevel, ToolCategory


@dataclass(frozen=True)
class ToolCatalogEntry:
    """Immutable tool metadata.

    Frozen dataclass ensures entries cannot be modified after creation,
    supporting the single source of truth pattern.
    """
    id: str
    description: str
    parameters: Dict[str, str]
    category: ToolCategory
    risk_level: RiskLevel = RiskLevel.LOW
    accepts: str = ""
    returns: str = ""

    def to_prompt_line(self) -> str:
        """Format entry for LLM prompt.

        Returns:
            Formatted string like: "- locate(symbol, scope?): Find code anywhere"
        """
        param_parts = []
        for name, ptype in self.parameters.items():
            if ptype.endswith("?") or "optional" in ptype.lower():
                param_parts.append(f"{name}?")
            else:
                param_parts.append(name)
        params = ", ".join(param_parts)
        return f"- {self.id}({params}): {self.description}"


@dataclass
class ToolDefinition:
    """Tool definition for ToolExecutor.

    Implements ToolDefinitionProtocol from protocols.
    This is the object returned by ToolCatalog.get_tool().
    """
    name: str
    function: Callable
    parameters: Dict[str, str]
    description: str = ""


class ToolCatalog:
    """Generic tool catalog - implements ToolRegistryProtocol.

    Registry that:
    - Stores all tool metadata (ToolCatalogEntry)
    - Maps tool name strings to implementation functions
    - Generates consistent prompts for agents
    - Validates tool existence by string name

    Usage:
        catalog = ToolCatalog()

        catalog.register_function(
            tool_name="locate",
            func=locate_impl,
            description="Find code anywhere",
            parameters={"symbol": "string", "scope": "string?"},
            category=ToolCategory.COMPOSITE,
        )
    """

    def __init__(self) -> None:
        """Initialize empty catalog."""
        self._entries: Dict[str, ToolCatalogEntry] = {}
        self._functions: Dict[str, Callable] = {}

    # ═══════════════════════════════════════════════════════════════════════════
    # REGISTRATION METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def register(
        self,
        tool_name: str,
        description: str,
        parameters: Dict[str, str],
        category: ToolCategory,
        risk_level: RiskLevel = RiskLevel.LOW,
        accepts: str = "",
        returns: str = "",
    ) -> Callable:
        """Register tool. Can be used as decorator.

        Args:
            tool_name: String tool identifier
            description: Human-readable description
            parameters: Dict of param_name -> type_description
            category: Tool category
            risk_level: Risk classification
            accepts: Description of accepted input
            returns: Description of returned output

        Returns:
            Decorator function that registers the tool implementation
        """
        entry = ToolCatalogEntry(
            id=tool_name,
            description=description,
            parameters=parameters,
            category=category,
            risk_level=risk_level,
            accepts=accepts,
            returns=returns,
        )
        self._entries[tool_name] = entry

        def decorator(func: Callable) -> Callable:
            self._functions[tool_name] = func
            return func
        return decorator

    def register_function(
        self,
        tool_name: str,
        func: Callable,
        description: str,
        parameters: Dict[str, str],
        category: ToolCategory,
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> None:
        """Register tool without decorator syntax.

        Args:
            tool_name: String tool identifier
            func: Implementation function
            description: Human-readable description
            parameters: Dict of param_name -> type_description
            category: Tool category
            risk_level: Risk classification
        """
        entry = ToolCatalogEntry(
            id=tool_name,
            description=description,
            parameters=parameters,
            category=category,
            risk_level=risk_level,
        )
        self._entries[tool_name] = entry
        self._functions[tool_name] = func

    # ═══════════════════════════════════════════════════════════════════════════
    # TOOLREGISTRYPROTOCOL IMPLEMENTATION (string-based interface)
    # ═══════════════════════════════════════════════════════════════════════════

    def has_tool(self, name: str) -> bool:
        """Check if tool is registered by string name.

        Args:
            name: Tool name string (e.g., "analyze")

        Returns:
            True if tool has both entry and function registered
        """
        return name in self._entries and name in self._functions

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by string name.

        Args:
            name: Tool name string (e.g., "analyze")

        Returns:
            ToolDefinition with function and parameters, or None
        """
        entry = self._entries.get(name)
        func = self._functions.get(name)
        if entry is None or func is None:
            return None
        return ToolDefinition(
            name=name,
            function=func,
            parameters=entry.parameters,
            description=entry.description,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # CATALOG OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def get_entry(self, tool_name: str) -> Optional[ToolCatalogEntry]:
        """Get tool metadata by name.

        Args:
            tool_name: Tool name string

        Returns:
            ToolCatalogEntry if registered, None otherwise
        """
        return self._entries.get(tool_name)

    def get_function(self, tool_name: str) -> Optional[Callable]:
        """Get tool implementation by name.

        Args:
            tool_name: Tool name string

        Returns:
            Implementation function if registered, None otherwise
        """
        return self._functions.get(tool_name)

    def get_entries_by_category(self, category: ToolCategory) -> List[ToolCatalogEntry]:
        """Get all entries in a category.

        Args:
            category: Tool category to filter by

        Returns:
            List of matching entries
        """
        return [e for e in self._entries.values() if e.category == category]

    def generate_prompt(self, allowed_tools: Optional[List[str]] = None) -> str:
        """Generate tool descriptions for agent prompts.

        Args:
            allowed_tools: Optional list of tool names to include.
                           If None, includes all registered tools.

        Returns:
            Formatted multi-line string with tool descriptions
        """
        lines = ["Available Tools:\n"]
        by_category: Dict[ToolCategory, List[ToolCatalogEntry]] = {
            cat: [] for cat in ToolCategory
        }

        tools_to_show = allowed_tools or list(self._entries.keys())
        for name in tools_to_show:
            entry = self._entries.get(name)
            if entry:
                by_category[entry.category].append(entry)

        for category in ToolCategory:
            entries = by_category.get(category, [])
            if entries:
                lines.append(f"\n═══ {category.value.upper()} ═══")
                for entry in sorted(entries, key=lambda e: e.id):
                    lines.append(entry.to_prompt_line())

        return "\n".join(lines)

    def list_all_names(self) -> List[str]:
        """List all registered tool names.

        Returns:
            List of all registered tool name strings
        """
        return list(self._entries.keys())

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Export catalog as dictionary (for serialization/debugging).

        Returns:
            Dict mapping tool names to their metadata
        """
        return {
            name: {
                "description": entry.description,
                "parameters": entry.parameters,
                "category": entry.category.value,
                "risk_level": entry.risk_level.value,
            }
            for name, entry in self._entries.items()
        }
