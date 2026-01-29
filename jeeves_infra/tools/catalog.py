"""
Canonical Tool Catalog - Single source of truth for all tools.

Decision 1:A: All tools registered here with typed ToolId, no hardcoded strings.

This module provides:
- ToolId: Typed enum for all tool identifiers (no raw strings)
- ToolCategory: IMPORTED from protocols (canonical location)
- RiskLevel: IMPORTED from protocols (canonical location)
- ToolCatalogEntry: Immutable metadata for each tool
- ToolCatalog: Singleton registry and prompt generation
- ToolDefinition: Tool definition for ToolExecutor (implements ToolDefinitionProtocol)
- EXPOSED_TOOL_IDS: Tools visible to agents

Constitutional Compliance:
- P1 (Accuracy First): Single source of truth prevents drift
- P5 (Deterministic Spine): Typed enums prevent typos/mismatches
- P6 (Observable): Explicit registration for auditability
- Infrastructure R4 (Swappable Implementations): Implements ToolRegistryProtocol
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from jeeves_infra.protocols import RiskLevel, ToolCategory


class ToolId(str, Enum):
    """Typed tool identifiers.

    All tool references must use these enum values, not raw strings.
    This ensures compile-time checking and prevents name mismatches.
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # CODE ANALYSIS TOOLS - Two-path architecture (Amendment XXII v2)
    # ═══════════════════════════════════════════════════════════════════════════
    # Primary search tool - always searches, never assumes paths exist
    SEARCH_CODE = "search_code"
    # Legacy unified tool - kept for backwards compatibility
    ANALYZE = "analyze"

    # ═══════════════════════════════════════════════════════════════════════════
    # COMPOSITE TOOLS (Amendment XVII) - Multi-step workflows with fallbacks
    # ═══════════════════════════════════════════════════════════════════════════
    LOCATE = "locate"
    EXPLORE_SYMBOL_USAGE = "explore_symbol_usage"
    MAP_MODULE = "map_module"
    TRACE_ENTRY_POINT = "trace_entry_point"
    EXPLAIN_CODE_HISTORY = "explain_code_history"

    # ═══════════════════════════════════════════════════════════════════════════
    # RESILIENT TOOLS (Amendment XXI) - Wrapped base tools with retry/fallback
    # ═══════════════════════════════════════════════════════════════════════════
    READ_CODE = "read_code"
    FIND_RELATED = "find_related"

    # ═══════════════════════════════════════════════════════════════════════════
    # STANDALONE TOOLS - Simple tools that don't need wrapping
    # ═══════════════════════════════════════════════════════════════════════════
    GIT_STATUS = "git_status"
    LIST_TOOLS = "list_tools"

    # ═══════════════════════════════════════════════════════════════════════════
    # INTERNAL/BASE TOOLS - Implementation details, not exposed to agents
    # ═══════════════════════════════════════════════════════════════════════════
    # Core traversal
    READ_FILE = "read_file"
    GLOB_FILES = "glob_files"
    GREP_SEARCH = "grep_search"
    TREE_STRUCTURE = "tree_structure"

    # Code parser
    FIND_SYMBOL = "find_symbol"
    GET_FILE_SYMBOLS = "get_file_symbols"
    GET_IMPORTS = "get_imports"
    GET_IMPORTERS = "get_importers"
    PARSE_SYMBOLS = "parse_symbols"
    FIND_REFERENCES = "find_references"
    GET_DEPENDENCIES = "get_dependencies"
    GET_DEPENDENTS = "get_dependents"

    # File navigation
    LIST_FILES = "list_files"
    SEARCH_FILES = "search_files"
    GET_PROJECT_TREE = "get_project_tree"

    # Semantic/RAG
    SEMANTIC_SEARCH = "semantic_search"
    FIND_SIMILAR_FILES = "find_similar_files"
    GET_INDEX_STATS = "get_index_stats"

    # Git
    GIT_LOG = "git_log"
    GIT_BLAME = "git_blame"
    GIT_DIFF = "git_diff"

    # Session
    GET_SESSION_STATE = "get_session_state"
    SAVE_SESSION_STATE = "save_session_state"

    # ═══════════════════════════════════════════════════════════════════════════
    # NOTE: Capability-specific tools are NOT defined here.
    # Each capability owns its own CapabilityToolCatalog (see protocols.capability).
    # This enum only contains core/infrastructure tools and code-analysis tools.
    # ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ToolCatalogEntry:
    """Immutable tool metadata.

    Frozen dataclass ensures entries cannot be modified after creation,
    supporting the single source of truth pattern.
    """
    id: ToolId
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
        return f"- {self.id.value}({params}): {self.description}"


# ═══════════════════════════════════════════════════════════════════════════════
# EXPOSED TOOL IDS - Tools visible to agents (Decision 2:B)
# Only Traverser can execute, but Planner can see for planning
# ═══════════════════════════════════════════════════════════════════════════════
EXPOSED_TOOL_IDS: FrozenSet[ToolId] = frozenset({
    # Unified Analyzer (Amendment XXII) - Primary entry point
    ToolId.ANALYZE,
    # Composite (5) - Now internal, orchestrated by analyze
    ToolId.LOCATE,
    ToolId.EXPLORE_SYMBOL_USAGE,
    ToolId.MAP_MODULE,
    ToolId.TRACE_ENTRY_POINT,
    ToolId.EXPLAIN_CODE_HISTORY,
    # Resilient (2)
    ToolId.READ_CODE,
    ToolId.FIND_RELATED,
    # Standalone (2)
    ToolId.GIT_STATUS,
    ToolId.LIST_TOOLS,
})


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL DEFINITION - Implements ToolDefinitionProtocol
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS - Must be defined before ToolCatalog uses them
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_tool_id(name: str) -> Optional[ToolId]:
    """Resolve string tool name to ToolId.

    Args:
        name: Tool name string (e.g., "locate")

    Returns:
        ToolId if valid, None otherwise
    """
    try:
        return ToolId(name)
    except ValueError:
        return None


def is_exposed_tool(tool_id: ToolId) -> bool:
    """Check if tool is in exposed set.

    Args:
        tool_id: Tool to check

    Returns:
        True if tool should be visible to agents
    """
    return tool_id in EXPOSED_TOOL_IDS


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL CATALOG - Implements ToolRegistryProtocol
# ═══════════════════════════════════════════════════════════════════════════════

class ToolCatalog:
    """Canonical tool catalog - single source of truth (Decision 1:A).

    Implements ToolRegistryProtocol from protocols.

    Singleton registry that:
    - Stores all tool metadata (ToolCatalogEntry)
    - Maps ToolId to implementation functions
    - Generates consistent prompts for Planner
    - Validates tool existence by typed ID or string name

    Usage:
        catalog = ToolCatalog.get_instance()

        @catalog.register(
            tool_id=ToolId.LOCATE,
            description="Find code anywhere",
            parameters={"symbol": "string", "scope": "string?"},
            category=ToolCategory.COMPOSITE,
        )
        async def locate(symbol: str, scope: str = None):
            ...
    """

    _instance: Optional["ToolCatalog"] = None

    def __init__(self) -> None:
        """Initialize empty catalog.

        Use get_instance() for singleton access.
        """
        self._entries: Dict[ToolId, ToolCatalogEntry] = {}
        self._functions: Dict[ToolId, Callable] = {}

    @classmethod
    def get_instance(cls) -> "ToolCatalog":
        """Get singleton instance.

        Returns:
            The global ToolCatalog instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing only)."""
        cls._instance = None

    # ═══════════════════════════════════════════════════════════════════════════
    # REGISTRATION METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def register(
        self,
        tool_id: ToolId,
        description: str,
        parameters: Dict[str, str],
        category: ToolCategory,
        risk_level: RiskLevel = RiskLevel.LOW,
        accepts: str = "",
        returns: str = "",
    ) -> Callable:
        """Register tool. Can be used as decorator.

        Args:
            tool_id: Typed tool identifier
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
            id=tool_id,
            description=description,
            parameters=parameters,
            category=category,
            risk_level=risk_level,
            accepts=accepts,
            returns=returns,
        )
        self._entries[tool_id] = entry

        def decorator(func: Callable) -> Callable:
            self._functions[tool_id] = func
            return func
        return decorator

    def register_function(
        self,
        tool_id: ToolId,
        func: Callable,
        description: str,
        parameters: Dict[str, str],
        category: ToolCategory,
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> None:
        """Register tool without decorator syntax.

        Args:
            tool_id: Typed tool identifier
            func: Implementation function
            description: Human-readable description
            parameters: Dict of param_name -> type_description
            category: Tool category
            risk_level: Risk classification
        """
        entry = ToolCatalogEntry(
            id=tool_id,
            description=description,
            parameters=parameters,
            category=category,
            risk_level=risk_level,
        )
        self._entries[tool_id] = entry
        self._functions[tool_id] = func

    # ═══════════════════════════════════════════════════════════════════════════
    # TOOLREGISTRYPROTOCOL IMPLEMENTATION (string-based interface)
    # ═══════════════════════════════════════════════════════════════════════════

    def has_tool(self, name: str) -> bool:
        """Check if tool is registered by string name.

        Implements ToolRegistryProtocol.has_tool().

        Args:
            name: Tool name string (e.g., "analyze")

        Returns:
            True if tool has both entry and function registered
        """
        tool_id = resolve_tool_id(name)
        if tool_id is None:
            return False
        return tool_id in self._entries and tool_id in self._functions

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by string name.

        Implements ToolRegistryProtocol.get_tool().

        Args:
            name: Tool name string (e.g., "analyze")

        Returns:
            ToolDefinition with function and parameters, or None
        """
        tool_id = resolve_tool_id(name)
        if tool_id is None:
            return None
        entry = self._entries.get(tool_id)
        func = self._functions.get(tool_id)
        if entry is None or func is None:
            return None
        return ToolDefinition(
            name=name,
            function=func,
            parameters=entry.parameters,
            description=entry.description,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # TOOLID-BASED ACCESS (typed interface for internal use)
    # ═══════════════════════════════════════════════════════════════════════════

    def has_tool_id(self, tool_id: ToolId) -> bool:
        """Check if tool is registered by ToolId.

        Args:
            tool_id: Typed tool identifier

        Returns:
            True if tool has both entry and function registered
        """
        return tool_id in self._entries and tool_id in self._functions

    def get_entry(self, tool_id: ToolId) -> Optional[ToolCatalogEntry]:
        """Get tool metadata by ToolId.

        Args:
            tool_id: Typed tool identifier

        Returns:
            ToolCatalogEntry if registered, None otherwise
        """
        return self._entries.get(tool_id)

    def get_function(self, tool_id: ToolId) -> Optional[Callable]:
        """Get tool implementation by ToolId.

        Args:
            tool_id: Typed tool identifier

        Returns:
            Implementation function if registered, None otherwise
        """
        return self._functions.get(tool_id)

    def has_entry(self, tool_id: ToolId) -> bool:
        """Check if tool entry exists (may not have function yet).

        Args:
            tool_id: Typed tool identifier

        Returns:
            True if entry registered
        """
        return tool_id in self._entries

    # ═══════════════════════════════════════════════════════════════════════════
    # CATALOG OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def get_exposed_entries(self) -> List[ToolCatalogEntry]:
        """Get entries for all exposed tools.

        Returns:
            List of ToolCatalogEntry for tools in EXPOSED_TOOL_IDS
        """
        return [self._entries[tid] for tid in EXPOSED_TOOL_IDS if tid in self._entries]

    def get_entries_by_category(self, category: ToolCategory) -> List[ToolCatalogEntry]:
        """Get all entries in a category.

        Args:
            category: Tool category to filter by

        Returns:
            List of matching entries
        """
        return [e for e in self._entries.values() if e.category == category]

    def generate_planner_prompt(self, allowed_tools: FrozenSet[ToolId]) -> str:
        """Generate tool descriptions for Planner prompt (Decision 1:A).

        This replaces hardcoded tool lists in planner.py.
        Generates consistent, up-to-date tool documentation.

        Args:
            allowed_tools: Set of ToolIds the Planner can reference

        Returns:
            Formatted multi-line string with tool descriptions
        """
        lines = ["Available Tools:\n"]
        by_category: Dict[ToolCategory, List[ToolCatalogEntry]] = {
            cat: [] for cat in ToolCategory
        }

        for tid in allowed_tools:
            entry = self._entries.get(tid)
            if entry:
                by_category[entry.category].append(entry)

        # Order: Unified, Composite, Resilient, Standalone (skip Internal)
        if by_category[ToolCategory.UNIFIED]:
            lines.append("═══ UNIFIED (primary entry point) ═══")
            for entry in sorted(by_category[ToolCategory.UNIFIED], key=lambda e: e.id.value):
                lines.append(entry.to_prompt_line())

        if by_category[ToolCategory.COMPOSITE]:
            lines.append("\n═══ COMPOSITE (multi-step workflows) ═══")
            for entry in sorted(by_category[ToolCategory.COMPOSITE], key=lambda e: e.id.value):
                lines.append(entry.to_prompt_line())

        if by_category[ToolCategory.RESILIENT]:
            lines.append("\n═══ RESILIENT (with fallbacks) ═══")
            for entry in sorted(by_category[ToolCategory.RESILIENT], key=lambda e: e.id.value):
                lines.append(entry.to_prompt_line())

        if by_category[ToolCategory.STANDALONE]:
            lines.append("\n═══ STANDALONE ═══")
            for entry in sorted(by_category[ToolCategory.STANDALONE], key=lambda e: e.id.value):
                lines.append(entry.to_prompt_line())

        return "\n".join(lines)

    def list_all_ids(self) -> List[ToolId]:
        """List all registered tool IDs.

        Returns:
            List of all registered ToolIds
        """
        return list(self._entries.keys())

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Export catalog as dictionary (for serialization/debugging).

        Returns:
            Dict mapping tool names to their metadata
        """
        return {
            tid.value: {
                "description": entry.description,
                "parameters": entry.parameters,
                "category": entry.category.value,
                "risk_level": entry.risk_level.value,
            }
            for tid, entry in self._entries.items()
        }


# Global singleton instance
tool_catalog = ToolCatalog.get_instance()
