"""GrpoBuilder — build GRPO (Group Relative Policy Optimization) datasets.

Output format:
    {"prompt": [{"role": "user", "content": "..."}], "completions": ["output1", ...], "rewards": [0.8, ...]}
"""

from __future__ import annotations

from typing import Any

from jeeves_airframe.reward.base import RewardFn
from jeeves_airframe.trajectory.types import Step, Trajectory


class GrpoBuilder:
    """Build GRPO datasets from groups of trajectories sharing the same input.

    Each group produces one example with multiple completions and their rewards.
    The training framework uses relative reward ranking within the group.

    Usage:
        grpo = GrpoBuilder(reward_fn=my_reward, group_size=4)
        grpo.add_trajectory_group(trajectories_same_input)
        grpo.export_jsonl("grpo.jsonl")
    """

    def __init__(
        self,
        reward_fn: RewardFn | None = None,
        *,
        group_size: int | None = None,
        target_stage: str | None = None,
    ):
        self._reward_fn = reward_fn
        self._group_size = group_size
        self._target_stage = target_stage
        self._examples: list[dict[str, Any]] = []

    def add_trajectory_group(self, trajectories: list[Trajectory]) -> int:
        """Add a group of trajectories for the same input. Returns 1 if example added, 0 otherwise."""
        if not trajectories:
            return 0

        # Limit to group_size if set
        group = trajectories[: self._group_size] if self._group_size else trajectories

        completions: list[str] = []
        rewards: list[float] = []

        for t in group:
            step = self._get_target_step(t)
            if step is None:
                continue
            completions.append(step.action.get("content", ""))
            if self._reward_fn:
                rewards.append(self._reward_fn.score(step))
            else:
                rewards.append(step.reward)

        if len(completions) < 2:
            return 0

        # Build prompt from the first trajectory's target step observation
        first_step = self._get_target_step(group[0])
        prompt = self._build_prompt(group[0], first_step)

        self._examples.append({
            "prompt": prompt,
            "completions": completions,
            "rewards": rewards,
        })
        return 1

    def build(self) -> list[dict[str, Any]]:
        return list(self._examples)

    def export_jsonl(self, path: str) -> int:
        import json
        from pathlib import Path

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for ex in self._examples:
                f.write(json.dumps(ex) + "\n")
        return len(self._examples)

    def _get_target_step(self, trajectory: Trajectory) -> Step | None:
        if self._target_stage:
            return trajectory.step_for_stage(self._target_stage)
        return trajectory.steps[-1] if trajectory.steps else None

    def _build_prompt(self, trajectory: Trajectory, step: Step | None) -> list[dict[str, str]]:
        if step is None:
            return [{"role": "user", "content": trajectory.input}]

        prior = step.observation.get("prior_outputs", {})
        context_parts = [f"Input: {trajectory.input}"]
        for stage_name, output in prior.items():
            content = output.get("content", "") if isinstance(output, dict) else str(output)
            if content:
                context_parts.append(f"[{stage_name}]: {content}")

        return [{"role": "user", "content": "\n\n".join(context_parts)}]

    def __len__(self) -> int:
        return len(self._examples)
