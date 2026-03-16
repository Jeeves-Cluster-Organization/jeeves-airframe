"""DpoBuilder — build DPO preference datasets from trajectory groups.

Output format (TRL-compatible):
    {"prompt": [{"role": "user", "content": "..."}], "chosen": "good output", "rejected": "bad output"}
"""

from __future__ import annotations

from typing import Any

from jeeves_airframe.reward.base import RewardFn
from jeeves_airframe.trajectory.types import Step, Trajectory


class DpoBuilder:
    """Build DPO datasets from groups of trajectories sharing the same input.

    For each group, pairs the highest-reward trajectory (chosen) with
    the lowest-reward trajectory (rejected), provided the margin is met.

    Usage:
        dpo = DpoBuilder(reward_fn=my_reward, margin=0.1)
        dpo.add_trajectory_group(trajectories_same_input)
        dpo.export_jsonl("dpo.jsonl")
    """

    def __init__(
        self,
        reward_fn: RewardFn | None = None,
        *,
        margin: float = 0.0,
        target_stage: str | None = None,
    ):
        self._reward_fn = reward_fn
        self._margin = margin
        self._target_stage = target_stage
        self._pairs: list[dict[str, Any]] = []

    def add_trajectory_group(self, trajectories: list[Trajectory]) -> int:
        """Add a group of trajectories for the same input. Returns pairs added."""
        if len(trajectories) < 2:
            return 0

        scored = self._score_trajectories(trajectories)
        scored.sort(key=lambda x: x[1], reverse=True)

        added = 0
        best_traj, best_score = scored[0]
        worst_traj, worst_score = scored[-1]

        if best_score - worst_score >= self._margin:
            pair = self._build_pair(best_traj, worst_traj)
            if pair:
                self._pairs.append(pair)
                added += 1

        return added

    def build(self) -> list[dict[str, Any]]:
        return list(self._pairs)

    def export_jsonl(self, path: str) -> int:
        import json
        from pathlib import Path

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for pair in self._pairs:
                f.write(json.dumps(pair) + "\n")
        return len(self._pairs)

    def _score_trajectories(self, trajectories: list[Trajectory]) -> list[tuple[Trajectory, float]]:
        results = []
        for t in trajectories:
            if self._reward_fn:
                score = sum(self._reward_fn.score(s) for s in t.steps)
            else:
                score = t.total_reward
            results.append((t, score))
        return results

    def _build_pair(self, chosen: Trajectory, rejected: Trajectory) -> dict[str, Any] | None:
        chosen_step = self._get_target_step(chosen)
        rejected_step = self._get_target_step(rejected)
        if chosen_step is None or rejected_step is None:
            return None

        # Build prompt from observation
        prompt_parts: list[dict[str, str]] = []
        prior = chosen_step.observation.get("prior_outputs", {})
        context_parts = [f"Input: {chosen.input}"]
        for stage_name, output in prior.items():
            content = output.get("content", "") if isinstance(output, dict) else str(output)
            if content:
                context_parts.append(f"[{stage_name}]: {content}")
        prompt_parts.append({"role": "user", "content": "\n\n".join(context_parts)})

        return {
            "prompt": prompt_parts,
            "chosen": chosen_step.action.get("content", ""),
            "rejected": rejected_step.action.get("content", ""),
        }

    def _get_target_step(self, trajectory: Trajectory) -> Step | None:
        if self._target_stage:
            return trajectory.step_for_stage(self._target_stage)
        return trajectory.steps[-1] if trajectory.steps else None

    def __len__(self) -> int:
        return len(self._pairs)
