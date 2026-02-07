"""Meta-validation types for the verification layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class MetaValidationIssue:
    type: str = ""
    message: str = ""
    severity: str = "warning"


@dataclass
class VerificationReport:
    approved: bool = False
    issues_found: List[MetaValidationIssue] = field(default_factory=list)
