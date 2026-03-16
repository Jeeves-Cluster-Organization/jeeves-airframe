"""Efficiency-based reward functions — penalize token usage and latency."""

from __future__ import annotations

from jeeves_airframe.trajectory.types import Step


class TokenEfficiencyReward:
    """Penalizes token usage relative to a budget.

    reward = -alpha * (tokens_in + tokens_out) / budget

    Lower token usage → less negative → higher reward.
    """

    def __init__(self, budget: int, *, alpha: float = 1.0):
        self._budget = budget
        self._alpha = alpha

    @property
    def name(self) -> str:
        return "token_efficiency"

    def score(self, step: Step) -> float:
        total = step.stage_trace.tokens_in + step.stage_trace.tokens_out
        return -self._alpha * total / self._budget


class LatencyReward:
    """Penalizes stage duration relative to a target.

    reward = -beta * duration_ms / target_ms
    """

    def __init__(self, target_ms: int, *, beta: float = 0.5):
        self._target_ms = target_ms
        self._beta = beta

    @property
    def name(self) -> str:
        return "latency"

    def score(self, step: Step) -> float:
        return -self._beta * step.stage_trace.duration_ms / self._target_ms
