"""Working memory protocols - generic interfaces for session state.

Capabilities implement these protocols with domain-specific types.
This module provides base classes that can be extended by capability layers.

Architecture:
    jeeves-infra defines: Finding, WorkingMemory (base types)
    Capabilities extend: Add domain-specific fields (focus_state, entity_refs, etc.)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class Finding:
    """A discovered fact during execution.

    Findings represent knowledge extracted during agent execution,
    such as code patterns, errors, or insights from analysis.

    Attributes:
        id: Unique identifier for this finding
        content: The actual finding content/description
        source: Where this finding came from (file, analysis, etc.)
        confidence: Confidence score (0.0 to 1.0)
        metadata: Additional context about the finding
        created_at: When this finding was created
    """
    id: str
    content: str
    source: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        """Create from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        return cls(
            id=data["id"],
            content=data["content"],
            source=data["source"],
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


@dataclass
class WorkingMemory:
    """Generic working memory state container.

    Working memory holds the current session state including findings,
    metadata, and timestamps. Capabilities can extend this with
    domain-specific fields.

    Attributes:
        session_id: The session this memory belongs to
        findings: List of discovered facts
        metadata: Additional session metadata
        created_at: When this memory was created
        updated_at: Last update timestamp
    """
    session_id: str
    findings: List[Finding] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to working memory."""
        self.findings.append(finding)
        self.updated_at = datetime.now()

    def get_findings(self, source: Optional[str] = None) -> List[Finding]:
        """Get findings, optionally filtered by source."""
        if source is None:
            return self.findings
        return [f for f in self.findings if f.source == source]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "findings": [f.to_dict() for f in self.findings],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkingMemory":
        """Create from dictionary."""
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now()

        findings = [
            Finding.from_dict(f) if isinstance(f, dict) else f
            for f in data.get("findings", [])
        ]

        return cls(
            session_id=data["session_id"],
            findings=findings,
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
        )


@runtime_checkable
class WorkingMemoryProtocol(Protocol):
    """Protocol for working memory implementations.

    Capabilities can implement this protocol to provide custom
    working memory behavior while maintaining compatibility with
    the infrastructure layer.
    """
    session_id: str
    findings: List[Finding]

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to working memory."""
        ...

    def get_findings(self, source: Optional[str] = None) -> List[Finding]:
        """Get findings, optionally filtered by source."""
        ...


__all__ = [
    "Finding",
    "WorkingMemory",
    "WorkingMemoryProtocol",
]
