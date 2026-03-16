"""Reward function protocol and combinators."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jeeves_airframe.trajectory.types import Step


@runtime_checkable
class RewardFn(Protocol):
    """Protocol for scoring a pipeline step."""

    @property
    def name(self) -> str: ...

    def score(self, step: Step) -> float: ...


class CompositeReward:
    """Sum of multiple reward functions."""

    def __init__(self, *fns: RewardFn):
        self._fns = list(fns)

    @property
    def name(self) -> str:
        return "+".join(f.name for f in self._fns)

    def score(self, step: Step) -> float:
        return sum(f.score(step) for f in self._fns)

    def score_breakdown(self, step: Step) -> dict[str, float]:
        return {f.name: f.score(step) for f in self._fns}


class WeightedReward:
    """Weighted combination of reward functions.

    Usage:
        reward = WeightedReward({
            "schema": (SchemaComplianceReward(schema), 2.0),
            "efficiency": (TokenEfficiencyReward(budget=1000), 0.5),
        })
        score = reward.score(step)
        breakdown = reward.score_breakdown(step)  # {"schema": 2.0, "efficiency": -0.15}
    """

    def __init__(self, weights: dict[str, tuple[RewardFn, float]]):
        self._weights = weights

    @property
    def name(self) -> str:
        return "weighted(" + ",".join(self._weights.keys()) + ")"

    def score(self, step: Step) -> float:
        return sum(fn.score(step) * w for fn, w in self._weights.values())

    def score_breakdown(self, step: Step) -> dict[str, float]:
        return {name: fn.score(step) * w for name, (fn, w) in self._weights.items()}
