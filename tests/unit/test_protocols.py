"""Unit tests for protocol types and capability registration.

Tests the capability registration system in jeeves_infra.protocols.capability.
"""

import sys
from pathlib import Path

# Add jeeves-infra root to path for imports
jeeves_infra_root = Path(__file__).parent.parent.parent
if str(jeeves_infra_root) not in sys.path:
    sys.path.insert(0, str(jeeves_infra_root))

import pytest
from dataclasses import FrozenInstanceError

from jeeves_infra.protocols.capability import (
    ToolCatalogEntry,
    ToolDefinition,
    CapabilityToolCatalog,
    CapabilityToolsConfig,
    CapabilityResourceRegistry,
    CapabilityOrchestratorConfig,
    CapabilityPromptConfig,
    CapabilityContractsConfig,
    DomainAgentConfig,
    DomainServiceConfig,
    DomainModeConfig,
    get_capability_resource_registry,
    reset_capability_resource_registry,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_registry():
    """Reset global registry before and after each test."""
    reset_capability_resource_registry()
    yield
    reset_capability_resource_registry()


# =============================================================================
# Tests for ToolCatalogEntry
# =============================================================================

class TestToolCatalogEntry:
    """Tests for ToolCatalogEntry frozen dataclass."""

    def test_frozen_dataclass(self):
        """Test that ToolCatalogEntry is frozen (immutable)."""
        entry = ToolCatalogEntry(
            id="test_tool",
            description="A test tool",
            parameters={"name": "string"},
            category="standalone",
        )

        # Attempting to modify should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            entry.id = "new_id"

    def test_all_fields(self):
        """Test all fields are set correctly."""
        entry = ToolCatalogEntry(
            id="add_task",
            description="Add a new task",
            parameters={"title": "string", "priority": "integer?"},
            category="standalone",
            risk_level="write",
        )

        assert entry.id == "add_task"
        assert entry.description == "Add a new task"
        assert entry.parameters == {"title": "string", "priority": "integer?"}
        assert entry.category == "standalone"
        assert entry.risk_level == "write"

    def test_default_risk_level(self):
        """Test default risk_level is 'low'."""
        entry = ToolCatalogEntry(
            id="read_file",
            description="Read a file",
            parameters={},
            category="read",
        )

        assert entry.risk_level == "low"


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_fields(self):
        """Test all fields."""
        def sample_func():
            pass

        defn = ToolDefinition(
            name="my_tool",
            function=sample_func,
            parameters={"arg1": "string"},
            description="A sample tool",
        )

        assert defn.name == "my_tool"
        assert defn.function is sample_func
        assert defn.parameters == {"arg1": "string"}
        assert defn.description == "A sample tool"


# =============================================================================
# Tests for CapabilityToolCatalog
# =============================================================================

class TestCapabilityToolCatalog:
    """Tests for CapabilityToolCatalog."""

    def test_init(self):
        """Test catalog initialization."""
        catalog = CapabilityToolCatalog("assistant")
        assert catalog.capability_id == "assistant"
        assert len(catalog) == 0

    def test_register_tool(self):
        """Test registering a tool."""
        catalog = CapabilityToolCatalog("assistant")

        async def add_task(title: str):
            return {"id": "1", "title": title}

        catalog.register(
            tool_id="add_task",
            func=add_task,
            description="Create a new task",
            parameters={"title": "string"},
            category="standalone",
            risk_level="write",
        )

        assert len(catalog) == 1
        assert "add_task" in catalog

    def test_get_tool(self):
        """Test getting a tool definition."""
        catalog = CapabilityToolCatalog("assistant")

        async def sample_func():
            pass

        catalog.register(
            tool_id="sample",
            func=sample_func,
            description="A sample tool",
            parameters={"arg": "string"},
            category="standalone",
        )

        tool = catalog.get_tool("sample")

        assert tool is not None
        assert tool.name == "sample"
        assert tool.function is sample_func
        assert tool.description == "A sample tool"

    def test_get_tool_not_found(self):
        """Test getting non-existent tool returns None."""
        catalog = CapabilityToolCatalog("assistant")
        tool = catalog.get_tool("nonexistent")
        assert tool is None

    def test_get_function(self):
        """Test getting tool function directly."""
        catalog = CapabilityToolCatalog("assistant")

        async def my_func():
            return "result"

        catalog.register(
            tool_id="my_tool",
            func=my_func,
            description="My tool",
            parameters={},
            category="standalone",
        )

        func = catalog.get_function("my_tool")
        assert func is my_func

    def test_has_tool(self):
        """Test has_tool method."""
        catalog = CapabilityToolCatalog("assistant")

        catalog.register(
            tool_id="tool1",
            func=lambda: None,
            description="Tool 1",
            parameters={},
            category="standalone",
        )

        assert catalog.has_tool("tool1") is True
        assert catalog.has_tool("tool2") is False

    def test_list_tools(self):
        """Test listing all tool IDs."""
        catalog = CapabilityToolCatalog("assistant")

        for i in range(3):
            catalog.register(
                tool_id=f"tool_{i}",
                func=lambda: None,
                description=f"Tool {i}",
                parameters={},
                category="standalone",
            )

        tools = catalog.list_tools()
        assert len(tools) == 3
        assert "tool_0" in tools
        assert "tool_1" in tools
        assert "tool_2" in tools

    def test_get_entries(self):
        """Test getting all tool entries."""
        catalog = CapabilityToolCatalog("assistant")

        catalog.register(
            tool_id="tool_a",
            func=lambda: None,
            description="Tool A",
            parameters={"x": "int"},
            category="standalone",
        )

        entries = catalog.get_entries()
        assert len(entries) == 1
        assert entries[0].id == "tool_a"
        assert entries[0].description == "Tool A"

    def test_generate_prompt_section(self):
        """Test generating prompt section for LLM."""
        catalog = CapabilityToolCatalog("assistant")

        catalog.register(
            tool_id="add",
            func=lambda: None,
            description="Add two numbers",
            parameters={"a": "int", "b": "int"},
            category="math",
        )

        catalog.register(
            tool_id="subtract",
            func=lambda: None,
            description="Subtract numbers",
            parameters={"a": "int", "b": "int?"},
            category="math",
        )

        prompt = catalog.generate_prompt_section()

        assert "Tools for assistant:" in prompt
        assert "add(a, b): Add two numbers" in prompt
        assert "subtract(a, b?): Subtract numbers" in prompt

    def test_len(self):
        """Test __len__ method."""
        catalog = CapabilityToolCatalog("assistant")
        assert len(catalog) == 0

        catalog.register(
            tool_id="tool1",
            func=lambda: None,
            description="Tool",
            parameters={},
            category="standalone",
        )
        assert len(catalog) == 1

    def test_contains(self):
        """Test __contains__ method."""
        catalog = CapabilityToolCatalog("assistant")

        catalog.register(
            tool_id="exists",
            func=lambda: None,
            description="Exists",
            parameters={},
            category="standalone",
        )

        assert "exists" in catalog
        assert "not_exists" not in catalog


# =============================================================================
# Tests for CapabilityToolsConfig
# =============================================================================

class TestCapabilityToolsConfig:
    """Tests for CapabilityToolsConfig."""

    def test_get_catalog_direct(self):
        """Test get_catalog with direct catalog instance."""
        catalog = CapabilityToolCatalog("test")
        config = CapabilityToolsConfig(
            tool_ids=["tool1"],
            catalog=catalog,
        )

        result = config.get_catalog()
        assert result is catalog

    def test_get_catalog_lazy_init(self):
        """Test get_catalog with lazy initialization."""
        def initializer(prefix: str = "default"):
            catalog = CapabilityToolCatalog("lazy")
            catalog.register(
                tool_id=f"{prefix}_tool",
                func=lambda: None,
                description="Lazy tool",
                parameters={},
                category="standalone",
            )
            return catalog

        config = CapabilityToolsConfig(
            tool_ids=["lazy_tool"],
            initializer=initializer,
        )

        # First call creates catalog
        result = config.get_catalog(prefix="custom")
        assert result is not None
        assert "custom_tool" in result

        # Second call returns cached catalog
        result2 = config.get_catalog(prefix="ignored")
        assert result2 is result

    def test_get_catalog_no_catalog_or_initializer(self):
        """Test get_catalog returns None when neither is set."""
        config = CapabilityToolsConfig(tool_ids=[])
        assert config.get_catalog() is None


# =============================================================================
# Tests for CapabilityResourceRegistry
# =============================================================================

class TestCapabilityResourceRegistry:
    """Tests for CapabilityResourceRegistry."""

    def test_register_schema(self):
        """Test schema registration."""
        registry = CapabilityResourceRegistry()
        registry.register_schema("code_analysis", "schemas/analysis.sql")

        schemas = registry.get_schemas("code_analysis")
        assert schemas == ["schemas/analysis.sql"]

    def test_get_schemas_all(self):
        """Test getting all schemas."""
        registry = CapabilityResourceRegistry()
        registry.register_schema("cap1", "schema1.sql")
        registry.register_schema("cap2", "schema2.sql")

        all_schemas = registry.get_schemas()
        assert len(all_schemas) == 2
        assert "schema1.sql" in all_schemas
        assert "schema2.sql" in all_schemas

    def test_register_mode(self):
        """Test mode registration."""
        registry = CapabilityResourceRegistry()
        mode = DomainModeConfig(
            mode_id="analysis",
            response_fields=["result", "confidence"],
            requires_repo_path=True,
        )
        registry.register_mode("code_analysis", mode)

        result = registry.get_mode_config("analysis")
        assert result is not None
        assert result.mode_id == "analysis"
        assert result.requires_repo_path is True

    def test_is_mode_registered(self):
        """Test is_mode_registered."""
        registry = CapabilityResourceRegistry()
        mode = DomainModeConfig(mode_id="test_mode")
        registry.register_mode("cap", mode)

        assert registry.is_mode_registered("test_mode") is True
        assert registry.is_mode_registered("other_mode") is False

    def test_list_modes(self):
        """Test listing all modes."""
        registry = CapabilityResourceRegistry()
        registry.register_mode("cap1", DomainModeConfig(mode_id="mode1"))
        registry.register_mode("cap2", DomainModeConfig(mode_id="mode2"))

        modes = registry.list_modes()
        assert len(modes) == 2
        assert "mode1" in modes
        assert "mode2" in modes

    def test_register_service(self):
        """Test service registration."""
        registry = CapabilityResourceRegistry()
        service = DomainServiceConfig(
            service_id="assistant",
            service_type="flow",
            max_concurrent=5,
            is_default=True,
        )
        registry.register_service("assistant_cap", service)

        services = registry.get_services("assistant_cap")
        assert len(services) == 1
        assert services[0].service_id == "assistant"

    def test_get_default_service(self):
        """Test getting default service."""
        registry = CapabilityResourceRegistry()

        # No services - returns None
        assert registry.get_default_service() is None

        # Add non-default service
        registry.register_service("cap1", DomainServiceConfig(
            service_id="service1",
            is_default=False,
        ))

        # Should return first registered
        assert registry.get_default_service() == "service1"

        # Add default service
        registry.register_service("cap2", DomainServiceConfig(
            service_id="service2",
            is_default=True,
        ))

        # Should return the one marked as default
        assert registry.get_default_service() == "service2"

    def test_list_capabilities(self):
        """Test listing all capability IDs."""
        registry = CapabilityResourceRegistry()
        registry.register_schema("cap1", "schema.sql")
        registry.register_mode("cap2", DomainModeConfig(mode_id="mode"))
        registry.register_service("cap3", DomainServiceConfig(service_id="svc"))

        caps = registry.list_capabilities()
        assert len(caps) == 3
        assert "cap1" in caps
        assert "cap2" in caps
        assert "cap3" in caps

    def test_register_orchestrator(self):
        """Test orchestrator registration."""
        registry = CapabilityResourceRegistry()

        def factory():
            return "orchestrator"

        config = CapabilityOrchestratorConfig(factory=factory)
        registry.register_orchestrator("cap", config)

        result = registry.get_orchestrator("cap")
        assert result is not None
        assert result.factory() == "orchestrator"

    def test_register_tools(self):
        """Test tools registration."""
        registry = CapabilityResourceRegistry()
        catalog = CapabilityToolCatalog("test")
        config = CapabilityToolsConfig(tool_ids=["tool1"], catalog=catalog)

        registry.register_tools("cap", config)

        result = registry.get_tools("cap")
        assert result is not None
        assert result.catalog is catalog

    def test_register_prompts(self):
        """Test prompts registration."""
        registry = CapabilityResourceRegistry()
        prompts = [
            CapabilityPromptConfig(
                prompt_id="system",
                version="1.0",
                description="System prompt",
                prompt_factory=lambda: "You are an assistant",
            )
        ]
        registry.register_prompts("cap", prompts)

        result = registry.get_prompts("cap")
        assert len(result) == 1
        assert result[0].prompt_id == "system"

    def test_register_agents(self):
        """Test agents registration."""
        registry = CapabilityResourceRegistry()
        agents = [
            DomainAgentConfig(
                name="planner",
                description="Plans tasks",
                layer="planning",
                tools=["analyze", "plan"],
            )
        ]
        registry.register_agents("cap", agents)

        result = registry.get_agents("cap")
        assert len(result) == 1
        assert result[0].name == "planner"
        assert result[0].layer == "planning"

    def test_register_contracts(self):
        """Test contracts registration."""
        registry = CapabilityResourceRegistry()
        config = CapabilityContractsConfig(
            schemas={"tool1": dict},
            validators={"tool1": lambda x: x},
        )
        registry.register_contracts("cap", config)

        result = registry.get_contracts("cap")
        assert result is not None
        assert "tool1" in result.schemas

    def test_clear(self):
        """Test clearing all registrations."""
        registry = CapabilityResourceRegistry()
        registry.register_schema("cap", "schema.sql")
        registry.register_mode("cap", DomainModeConfig(mode_id="mode"))
        registry.register_service("cap", DomainServiceConfig(service_id="svc"))

        registry.clear()

        assert len(registry.list_capabilities()) == 0
        assert len(registry.get_schemas()) == 0
        assert len(registry.list_modes()) == 0
        assert len(registry.get_services()) == 0


# =============================================================================
# Tests for Global Registry
# =============================================================================

class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_capability_resource_registry_singleton(self):
        """Test get_capability_resource_registry returns singleton."""
        reg1 = get_capability_resource_registry()
        reg2 = get_capability_resource_registry()

        assert reg1 is reg2

    def test_reset_capability_resource_registry(self):
        """Test reset creates new instance."""
        reg1 = get_capability_resource_registry()
        reg1.register_schema("cap", "schema.sql")

        reset_capability_resource_registry()

        reg2 = get_capability_resource_registry()
        assert reg2 is not reg1
        assert len(reg2.get_schemas()) == 0
