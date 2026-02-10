"""
Infrastructure Wiring - Tool Execution and LLM Provider Factory

This module provides infrastructure primitives for tool execution and
LLM provider creation.

**Key exports:**
- ToolExecutor: Protocol-compliant tool executor with access control
- AgentContext: Context for tool execution with agent identity
- create_tool_executor(): Factory for creating ToolExecutor
- create_llm_provider_factory(): Factory for creating LLM providers

**Decision 2:B Implementation:**
- AgentContext: Identifies calling agent for access enforcement
- ToolExecutor.execute_with_context(): Enforces AGENT_TOOL_ACCESS at runtime
- Only Traverser can execute tools; others get rejection

**Usage:**
    ```python
    from jeeves_infra.wiring import ToolExecutor, AgentContext

    # Create executor with registry
    executor = ToolExecutor(registry=tool_registry, logger=logger)

    # Execute with access control
    context = AgentContext(agent_name="CodeTraverserAgent", request_id="req-123")
    result = await executor.execute_with_context(ToolId.LOCATE, params, context)
    ```
"""

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from jeeves_infra.protocols import (
    AgentToolAccessProtocol,
    LoggerProtocol,
    LLMProviderProtocol,
    ToolRegistryProtocol,
    ToolExecutorProtocol,
)
from jeeves_infra.logging import create_logger
from jeeves_infra.settings import Settings, get_settings
from jeeves_infra.database.client import DatabaseClientProtocol

# LLM provider factory - must be injected by capability/application
# The kernel does not import from jeeves-infra; capabilities register providers at startup
_llm_provider_factory: Optional[Callable[['Settings', str], 'LLMProviderProtocol']] = None


def set_llm_provider_factory(factory: Callable[['Settings', str], 'LLMProviderProtocol']) -> None:
    """Register the LLM provider factory (called by capability at startup).

    Args:
        factory: Function that takes (settings, agent_name) and returns LLMProviderProtocol
    """
    global _llm_provider_factory
    _llm_provider_factory = factory

# Import tool catalog for typed tool IDs (Decision 1:A)
from jeeves_infra.tools.catalog import ToolId


# =============================================================================
# Agent Context - For Tool Access Enforcement (Decision 2:B)
# =============================================================================

@dataclass(frozen=True)
class AgentContext:
    """Context for tool execution - identifies calling agent.

    Decision 2:B: Used by ToolExecutor to enforce AGENT_TOOL_ACCESS at runtime.
    Only CodeTraverserAgent has permission to execute tools.

    Attributes:
        agent_name: Name of the agent requesting execution
        request_id: Optional request/envelope ID for tracing
        session_id: Optional session ID for context

    Usage:
        context = AgentContext(agent_name="CodeTraverserAgent", request_id="req-123")
        result = await executor.execute_with_context(ToolId.LOCATE, params, context)
    """
    agent_name: str
    request_id: Optional[str] = None
    session_id: Optional[str] = None


# Resilient ops mapping - tools with automatic fallback strategies
# Maps base tool name to resilient tool name
RESILIENT_OPS_MAP = {
    "read_file": "read_code",
    "find_symbol": "locate",
    "find_similar_files": "find_related",
}

# Parameter transformations when mapping base tools to resilient tools
# Maps: base_tool -> {base_param: resilient_param}
# Required because resilient tools may use different parameter names
RESILIENT_PARAM_MAP = {
    "find_similar_files": {"file_path": "reference"},
    # read_file -> read_code: parameters match (path, start_line, end_line)
    # find_symbol -> locate: parameters match (symbol -> query)
}


class ToolExecutor:
    """Concrete implementation of ToolExecutorProtocol.

    Wraps the tool registry and resilient operations to provide
    a protocol-compliant interface for tool execution.

    This implementation:
    - Delegates to tool_registry for direct tool execution
    - Uses resilient_ops for tools with fallback strategies
    - Tracks execution timing and attempt history
    - Validates parameters against registered schemas (Phase 1.1)
    - Filters None values so function defaults apply (Phase 1.2)

    Decision 2:B Implementation:
    - execute_with_context(): Enforces AGENT_TOOL_ACCESS at runtime
    - Only CodeTraverserAgent can execute tools
    - Other agents get rejection with clear error message

    Constitutional compliance (P3 - Bounded Efficiency):
    - Returns clear, bounded error messages on validation failure
    - Prevents cascade failures from invalid parameters
    """

    def __init__(
        self,
        registry: ToolRegistryProtocol,
        logger: Optional[LoggerProtocol] = None,
        access_checker: Optional[AgentToolAccessProtocol] = None,
    ):
        """Initialize with a tool registry.

        Args:
            registry: Tool registry implementing ToolRegistryProtocol (required)
            logger: LoggerProtocol for structured logging
            access_checker: Optional AgentToolAccessProtocol for access control (ADR-001 DI)
        """
        self._registry = registry
        self._logger = logger or create_logger("tool_executor")
        # Access checker is now injected via constructor (ADR-001)
        self._access_checker = access_checker

    def _get_access_checker(self) -> Optional[AgentToolAccessProtocol]:
        """Get access checker if configured.

        Returns:
            AgentToolAccessProtocol if configured, None otherwise.
        """
        return self._access_checker

    def _validate_params(self, tool_def: Any, params: Dict[str, Any]) -> List[str]:
        """Validate parameters against registered schemas.

        Phase 1.1: Uses existing ToolParameterSchema infrastructure from registry.

        Args:
            tool_def: Tool definition with parameter_schemas
            params: Parameters to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Skip validation if no schemas registered (backward compat)
        if not hasattr(tool_def, 'parameter_schemas') or not tool_def.parameter_schemas:
            return errors

        for param_name, schema in tool_def.parameter_schemas.items():
            value = params.get(param_name)

            # Validate using existing schema infrastructure
            is_valid, error_msg = schema.validate_value(value)
            if not is_valid:
                errors.append(error_msg)

        return errors

    async def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool by name with parameters.

        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters

        Returns:
            Dict with status, data/error, execution_time_ms, and error_type on failure

        Constitutional compliance (P3 - Bounded Efficiency):
        - Validates parameters against registered schemas before execution
        - Filters None values so function defaults apply correctly
        - Returns clear, bounded error messages on validation failure
        """
        start_time = time.perf_counter()

        try:
            if not self._registry.has_tool(tool_name):
                return {
                    "status": "error",
                    "error": f"Unknown tool: {tool_name}",
                    "error_type": "tool_not_found",
                    "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
                }

            tool_def = self._registry.get_tool(tool_name)

            # Phase 1.2: Filter None values so function defaults apply
            # This prevents None from overriding default parameter values
            # e.g., list_files(path=None) would fail, but omitting path uses default "."
            filtered_params = {k: v for k, v in params.items() if v is not None}

            # Phase 1.1: Validate parameters against registered schemas
            validation_errors = self._validate_params(tool_def, filtered_params)
            if validation_errors:
                self._logger.warning(
                    "tool_parameter_validation_failed",
                    tool=tool_name,
                    errors=validation_errors,
                    original_params=list(params.keys()),
                    filtered_params=list(filtered_params.keys()),
                )
                return {
                    "status": "error",
                    "error": f"Parameter validation failed: {'; '.join(validation_errors)}",
                    "error_type": "validation_error",
                    "validation_errors": validation_errors,
                    "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
                }

            result = await tool_def.function(**filtered_params)
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Normalize result format
            # Per Constitution P1 (Accuracy First): Preserve actual tool status
            # - "error": Actual failure, propagate as error
            # - "not_found"/"partial": Valid outcomes, not errors (P3: partial results acceptable)
            # - "success": Actual success
            tool_status = result.get("status", "success")

            if tool_status == "error":
                return {
                    "status": "error",
                    "error": result.get("error", "Unknown error"),
                    "error_type": "tool_error",
                    "execution_time_ms": execution_time_ms,
                }

            # Preserve not_found/partial status instead of converting to success
            # This enables proper handling by traverser and critic
            if tool_status in ("not_found", "partial"):
                return {
                    "status": tool_status,
                    "data": result,
                    "message": result.get("message", f"Tool returned {tool_status}"),
                    "execution_time_ms": execution_time_ms,
                }

            return {
                "status": "success",
                "data": result,
                "execution_time_ms": execution_time_ms,
            }

        except TypeError as e:
            # Catch parameter binding errors (missing required args, unexpected kwargs)
            error_msg = str(e)
            self._logger.warning(
                "tool_parameter_binding_error",
                tool=tool_name,
                error=error_msg,
                params=list(params.keys()),
            )
            return {
                "status": "error",
                "error": f"Parameter error: {error_msg}",
                "error_type": "parameter_error",
                "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
            }
        except Exception as e:
            error_type = type(e).__name__
            self._logger.error(
                "tool_execution_error",
                tool=tool_name,
                error_type=error_type,
                error=str(e),
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": error_type,
                "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
            }

    async def execute_with_context(
        self,
        tool_id: ToolId,
        params: Dict[str, Any],
        context: AgentContext,
    ) -> Dict[str, Any]:
        """Execute tool with access enforcement (Decision 2:B).

        This method enforces AGENT_TOOL_ACCESS at runtime. Only authorized
        agents (CodeTraverserAgent) can execute tools. Other agents receive
        a rejection response.

        Args:
            tool_id: Typed tool identifier (ToolId enum)
            params: Tool parameters
            context: AgentContext with agent identity

        Returns:
            Dict with status, data/error, execution_time_ms
            - status="rejected" if agent not authorized
            - status="error" if tool not found or execution fails
            - status="success" if tool executes successfully
        """
        start_time = time.perf_counter()

        # Decision 2:B: Enforce access control via AgentToolAccessProtocol (ADR-001)
        access_checker = self._get_access_checker()

        if access_checker is not None:
            tool_name = tool_id.value
            if not access_checker.can_access(context.agent_name, tool_name):
                rejection_msg = (
                    f"Agent '{context.agent_name}' is not authorized to use tool '{tool_name}'. "
                    f"Allowed tools: {access_checker.get_allowed_tools(context.agent_name)}"
                )
                self._logger.warning(
                    "tool_access_rejected",
                    agent=context.agent_name,
                    tool=tool_name,
                    request_id=context.request_id,
                )
                return {
                    "status": "rejected",
                    "error": rejection_msg,
                    "error_type": "access_denied",
                    "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
                }

        # Delegate to standard execute using tool name string
        self._logger.debug(
            "tool_access_granted",
            agent=context.agent_name,
            tool=tool_id.value,
            request_id=context.request_id,
        )
        return await self.execute(tool_id.value, params)

    async def execute_resilient_with_context(
        self,
        tool_id: ToolId,
        params: Dict[str, Any],
        context: AgentContext,
    ) -> Dict[str, Any]:
        """Execute resilient tool with access enforcement (Decision 2:B).

        Combines resilient execution with access control.

        Args:
            tool_id: Typed tool identifier (ToolId enum)
            params: Tool parameters
            context: AgentContext with agent identity

        Returns:
            Dict with status, data/error, execution_time_ms
        """
        start_time = time.perf_counter()

        # Decision 2:B: Enforce access control via AgentToolAccessProtocol (ADR-001)
        access_checker = self._get_access_checker()

        if access_checker is not None:
            tool_name = tool_id.value
            if not access_checker.can_access(context.agent_name, tool_name):
                rejection_msg = (
                    f"Agent '{context.agent_name}' is not authorized to use tool '{tool_name}'. "
                    f"Allowed tools: {access_checker.get_allowed_tools(context.agent_name)}"
                )
                self._logger.warning(
                    "tool_access_rejected",
                    agent=context.agent_name,
                    tool=tool_name,
                    request_id=context.request_id,
                )
                return {
                    "status": "rejected",
                    "error": rejection_msg,
                    "error_type": "access_denied",
                    "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
                }

        # Delegate to standard resilient execute
        return await self.execute_resilient(tool_id.value, params)

    async def execute_resilient(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool with resilient fallback strategies.

        For tools with resilient equivalents (read_file -> read_code),
        this delegates to the resilient tool registered in the registry.

        NOTE: Resilient tool implementations are registered by the capability layer.
        This infrastructure layer only uses them via the protocol interface.

        IMPORTANT: This method handles parameter name transformations when
        base tools and resilient tools use different parameter names.
        See RESILIENT_PARAM_MAP for the mapping.

        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters

        Returns:
            Dict with status, data/error, execution_time_ms, attempt_history
        """
        resilient_tool = self.get_resilient_mapping(tool_name)

        if not resilient_tool:
            # No resilient equivalent - use direct execution
            return await self.execute(tool_name, params)

        # Check if resilient tool exists in registry
        if not self._registry.has_tool(resilient_tool):
            # Fallback to original tool if resilient version not registered
            return await self.execute(tool_name, params)

        # Transform parameters if mapping exists
        # e.g., find_similar_files.file_path -> find_related.reference
        transformed_params = self._transform_resilient_params(tool_name, params)

        # Delegate to the resilient tool via registry protocol
        return await self.execute(resilient_tool, transformed_params)

    def _transform_resilient_params(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Transform parameters for resilient tool execution.

        When base tools and resilient tools use different parameter names,
        this maps the parameters correctly.

        Example:
            find_similar_files(file_path="foo.py") -> find_related(reference="foo.py")

        Args:
            tool_name: Original tool name (e.g., "find_similar_files")
            params: Original parameters

        Returns:
            Transformed parameters for the resilient tool
        """
        param_map = RESILIENT_PARAM_MAP.get(tool_name)

        if not param_map:
            # No parameter transformation needed
            return params

        # Transform parameter names
        transformed = {}
        for key, value in params.items():
            new_key = param_map.get(key, key)  # Use mapped name or keep original
            transformed[new_key] = value

        self._logger.debug(
            "resilient_params_transformed",
            tool=tool_name,
            original_keys=list(params.keys()),
            transformed_keys=list(transformed.keys()),
        )

        return transformed

    def has_tool(self, name: str) -> bool:
        """Check if a tool is available.

        Args:
            name: Tool name

        Returns:
            True if tool exists
        """
        return self._registry.has_tool(name)

    def get_resilient_mapping(self, tool_name: str) -> Optional[str]:
        """Get the resilient operation equivalent for a tool.

        Args:
            tool_name: Original tool name (e.g., "read_file")

        Returns:
            Resilient tool name (e.g., "read_code") or None
        """
        return RESILIENT_OPS_MAP.get(tool_name)


def create_tool_executor(
    registry: ToolRegistryProtocol,
) -> ToolExecutorProtocol:
    """Create a ToolExecutor implementing ToolExecutorProtocol.

    Args:
        registry: Tool registry implementing ToolRegistryProtocol (required)

    Returns:
        ToolExecutor implementing ToolExecutorProtocol
    """
    return ToolExecutor(registry)


def create_llm_provider_factory(
    settings: Optional[Settings] = None,
) -> Callable[[str], LLMProviderProtocol]:
    """Create an LLM provider factory function.

    Returns a factory that creates LLM providers for each agent role.
    The factory is injected into capability flow services.

    NOTE: Requires LLM provider factory to be registered at startup via
    set_llm_provider_factory(). This is typically done by the capability
    bootstrap code which imports from jeeves-infra.

    Args:
        settings: Application settings. If None, uses get_settings().

    Returns:
        Factory function: (agent_role: str) -> LLMProviderProtocol

    Raises:
        RuntimeError: If LLM provider factory not registered
    """
    if _llm_provider_factory is None:
        raise RuntimeError(
            "LLM provider factory not registered. Call set_llm_provider_factory() "
            "at application startup. This is typically done in capability bootstrap."
        )

    if settings is None:
        settings = get_settings()

    def factory(agent_role: str) -> LLMProviderProtocol:
        """Create an LLM provider for the given agent role."""
        return _llm_provider_factory(settings, agent_role)

    return factory


# Re-export commonly used concrete implementations for convenience
# These should be used in application bootstrapping, not in core code
async def get_database_client(settings: Optional[Settings] = None) -> DatabaseClientProtocol:
    """Get a DatabaseClient instance.

    Args:
        settings: Application settings. If None, uses get_settings().

    Returns:
        DatabaseClientProtocol implementing PersistenceProtocol
    """
    from jeeves_infra.database.factory import create_database_client
    if settings is None:
        settings = get_settings()
    return await create_database_client(settings)
