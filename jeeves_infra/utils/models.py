"""Shared data models used across core and verticals.

These models are re-exported from protocols for backwards compatibility.
The canonical definitions are in protocols.validation (L0).

RULE 3 Compliance: common/ must not import from agents/.
Models that need to be used in common/ live here.
"""

# Re-export validation types from protocols (L0) for backwards compatibility
from jeeves_infra.protocols.validation import MetaValidationIssue, VerificationReport

__all__ = [
    "MetaValidationIssue",
    "VerificationReport",
]
