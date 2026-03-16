"""ModelComparison — compare two EvalResults side-by-side."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jeeves_airframe.eval.harness import EvalResult


@dataclass
class ModelComparison:
    """Compare baseline vs candidate EvalResults.

    Usage:
        comparison = ModelComparison(baseline=result_v1, candidate=result_v2)
        print(comparison.summary())
        print(comparison.per_stage_delta())
    """

    baseline: EvalResult
    candidate: EvalResult

    def summary(self) -> dict[str, Any]:
        b_reward = self.baseline.reward_stats.get("mean", 0)
        c_reward = self.candidate.reward_stats.get("mean", 0)

        b_rewards = [t.total_reward for t in self.baseline.trajectories]
        c_rewards = [t.total_reward for t in self.candidate.trajectories]

        # Win rate: fraction of examples where candidate beats baseline
        wins = sum(
            1 for b, c in zip(b_rewards, c_rewards) if c > b
        )
        ties = sum(
            1 for b, c in zip(b_rewards, c_rewards) if c == b
        )
        total = min(len(b_rewards), len(c_rewards))

        return {
            "baseline_mean_reward": b_reward,
            "candidate_mean_reward": c_reward,
            "reward_delta": c_reward - b_reward,
            "win_rate": wins / total if total > 0 else 0.0,
            "tie_rate": ties / total if total > 0 else 0.0,
            "num_compared": total,
        }

    def per_stage_delta(self) -> dict[str, dict[str, float]]:
        """Per-stage metric deltas (candidate - baseline)."""
        deltas: dict[str, dict[str, float]] = {}

        all_stages = set(self.baseline.per_stage_metrics.keys()) | set(self.candidate.per_stage_metrics.keys())
        for stage in all_stages:
            b_metrics = self.baseline.per_stage_metrics.get(stage, {})
            c_metrics = self.candidate.per_stage_metrics.get(stage, {})
            all_keys = set(b_metrics.keys()) | set(c_metrics.keys())
            deltas[stage] = {
                k: c_metrics.get(k, 0) - b_metrics.get(k, 0)
                for k in all_keys
            }

        return deltas

    def win_rate(self) -> float:
        return self.summary()["win_rate"]
