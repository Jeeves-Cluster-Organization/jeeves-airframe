"""Core data types for pipeline trajectory capture.

Maps directly to jeeves-core's PipelineEvent stream:
  - serde(tag = "type", rename_all = "snake_case")
  - StageMetrics: {duration_ms, llm_calls, tool_calls, tokens_in, tokens_out, tool_results, success}
  - AggregateMetrics: {total_duration_ms, total_llm_calls, total_tool_calls, total_tokens_in, total_tokens_out, stages_executed}
  - ToolCallResult: {name, success, latency_ms, error_type}
  - RoutingReason: ErrorRoute | RuleMatch{rule_index} | DefaultRoute | RouterChoice | NoMatch
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Single tool call result from a stage execution."""

    name: str
    success: bool
    latency_ms: int
    error_type: str | None = None

    @classmethod
    def from_event(cls, d: dict[str, Any]) -> ToolResult:
        return cls(
            name=str(d.get("name", "")),
            success=bool(d.get("success", False)),
            latency_ms=int(d.get("latency_ms", 0)),
            error_type=d.get("error_type"),
        )


@dataclass(frozen=True)
class RoutingDecision:
    """A routing decision between pipeline stages."""

    from_stage: str
    to_stage: str | None
    reason: str  # "ErrorRoute" | "RuleMatch" | "DefaultRoute" | "RouterChoice" | "NoMatch"
    reason_detail: tuple[tuple[str, Any], ...] = ()  # Immutable key-value pairs

    @classmethod
    def from_event(cls, d: dict[str, Any]) -> RoutingDecision:
        reason = d.get("reason", "unknown")
        detail: dict[str, Any] = {}
        # RoutingReason is serde-serialized as tagged enum:
        #   {"RuleMatch": {"rule_index": 0}} or plain string "ErrorRoute"
        if isinstance(reason, dict) and len(reason) == 1:
            reason_key = next(iter(reason))
            inner = reason[reason_key]
            detail = inner if isinstance(inner, dict) else {}
            reason = reason_key
        return cls(
            from_stage=str(d.get("from_stage", "")),
            to_stage=d.get("to_stage"),
            reason=str(reason),
            reason_detail=tuple(detail.items()),
        )


@dataclass(frozen=True)
class StageTrace:
    """Data captured from a single pipeline stage execution.

    Built from PipelineEvent stream: StageStarted -> Delta* -> ToolCallStart/ToolResult* -> StageCompleted.
    """

    stage_name: str
    duration_ms: int
    llm_calls: int
    tool_calls: int
    tokens_in: int
    tokens_out: int
    tool_results: tuple[ToolResult, ...]
    success: bool
    routing: RoutingDecision | None = None
    deltas: tuple[str, ...] = ()
    tool_events: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Step:
    """Single stage transition in a trajectory.

    Represents the execution of one pipeline stage: the accumulated state (observation)
    before the stage ran, what the model produced (action), and how it scored (reward).
    """

    stage_name: str
    observation: dict[str, Any]  # Accumulated pipeline state before this stage
    action: dict[str, Any]  # Model output: {"content": str, "tool_events": [...]}
    reward: float  # Scored by RewardFn (0.0 if no reward fn)
    stage_trace: StageTrace
    terminal: bool


@dataclass
class Trajectory:
    """Complete pipeline execution trajectory.

    Captures every stage's execution data from a single pipeline run.
    Multiple trajectories for the same input (with different outputs) are
    used for DPO/GRPO dataset building.
    """

    trajectory_id: str
    pipeline_name: str
    input: str
    steps: list[Step]
    terminal_reason: str | None
    aggregate_metrics: dict[str, Any]
    outputs: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    @property
    def total_reward(self) -> float:
        return sum(s.reward for s in self.steps)

    @property
    def stage_names(self) -> list[str]:
        return [s.stage_name for s in self.steps]

    def step_for_stage(self, stage_name: str) -> Step | None:
        for s in self.steps:
            if s.stage_name == stage_name:
                return s
        return None
