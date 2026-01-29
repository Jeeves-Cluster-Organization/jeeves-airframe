"""Test that all protocol exports are importable.

This test ensures that all expected types are properly exported
from jeeves_infra.protocols and can be imported without errors.
"""
import pytest


@pytest.mark.unit
class TestProtocolImports:
    """Test suite for protocol imports."""

    def test_runtime_types_importable(self):
        """Test that runtime types can be imported from protocols."""
        from jeeves_infra.protocols import (
            Agent,
            PipelineRunner,
            create_pipeline_runner,
            create_envelope,
        )
        assert Agent is not None
        assert PipelineRunner is not None
        assert callable(create_pipeline_runner)
        assert callable(create_envelope)

    def test_working_memory_types_importable(self):
        """Test that working memory types can be imported from protocols."""
        from jeeves_infra.protocols import (
            Finding,
            WorkingMemory,
            WorkingMemoryProtocol,
        )
        assert Finding is not None
        assert WorkingMemory is not None
        assert WorkingMemoryProtocol is not None

    def test_utility_types_importable(self):
        """Test that utility types can be imported from protocols."""
        from jeeves_infra.protocols import (
            JSONRepairKit,
            normalize_string_list,
        )
        assert JSONRepairKit is not None
        assert callable(normalize_string_list)

    def test_core_types_importable(self):
        """Test that core protocol types can be imported."""
        from jeeves_infra.protocols import (
            # Enums
            TerminalReason,
            RiskLevel,
            ToolCategory,
            HealthStatus,
            # Dataclasses
            AgentConfig,
            PipelineConfig,
            Envelope,
            RequestContext,
            # Protocols
            LLMProviderProtocol,
            ToolProtocol,
            MemoryServiceProtocol,
        )
        assert TerminalReason is not None
        assert AgentConfig is not None
        assert LLMProviderProtocol is not None

    def test_capability_registration_importable(self):
        """Test that capability registration types can be imported."""
        from jeeves_infra.protocols import (
            get_capability_resource_registry,
            reset_capability_resource_registry,
            CapabilityResourceRegistry,
            CapabilityToolCatalog,
            ToolDefinition,
        )
        assert callable(get_capability_resource_registry)
        assert callable(reset_capability_resource_registry)
        assert CapabilityResourceRegistry is not None
        assert CapabilityToolCatalog is not None
        assert ToolDefinition is not None


@pytest.mark.unit
class TestWorkingMemoryTypes:
    """Test suite for working memory types."""

    def test_finding_creation(self):
        """Test that Finding can be created and used."""
        from jeeves_infra.protocols import Finding

        finding = Finding(
            id="test-1",
            content="Found a bug in the code",
            source="analysis",
            confidence=0.9,
        )
        assert finding.id == "test-1"
        assert finding.content == "Found a bug in the code"
        assert finding.source == "analysis"
        assert finding.confidence == 0.9

    def test_finding_to_dict(self):
        """Test Finding serialization."""
        from jeeves_infra.protocols import Finding

        finding = Finding(
            id="test-1",
            content="Test content",
            source="test",
        )
        data = finding.to_dict()
        assert data["id"] == "test-1"
        assert data["content"] == "Test content"
        assert data["source"] == "test"
        assert "created_at" in data

    def test_finding_from_dict(self):
        """Test Finding deserialization."""
        from jeeves_infra.protocols import Finding

        data = {
            "id": "test-1",
            "content": "Test content",
            "source": "test",
            "confidence": 0.8,
        }
        finding = Finding.from_dict(data)
        assert finding.id == "test-1"
        assert finding.confidence == 0.8

    def test_working_memory_creation(self):
        """Test that WorkingMemory can be created and used."""
        from jeeves_infra.protocols import WorkingMemory, Finding

        memory = WorkingMemory(session_id="session-1")
        assert memory.session_id == "session-1"
        assert memory.findings == []

        finding = Finding(id="f1", content="test", source="test")
        memory.add_finding(finding)
        assert len(memory.findings) == 1

    def test_working_memory_get_findings_by_source(self):
        """Test filtering findings by source."""
        from jeeves_infra.protocols import WorkingMemory, Finding

        memory = WorkingMemory(session_id="session-1")
        memory.add_finding(Finding(id="f1", content="test1", source="analysis"))
        memory.add_finding(Finding(id="f2", content="test2", source="search"))
        memory.add_finding(Finding(id="f3", content="test3", source="analysis"))

        analysis_findings = memory.get_findings(source="analysis")
        assert len(analysis_findings) == 2

        all_findings = memory.get_findings()
        assert len(all_findings) == 3

    def test_working_memory_protocol_compliance(self):
        """Test that WorkingMemory implements WorkingMemoryProtocol."""
        from jeeves_infra.protocols import (
            WorkingMemory,
            WorkingMemoryProtocol,
        )

        memory = WorkingMemory(session_id="session-1")
        assert isinstance(memory, WorkingMemoryProtocol)
