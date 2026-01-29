"""
Mission System Contracts Package.

This package exports stable type contracts for app integration:
- Core types from jeeves_core_engine (re-exported for convenience)

Architecture:
    apps/verticals → mission_system.contracts (types only)
                  → mission_system.adapters (infrastructure)

Centralized Architecture (v4.0):
    All imports like `from mission_system.contracts import Envelope`
    work correctly. The core contracts are re-exported via * import from contracts_core.

Layer Extraction Compliant:
    Capability-specific contracts are owned by capabilities and registered
    via CapabilityResourceRegistry. This module only exports generic contracts.
"""

# Re-export ALL core contracts from contracts_core.py
# This maintains backward compatibility with existing imports
from mission_system.contracts_core import *

# Import __all__ from contracts_core to extend it
from mission_system.contracts_core import __all__ as _core_all

# Export only core contracts - capability-specific contracts are registered dynamically
__all__ = list(_core_all)
