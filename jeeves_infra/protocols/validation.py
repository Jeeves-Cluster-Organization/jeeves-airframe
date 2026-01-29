"""Validation types for meta-validation and verification.

Provides:
- MetaValidationIssue: Issue detected during validation
- VerificationReport: Report from verification process
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MetaValidationIssue:
    """An issue detected during meta-validation.

    Attributes:
        type: Issue type identifier (e.g., "tool_count_mismatch")
        message: Human-readable description
        severity: Issue severity (error, warning, info)
        location: Where the issue was found
    """
    type: str
    message: str = ""
    severity: str = "error"
    location: Optional[str] = None


@dataclass
class VerificationReport:
    """Report from a verification process.

    Attributes:
        approved: Whether the verification passed
        issues_found: List of issues detected
        summary: Summary of the verification
    """
    approved: bool = False
    issues_found: List[MetaValidationIssue] = field(default_factory=list)
    summary: str = ""


__all__ = [
    "MetaValidationIssue",
    "VerificationReport",
]
