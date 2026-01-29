"""Tool Execution Core - Pure, testable execution logic.

Constitutional Pattern:
- This module contains ONLY pure execution logic with minimal dependencies
- No registry lookup, no LLM, no database - just execution mechanics
- Easily testable without mocking complex infrastructure

The core handles:
- Parameter validation against schemas
- None value filtering (so defaults apply)
- Execution timing
- Error normalization

Usage:
    # In tests (directly test core logic)
    from avionics.tools.executor import ToolExecutionCore
    core = ToolExecutionCore()
    result = await core.execute_tool(tool_def.function, params, tool_def.parameter_schemas)

    # In ToolExecutor (facade over core)
    self._core = ToolExecutionCore(logger)
    result = await self._core.execute_tool(tool_def.function, params, tool_def.parameter_schemas)
"""

import time
from typing import Any, Callable, Dict, List, Optional, Awaitable

from jeeves_infra.protocols import LoggerProtocol


class ToolExecutionCore:
    """Pure execution logic for tools - easily testable.

    This class contains the core mechanics of tool execution:
    - Parameter validation
    - None filtering
    - Execution timing
    - Result normalization

    It does NOT handle:
    - Registry lookups (that's ToolExecutor's job)
    - Access control (that's ToolExecutor's job)
    - Resilient fallbacks (that's ToolExecutor's job)

    Constitutional compliance (P3 - Bounded Efficiency):
    - Returns clear, bounded error messages on validation failure
    - Prevents cascade failures from invalid parameters
    """

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        """Initialize with optional logger.

        Args:
            logger: Optional LoggerProtocol for structured logging.
                    If None, logging is skipped (useful for tests).
        """
        self._logger = logger

    def validate_params(
        self,
        parameter_schemas: Optional[Dict[str, Any]],
        params: Dict[str, Any],
    ) -> List[str]:
        """Validate parameters against schemas.

        Args:
            parameter_schemas: Dict mapping param names to schemas with validate_value()
            params: Parameters to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not parameter_schemas:
            return errors

        for param_name, schema in parameter_schemas.items():
            value = params.get(param_name)
            is_valid, error_msg = schema.validate_value(value)
            if not is_valid:
                errors.append(error_msg)

        return errors

    def filter_none_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out None values so function defaults apply.

        Args:
            params: Original parameters (may contain None values)

        Returns:
            Filtered parameters without None values
        """
        return {k: v for k, v in params.items() if v is not None}

    def normalize_result(
        self,
        result: Dict[str, Any],
        execution_time_ms: int,
    ) -> Dict[str, Any]:
        """Normalize tool result into standard format.

        Args:
            result: Raw result from tool function
            execution_time_ms: Execution time in milliseconds

        Returns:
            Normalized result dict with status, data/error, execution_time_ms
        """
        tool_status = result.get("status", "success")

        if tool_status == "error":
            return {
                "status": "error",
                "error": result.get("error", "Unknown error"),
                "error_type": "tool_error",
                "execution_time_ms": execution_time_ms,
            }

        # Preserve not_found/partial status (Constitution P3: partial results acceptable)
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

    async def execute_tool(
        self,
        tool_function: Callable[..., Awaitable[Dict[str, Any]]],
        params: Dict[str, Any],
        parameter_schemas: Optional[Dict[str, Any]] = None,
        tool_name: str = "unknown",
    ) -> Dict[str, Any]:
        """Execute a tool function with validation, filtering, and timing.

        This is the main entry point for pure tool execution.

        Args:
            tool_function: Async function to execute
            params: Tool parameters
            parameter_schemas: Optional schemas for validation
            tool_name: Tool name for logging

        Returns:
            Normalized result dict with status, data/error, execution_time_ms
        """
        start_time = time.perf_counter()

        try:
            # Step 1: Filter None values
            filtered_params = self.filter_none_params(params)

            # Step 2: Validate parameters
            validation_errors = self.validate_params(parameter_schemas, filtered_params)
            if validation_errors:
                if self._logger:
                    self._logger.warning(
                        "tool_parameter_validation_failed",
                        tool=tool_name,
                        errors=validation_errors,
                    )
                return {
                    "status": "error",
                    "error": f"Parameter validation failed: {'; '.join(validation_errors)}",
                    "error_type": "validation_error",
                    "validation_errors": validation_errors,
                    "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
                }

            # Step 3: Execute
            result = await tool_function(**filtered_params)
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Step 4: Normalize result
            return self.normalize_result(result, execution_time_ms)

        except TypeError as e:
            # Parameter binding errors (missing required args, unexpected kwargs)
            error_msg = str(e)
            if self._logger:
                self._logger.warning(
                    "tool_parameter_binding_error",
                    tool=tool_name,
                    error=error_msg,
                )
            return {
                "status": "error",
                "error": f"Parameter error: {error_msg}",
                "error_type": "parameter_error",
                "execution_time_ms": int((time.perf_counter() - start_time) * 1000),
            }
        except Exception as e:
            error_type = type(e).__name__
            if self._logger:
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


__all__ = ["ToolExecutionCore"]
