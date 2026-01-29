"""Tests for ToolExecutor and ToolExecutionCore.

Tests verify:
1. Defaults are respected when None values are filtered
2. Invalid params are caught before tool execution
3. Clear, bounded errors are returned on validation failure

Constitutional compliance: P3 (Bounded Efficiency)

Refactored to test REAL implementations:
- ToolExecutionCore: Pure logic tests (no registry)
- ToolExecutor: Full facade tests (with mock registry)
"""

import pytest
from typing import Any, Dict, Optional

# Test the REAL implementations
from jeeves_infra.tools.executor import ToolExecutionCore
from jeeves_infra.wiring import ToolExecutor, RESILIENT_PARAM_MAP, RESILIENT_OPS_MAP


# =============================================================================
# Minimal Mocks (only for ToolExecutor tests that need a registry)
# =============================================================================


class MockToolParameterSchema:
    """Mock schema for testing validation."""

    def __init__(
        self,
        name: str,
        required: bool = True,
        valid: bool = True,
        error_msg: str = None,
    ):
        self.name = name
        self.required = required
        self._valid = valid
        self._error_msg = error_msg or f"Invalid value for '{name}'"

    def validate_value(self, value: Any) -> tuple:
        """Return (is_valid, error_message)."""
        if value is None and self.required:
            return False, f"Required parameter '{self.name}' is missing"
        if not self._valid:
            return False, self._error_msg
        return True, None


class MockToolDefinition:
    """Mock tool definition for testing."""

    def __init__(
        self,
        name: str,
        function: callable,
        parameter_schemas: Dict[str, MockToolParameterSchema] = None,
    ):
        self.name = name
        self.function = function
        self.parameter_schemas = parameter_schemas or {}


class MockToolRegistry:
    """Mock tool registry for testing ToolExecutor."""

    def __init__(self):
        self._tools: Dict[str, MockToolDefinition] = {}

    def register(self, tool_def: MockToolDefinition):
        """Register a tool."""
        self._tools[tool_def.name] = tool_def

    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return name in self._tools

    def get_tool(self, name: str) -> MockToolDefinition:
        """Get tool by name."""
        return self._tools[name]


# =============================================================================
# Tests for ToolExecutionCore (Pure Logic - No Registry)
# =============================================================================


class TestToolExecutionCore:
    """Test the pure execution core logic."""

    def test_filter_none_params(self):
        """Verify None values are filtered."""
        core = ToolExecutionCore()

        params = {"path": None, "max_results": 50, "pattern": "*.py"}
        filtered = core.filter_none_params(params)

        assert "path" not in filtered
        assert filtered["max_results"] == 50
        assert filtered["pattern"] == "*.py"

    def test_filter_preserves_empty_string(self):
        """Verify empty strings are NOT filtered (only None)."""
        core = ToolExecutionCore()

        params = {"path": "", "name": None}
        filtered = core.filter_none_params(params)

        assert filtered["path"] == ""
        assert "name" not in filtered

    def test_filter_preserves_zero(self):
        """Verify zero values are NOT filtered."""
        core = ToolExecutionCore()

        params = {"count": 0, "offset": None}
        filtered = core.filter_none_params(params)

        assert filtered["count"] == 0
        assert "offset" not in filtered

    def test_filter_preserves_false(self):
        """Verify False values are NOT filtered."""
        core = ToolExecutionCore()

        params = {"recursive": False, "missing": None}
        filtered = core.filter_none_params(params)

        assert filtered["recursive"] is False
        assert "missing" not in filtered

    def test_validate_params_empty_schemas(self):
        """Verify validation passes with no schemas."""
        core = ToolExecutionCore()

        errors = core.validate_params(None, {"any": "param"})
        assert errors == []

        errors = core.validate_params({}, {"any": "param"})
        assert errors == []

    def test_validate_params_required_missing(self):
        """Verify validation fails for missing required param."""
        core = ToolExecutionCore()

        schemas = {
            "query": MockToolParameterSchema(name="query", required=True),
        }
        errors = core.validate_params(schemas, {})

        assert len(errors) == 1
        assert "query" in errors[0]

    def test_validate_params_multiple_errors(self):
        """Verify all validation errors are collected."""
        core = ToolExecutionCore()

        schemas = {
            "a": MockToolParameterSchema(name="a", required=True),
            "b": MockToolParameterSchema(name="b", required=True),
        }
        errors = core.validate_params(schemas, {})

        assert len(errors) == 2

    def test_normalize_result_success(self):
        """Verify success results are normalized."""
        core = ToolExecutionCore()

        result = core.normalize_result(
            {"status": "success", "data": [1, 2, 3]},
            execution_time_ms=42,
        )

        assert result["status"] == "success"
        assert result["data"]["data"] == [1, 2, 3]
        assert result["execution_time_ms"] == 42

    def test_normalize_result_error(self):
        """Verify error results are normalized."""
        core = ToolExecutionCore()

        result = core.normalize_result(
            {"status": "error", "error": "Something broke"},
            execution_time_ms=10,
        )

        assert result["status"] == "error"
        assert result["error"] == "Something broke"
        assert result["error_type"] == "tool_error"

    def test_normalize_result_not_found(self):
        """Verify not_found status is preserved (not converted to success)."""
        core = ToolExecutionCore()

        result = core.normalize_result(
            {"status": "not_found", "message": "File not found"},
            execution_time_ms=5,
        )

        assert result["status"] == "not_found"
        assert "message" in result

    def test_normalize_result_partial(self):
        """Verify partial status is preserved."""
        core = ToolExecutionCore()

        result = core.normalize_result(
            {"status": "partial", "message": "Only found 3 of 10"},
            execution_time_ms=100,
        )

        assert result["status"] == "partial"

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        """Verify successful tool execution via core."""
        core = ToolExecutionCore()

        received_params = {}

        async def mock_tool(path: str = ".", pattern: str = "*") -> Dict[str, Any]:
            received_params["path"] = path
            received_params["pattern"] = pattern
            return {"status": "success", "files": ["a.py", "b.py"]}

        result = await core.execute_tool(mock_tool, {"pattern": "*.py"})

        assert result["status"] == "success"
        assert received_params["path"] == "."  # Default used
        assert received_params["pattern"] == "*.py"  # Explicit value

    @pytest.mark.asyncio
    async def test_execute_tool_none_filtered(self):
        """Verify None values are filtered, defaults apply."""
        core = ToolExecutionCore()

        received_params = {}

        async def mock_tool(path: str = "/default") -> Dict[str, Any]:
            received_params["path"] = path
            return {"status": "success"}

        result = await core.execute_tool(mock_tool, {"path": None})

        assert result["status"] == "success"
        assert received_params["path"] == "/default"

    @pytest.mark.asyncio
    async def test_execute_tool_validation_error(self):
        """Verify validation errors are returned."""
        core = ToolExecutionCore()

        async def mock_tool(query: str) -> Dict[str, Any]:
            return {"status": "success"}

        schemas = {
            "query": MockToolParameterSchema(name="query", required=True),
        }
        result = await core.execute_tool(mock_tool, {}, schemas)

        assert result["status"] == "error"
        assert result["error_type"] == "validation_error"
        assert "validation_errors" in result

    @pytest.mark.asyncio
    async def test_execute_tool_type_error(self):
        """Verify TypeError is caught and returned cleanly."""
        core = ToolExecutionCore()

        async def mock_tool(required_arg: str) -> Dict[str, Any]:
            return {"status": "success"}

        result = await core.execute_tool(mock_tool, {"wrong_arg": "value"})

        assert result["status"] == "error"
        assert result["error_type"] == "parameter_error"

    @pytest.mark.asyncio
    async def test_execute_tool_exception(self):
        """Verify exceptions are caught with type info."""
        core = ToolExecutionCore()

        async def crashing_tool() -> Dict[str, Any]:
            raise ValueError("Unexpected value")

        result = await core.execute_tool(crashing_tool, {})

        assert result["status"] == "error"
        assert result["error_type"] == "ValueError"
        assert "Unexpected value" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_tool_timing(self):
        """Verify execution time is always present."""
        core = ToolExecutionCore()

        async def mock_tool() -> Dict[str, Any]:
            return {"status": "success"}

        result = await core.execute_tool(mock_tool, {})

        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)
        assert result["execution_time_ms"] >= 0


# =============================================================================
# Tests for ToolExecutor (Full Facade with Registry)
# =============================================================================


class TestToolExecutor:
    """Test the ToolExecutor facade with mock registry."""

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Verify clear error for unknown tool."""
        registry = MockToolRegistry()
        executor = ToolExecutor(registry)

        result = await executor.execute("nonexistent_tool", {})

        assert result["status"] == "error"
        assert result["error_type"] == "tool_not_found"
        assert "nonexistent_tool" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_with_none_filtering(self):
        """Verify None values filtered, defaults used."""
        received_params = {}

        async def mock_tool(path: str = ".", max_results: int = 100) -> Dict[str, Any]:
            received_params["path"] = path
            received_params["max_results"] = max_results
            return {"status": "success", "files": []}

        registry = MockToolRegistry()
        tool_def = MockToolDefinition(name="list_files", function=mock_tool)
        registry.register(tool_def)

        executor = ToolExecutor(registry)
        result = await executor.execute("list_files", {"path": None, "max_results": 50})

        assert result["status"] == "success"
        assert received_params["path"] == "."  # Default used
        assert received_params["max_results"] == 50  # Explicit value

    @pytest.mark.asyncio
    async def test_execute_validation_error(self):
        """Verify validation error when required param missing."""

        async def mock_tool(query: str) -> Dict[str, Any]:
            return {"status": "success"}

        registry = MockToolRegistry()
        tool_def = MockToolDefinition(
            name="search",
            function=mock_tool,
            parameter_schemas={
                "query": MockToolParameterSchema(name="query", required=True),
            },
        )
        registry.register(tool_def)

        executor = ToolExecutor(registry)
        result = await executor.execute("search", {})

        assert result["status"] == "error"
        assert result["error_type"] == "validation_error"
        assert "query" in str(result["validation_errors"])

    @pytest.mark.asyncio
    async def test_execute_tool_error_propagated(self):
        """Verify tool errors include error_type."""

        async def failing_tool() -> Dict[str, Any]:
            return {"status": "error", "error": "Something went wrong"}

        registry = MockToolRegistry()
        tool_def = MockToolDefinition(name="failing", function=failing_tool)
        registry.register(tool_def)

        executor = ToolExecutor(registry)
        result = await executor.execute("failing", {})

        assert result["status"] == "error"
        assert result["error_type"] == "tool_error"
        assert result["error"] == "Something went wrong"

    @pytest.mark.asyncio
    async def test_has_tool(self):
        """Verify has_tool delegates to registry."""

        async def mock_tool() -> Dict[str, Any]:
            return {"status": "success"}

        registry = MockToolRegistry()
        tool_def = MockToolDefinition(name="exists", function=mock_tool)
        registry.register(tool_def)

        executor = ToolExecutor(registry)

        assert executor.has_tool("exists") is True
        assert executor.has_tool("not_exists") is False


# =============================================================================
# Tests for Resilient Parameter Transformation
# =============================================================================


class TestResilientParameterTransformation:
    """Test parameter transformation for resilient tool execution."""

    def test_resilient_param_map_exists(self):
        """Verify RESILIENT_PARAM_MAP is defined."""
        assert isinstance(RESILIENT_PARAM_MAP, dict)
        assert "find_similar_files" in RESILIENT_PARAM_MAP
        assert RESILIENT_PARAM_MAP["find_similar_files"] == {"file_path": "reference"}

    def test_resilient_ops_map_exists(self):
        """Verify RESILIENT_OPS_MAP is defined."""
        assert isinstance(RESILIENT_OPS_MAP, dict)
        assert "find_similar_files" in RESILIENT_OPS_MAP
        assert RESILIENT_OPS_MAP["find_similar_files"] == "find_related"

    def test_transform_resilient_params_transforms_keys(self):
        """Verify _transform_resilient_params correctly maps parameter names."""
        registry = MockToolRegistry()
        executor = ToolExecutor(registry)

        params = {"file_path": "agent.py", "limit": 5}
        transformed = executor._transform_resilient_params("find_similar_files", params)

        assert "reference" in transformed
        assert transformed["reference"] == "agent.py"
        assert transformed["limit"] == 5
        assert "file_path" not in transformed

    def test_transform_resilient_params_no_mapping(self):
        """Verify params pass through unchanged when no mapping exists."""
        registry = MockToolRegistry()
        executor = ToolExecutor(registry)

        params = {"path": "test.py", "start_line": 1}
        transformed = executor._transform_resilient_params("read_file", params)

        assert transformed == params

    def test_transform_resilient_params_preserves_unmapped(self):
        """Verify unmapped parameter keys are preserved."""
        registry = MockToolRegistry()
        executor = ToolExecutor(registry)

        params = {"file_path": "agent.py", "limit": 10, "min_similarity": 0.5}
        transformed = executor._transform_resilient_params("find_similar_files", params)

        assert transformed["reference"] == "agent.py"
        assert transformed["limit"] == 10
        assert transformed["min_similarity"] == 0.5

    def test_get_resilient_mapping(self):
        """Verify get_resilient_mapping returns correct mappings."""
        registry = MockToolRegistry()
        executor = ToolExecutor(registry)

        assert executor.get_resilient_mapping("read_file") == "read_code"
        assert executor.get_resilient_mapping("find_symbol") == "locate"
        assert executor.get_resilient_mapping("find_similar_files") == "find_related"
        assert executor.get_resilient_mapping("unknown_tool") is None
