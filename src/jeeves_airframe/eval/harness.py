"""EvalHarness — run pipelines against eval datasets, collect metrics."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from jeeves_airframe.reward.base import RewardFn
from jeeves_airframe.trajectory.collector import StreamableRunner, TrajectoryCollector
from jeeves_airframe.trajectory.types import Trajectory


@dataclass
class EvalDataset:
    """Simple eval dataset: list of (input, expected, metadata) tuples."""

    examples: list[dict[str, Any]]

    @classmethod
    def from_jsonl(cls, path: str | Path) -> EvalDataset:
        examples = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    examples.append(json.loads(line))
        return cls(examples=examples)

    @classmethod
    def from_list(cls, examples: list[dict[str, Any]]) -> EvalDataset:
        return cls(examples=examples)

    def __len__(self) -> int:
        return len(self.examples)

    def __iter__(self):
        return iter(self.examples)


@dataclass
class EvalResult:
    """Results from evaluating a pipeline on a dataset."""

    trajectories: list[Trajectory]
    reward_stats: dict[str, float] = field(default_factory=dict)
    per_stage_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    aggregate: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_trajectories(cls, trajectories: list[Trajectory]) -> EvalResult:
        result = cls(trajectories=trajectories)
        result._compute_stats()
        return result

    def _compute_stats(self) -> None:
        if not self.trajectories:
            return

        # Reward stats
        rewards = [t.total_reward for t in self.trajectories]
        self.reward_stats = _stats(rewards)

        # Per-stage metrics
        stage_data: dict[str, dict[str, list[float]]] = {}
        for t in self.trajectories:
            for step in t.steps:
                name = step.stage_name
                if name not in stage_data:
                    stage_data[name] = {
                        "duration_ms": [],
                        "tokens_in": [],
                        "tokens_out": [],
                        "llm_calls": [],
                        "tool_calls": [],
                        "success_rate": [],
                    }
                sd = stage_data[name]
                tr = step.stage_trace
                sd["duration_ms"].append(tr.duration_ms)
                sd["tokens_in"].append(tr.tokens_in)
                sd["tokens_out"].append(tr.tokens_out)
                sd["llm_calls"].append(tr.llm_calls)
                sd["tool_calls"].append(tr.tool_calls)
                sd["success_rate"].append(1.0 if tr.success else 0.0)

        self.per_stage_metrics = {
            stage: {k: statistics.mean(v) for k, v in metrics.items() if v}
            for stage, metrics in stage_data.items()
        }

        # Aggregate
        agg_durations = [t.aggregate_metrics.get("total_duration_ms", 0) for t in self.trajectories]
        agg_tokens = [
            t.aggregate_metrics.get("total_tokens_in", 0) + t.aggregate_metrics.get("total_tokens_out", 0)
            for t in self.trajectories
        ]
        self.aggregate = {
            "avg_duration_ms": statistics.mean(agg_durations) if agg_durations else 0,
            "avg_total_tokens": statistics.mean(agg_tokens) if agg_tokens else 0,
            "num_examples": len(self.trajectories),
        }


class EvalHarness:
    """Run a pipeline against an eval dataset, collect trajectories and metrics.

    Usage:
        harness = EvalHarness(runner, reward_fn=my_reward)
        result = harness.evaluate(eval_dataset)
        print(result.reward_stats)
        print(result.per_stage_metrics)
    """

    def __init__(self, runner: StreamableRunner, reward_fn: RewardFn | None = None):
        self._runner = runner
        self._collector = TrajectoryCollector(reward_fn=reward_fn)

    def evaluate(
        self,
        dataset: EvalDataset | Iterable[dict[str, Any]],
        *,
        pipeline_name: str | None = None,
        input_key: str = "input",
    ) -> EvalResult:
        trajectories: list[Trajectory] = []
        for example in dataset:
            inp = example.get(input_key, "")
            metadata = {k: v for k, v in example.items() if k != input_key}
            t = self._collector.collect(
                self._runner,
                inp,
                pipeline_name=pipeline_name,
                metadata=metadata,
            )
            trajectories.append(t)
        return EvalResult.from_trajectories(trajectories)


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }
