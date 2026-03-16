"""CustomReward — wraps an arbitrary Python callable as a RewardFn."""

from __future__ import annotations

from typing import Callable

from jeeves_airframe.trajectory.types import Step


class CustomReward:
    """Wraps a callable as a reward function.

    Usage:
        reward = CustomReward("length_penalty", lambda step: -len(step.action["content"]) / 1000)
    """

    def __init__(self, name: str, fn: Callable[[Step], float]):
        self._name = name
        self._fn = fn

    @property
    def name(self) -> str:
        return self._name

    def score(self, step: Step) -> float:
        return self._fn(step)
