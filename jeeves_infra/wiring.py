"""
Infrastructure Wiring - Tool Execution

This module provides infrastructure primitives for tool execution.

**Key exports:**
- ToolExecutor: Protocol-compliant tool executor with access control
- AgentContext: Context for tool execution with agent identity
- create_tool_executor(): Factory for creating ToolExecutor

Note: LLM provider factory is accessed via AppContext.llm_provider_factory
(eagerly provisioned by bootstrap.create_app_context()).

**Usage:**
    ```python
    from jeeves_infra.wiring import ToolExecutor, AgentContext

    # Create executor with registry
    executor = ToolExecutor(registry=tool_registry, logger=logger)

    # Execute with access control
    context = AgentContext(agent_name="MyAgent", request_id="req-123")
    result = await executor.execute_with_context("locate", params, context)
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


# =============================================================================
# Agent Context - For Tool Access Enforcement
# =============================================================================

@dataclass(frozen=True)
class AgentContext:
    """Context for tool execution - identifies calling agent.

    Used by ToolExecutor to enforce tool access at runtime.

    Attributes:
        agent_name: Name of the agent requesting execution
        request_id: Optional request/envelope ID for tracing
        session_id: Optional session ID for context
    """
    agent_name: str
    request_id: Optional[str] = None
    session_id: Optional[str] = None


class ToolExecutor:
    """Concrete implementation of ToolExecutorProtocol.

    Wraps the tool registry to provide a protocol-compliant interface
    for tool execution with access control.

    This implementation:
    - Delegates to tool_registry for tool execution
    - Tracks execution timing
    - Validates parameters against registered schemas
    - Filters None values so function defaults apply
    - Enforces agent-level access control via execute_with_context()
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
            access_checker: Optional AgentToolAccessProtocol for access control
        """
        self._registry = registry
        self._logger = logger or create_logger("tool_executor")
        self._access_checker = access_checker

    def _get_access_checker(self) -> Optional[AgentToolAccessProtocol]:
        """Get access checker if configured."""
        return self._access_checker

    def _validate_params(self, tool_def: Any, params: Dict[str, Any]) -> List[str]:
        """Validate parameters against registered schemas.

        Args:
            tool_def: Tool definition with parameter_schemas
            params: Parameters to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not hasattr(tool_def, 'parameter_schemas') or not tool_def.parameter_schemas:
            return errors

        for param_name, schema in tool_def.parameter_schemas.items():
            value = params.get(param_name)
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

            # Filter None values so function defaults apply
            filtered_params = {k: v for k, v in params.items() if v is not None}

            # Validate parameters against registered schemas
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

            # Preserve actual tool status
            tool_status = result.get("status", "success")

            if tool_status == "error":
                return {
                    "status": "error",
                    "error": result.get("error", "Unknown error"),
                    "error_type": "tool_error",
                    "execution_time_ms": execution_time_ms,
                }

            # Preserve not_found/partial status instead of converting to success
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
        tool_name: str,
        params: Dict[str, Any],
        context: AgentContext,
    ) -> Dict[str, Any]:
        """Execute tool with access enforcement.

        This method enforces tool access at runtime. Only authorized
        agents can execute tools. Other agents receive a rejection response.

        Args:
            tool_name: String tool identifier
            params: Tool parameters
            context: AgentContext with agent identity

        Returns:
            Dict with status, data/error, execution_time_ms
            - status="rejected" if agent not authorized
            - status="error" if tool not found or execution fails
            - status="success" if tool executes successfully
        """
        start_time = time.perf_counter()

        access_checker = self._get_access_checker()

        if access_checker is not None:
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

        self._logger.debug(
            "tool_access_granted",
            agent=context.agent_name,
            tool=tool_name,
            request_id=context.request_id,
        )
        return await self.execute(tool_name, params)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is available.

        Args:
            name: Tool name

        Returns:
            True if tool exists
        """
        return self._registry.has_tool(name)


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


