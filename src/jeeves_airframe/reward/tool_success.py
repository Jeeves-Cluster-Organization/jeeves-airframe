"""ToolSuccessRateReward — reward based on tool call success rate."""

from __future__ import annotations

from jeeves_airframe.trajectory.types import Step


class ToolSuccessRateReward:
    """Scores the fraction of successful tool calls in a step.

    Returns 1.0 if all tools succeeded (or no tools were called),
    0.0 if all failed, proportional otherwise.
    """

    def __init__(self, *, no_tools_score: float = 1.0):
        self._no_tools_score = no_tools_score

    @property
    def name(self) -> str:
        return "tool_success_rate"

    def score(self, step: Step) -> float:
        results = step.stage_trace.tool_results
        if not results:
            return self._no_tools_score
        return sum(1.0 for r in results if r.success) / len(results)
