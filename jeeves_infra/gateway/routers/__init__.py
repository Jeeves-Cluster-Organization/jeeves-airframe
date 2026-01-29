"""Gateway routers package.

Code Analysis Focus (v3.0 Pivot):
- REMOVED: kanban, journal, open_loops routers
- FOCUS: chat, governance (health), interrupts

Unified Interrupt System (v4.0):
- interrupts: Single endpoint for all interrupt types (clarification, confirmation, etc.)
- Replaces separate /clarifications and /confirmations endpoints

Note: governance router is now in health.py (renamed in f670752)
"""

from jeeves_infra.gateway.routers import chat, interrupts
from jeeves_infra.gateway.routers import health as governance

__all__ = ["chat", "governance", "interrupts"]
