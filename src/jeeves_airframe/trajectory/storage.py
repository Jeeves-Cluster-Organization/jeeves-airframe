"""TrajectoryStore — JSONL-based trajectory persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterator

from jeeves_airframe.trajectory.types import (
    RoutingDecision,
    StageTrace,
    Step,
    ToolResult,
    Trajectory,
)


class TrajectoryStore:
    """Append-only JSONL store for trajectories.

    Usage:
        store = TrajectoryStore("trajectories/runs.jsonl")
        store.save(trajectory)
        store.save_batch(trajectories)
        for t in store.load():
            print(t.trajectory_id, t.total_reward)
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, trajectory: Trajectory) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(trajectory), default=str) + "\n")

    def save_batch(self, trajectories: list[Trajectory]) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            for t in trajectories:
                f.write(json.dumps(asdict(t), default=str) + "\n")

    def load(self) -> Iterator[Trajectory]:
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield _trajectory_from_dict(json.loads(line))

    def load_filtered(self, filter_fn: Callable[[dict[str, Any]], bool]) -> Iterator[Trajectory]:
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if filter_fn(d):
                    yield _trajectory_from_dict(d)

    def load_all(self) -> list[Trajectory]:
        return list(self.load())

    def count(self) -> int:
        if not self._path.exists():
            return 0
        n = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n


def _trajectory_from_dict(d: dict[str, Any]) -> Trajectory:
    """Reconstruct a Trajectory from a deserialized dict."""
    steps = []
    for sd in d.get("steps", []):
        trace_d = sd["stage_trace"]
        routing = None
        if trace_d.get("routing"):
            rd = trace_d["routing"]
            # reason_detail is serialized as list of [key, value] pairs (from tuple)
            detail_raw = rd.get("reason_detail", [])
            detail = tuple(tuple(pair) for pair in detail_raw) if detail_raw else ()
            routing = RoutingDecision(
                from_stage=rd["from_stage"],
                to_stage=rd.get("to_stage"),
                reason=rd["reason"],
                reason_detail=detail,
            )
        trace = StageTrace(
            stage_name=trace_d["stage_name"],
            duration_ms=trace_d["duration_ms"],
            llm_calls=trace_d["llm_calls"],
            tool_calls=trace_d["tool_calls"],
            tokens_in=trace_d["tokens_in"],
            tokens_out=trace_d["tokens_out"],
            tool_results=tuple(
                ToolResult(
                    name=tr["name"],
                    success=tr["success"],
                    latency_ms=tr["latency_ms"],
                    error_type=tr.get("error_type"),
                )
                for tr in trace_d.get("tool_results", [])
            ),
            success=trace_d["success"],
            routing=routing,
            deltas=tuple(trace_d.get("deltas", [])),
            tool_events=tuple(trace_d.get("tool_events", [])),
        )
        steps.append(
            Step(
                stage_name=sd["stage_name"],
                observation=sd["observation"],
                action=sd["action"],
                reward=sd["reward"],
                stage_trace=trace,
                terminal=sd["terminal"],
            )
        )
    return Trajectory(
        trajectory_id=d["trajectory_id"],
        pipeline_name=d["pipeline_name"],
        input=d["input"],
        steps=steps,
        terminal_reason=d.get("terminal_reason"),
        aggregate_metrics=d.get("aggregate_metrics", {}),
        outputs=d.get("outputs", {}),
        metadata=d.get("metadata", {}),
        timestamp=d.get("timestamp", ""),
    )
