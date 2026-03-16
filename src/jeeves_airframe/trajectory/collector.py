"""TrajectoryCollector — builds Trajectory objects from PipelineRunner.stream() events."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable, Protocol

from jeeves_airframe.trajectory.types import (
    RoutingDecision,
    StageTrace,
    Step,
    ToolResult,
    Trajectory,
)

if TYPE_CHECKING:
    from jeeves_airframe.reward.base import RewardFn


class StreamableRunner(Protocol):
    """Protocol for anything that exposes a stream() method returning PipelineEvent dicts."""

    def stream(
        self,
        input: str,
        *,
        user_id: str = ...,
        session_id: str | None = ...,
        pipeline_name: str | None = ...,
        metadata: dict[str, Any] | None = ...,
    ) -> Iterable[dict[str, Any]]: ...


class TrajectoryCollector:
    """Collects trajectory data from PipelineRunner event streams.

    Usage:
        collector = TrajectoryCollector(reward_fn=my_reward)
        trajectory = collector.collect(runner, "hello world")
        # trajectory.steps contains per-stage data with rewards
    """

    def __init__(self, reward_fn: RewardFn | None = None, *, include_deltas: bool = False):
        self._reward_fn = reward_fn
        self._include_deltas = include_deltas

    def collect(
        self,
        runner: StreamableRunner,
        input: str,
        *,
        user_id: str = "airframe",
        pipeline_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Trajectory:
        """Run a pipeline and collect the full trajectory."""
        events = list(
            runner.stream(
                input,
                user_id=user_id,
                pipeline_name=pipeline_name,
                metadata=metadata,
            )
        )
        return self.build_trajectory(events, input=input, metadata=metadata)

    def collect_batch(
        self,
        runner: StreamableRunner,
        inputs: list[str],
        *,
        user_id: str = "airframe",
        pipeline_name: str | None = None,
    ) -> list[Trajectory]:
        """Collect trajectories for multiple inputs sequentially."""
        return [
            self.collect(runner, inp, user_id=user_id, pipeline_name=pipeline_name)
            for inp in inputs
        ]

    def build_trajectory(
        self,
        events: list[dict[str, Any]],
        *,
        input: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Trajectory:
        """Build a Trajectory from a list of PipelineEvent dicts.

        This can also be used to rebuild trajectories from stored events.
        """
        stages: list[_StageAccumulator] = []
        current: _StageAccumulator | None = None
        done_event: dict[str, Any] | None = None
        pipeline_name = ""

        for event in events:
            etype = event.get("type", "")
            pipeline_name = event.get("pipeline", pipeline_name)

            if etype == "stage_started":
                current = _StageAccumulator(stage_name=event.get("stage", ""))
                stages.append(current)

            elif etype == "delta" and current is not None:
                current.deltas.append(event.get("content", ""))

            elif etype == "tool_call_start" and current is not None:
                current.tool_events.append({
                    "type": "start",
                    "id": event.get("id", ""),
                    "name": event.get("name", ""),
                })

            elif etype == "tool_result" and current is not None:
                current.tool_events.append({
                    "type": "result",
                    "id": event.get("id", ""),
                    "content": event.get("content", ""),
                })

            elif etype == "stage_completed" and current is not None:
                current.metrics = event.get("metrics") or {}
                current = None

            elif etype == "routing_decision":
                rd = RoutingDecision.from_event(event)
                for s in reversed(stages):
                    if s.stage_name == event.get("from_stage"):
                        s.routing = rd
                        break

            elif etype == "done":
                done_event = event

            elif etype == "error":
                if current is not None:
                    current.error = event.get("message", "")

        # Build steps from accumulated stage data
        steps: list[Step] = []
        accumulated_outputs: dict[str, Any] = {}

        for i, acc in enumerate(stages):
            is_terminal = i == len(stages) - 1
            observation = {"prior_outputs": dict(accumulated_outputs), "input": input}

            content = "".join(acc.deltas)
            action: dict[str, Any] = {"content": content, "tool_events": list(acc.tool_events)}

            metrics = acc.metrics
            trace = StageTrace(
                stage_name=acc.stage_name,
                duration_ms=int(metrics.get("duration_ms", 0)),
                llm_calls=int(metrics.get("llm_calls", 0)),
                tool_calls=int(metrics.get("tool_calls", 0)),
                tokens_in=int(metrics.get("tokens_in", 0)),
                tokens_out=int(metrics.get("tokens_out", 0)),
                tool_results=tuple(ToolResult.from_event(tr) for tr in metrics.get("tool_results", [])),
                success=bool(metrics.get("success", True)),
                routing=acc.routing,
                deltas=tuple(acc.deltas) if self._include_deltas else (),
                tool_events=tuple(acc.tool_events),
            )

            step = Step(
                stage_name=acc.stage_name,
                observation=observation,
                action=action,
                reward=0.0,
                stage_trace=trace,
                terminal=is_terminal,
            )

            if self._reward_fn is not None:
                reward = self._reward_fn.score(step)
                step = Step(
                    stage_name=step.stage_name,
                    observation=step.observation,
                    action=step.action,
                    reward=reward,
                    stage_trace=step.stage_trace,
                    terminal=step.terminal,
                )

            steps.append(step)
            accumulated_outputs[acc.stage_name] = action

        outputs = (done_event or {}).get("outputs") or {}
        terminal_reason = (done_event or {}).get("terminal_reason")
        agg_metrics = (done_event or {}).get("aggregate_metrics") or {}

        return Trajectory(
            trajectory_id=uuid.uuid4().hex[:16],
            pipeline_name=pipeline_name,
            input=input,
            steps=steps,
            terminal_reason=terminal_reason,
            aggregate_metrics=agg_metrics,
            outputs=outputs if isinstance(outputs, dict) else {},
            metadata=metadata or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class _StageAccumulator:
    """Internal: accumulates events for a single stage during collection."""

    __slots__ = ("stage_name", "deltas", "tool_events", "metrics", "routing", "error")

    def __init__(self, stage_name: str) -> None:
        self.stage_name = stage_name
        self.deltas: list[str] = []
        self.tool_events: list[dict[str, Any]] = []
        self.metrics: dict[str, Any] = {}
        self.routing: RoutingDecision | None = None
        self.error: str | None = None
