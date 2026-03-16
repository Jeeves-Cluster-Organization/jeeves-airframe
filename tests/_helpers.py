"""Shared test helpers — mock pipeline events and runners."""

from __future__ import annotations

from typing import Any


def make_events(
    stages: list[dict[str, Any]] | None = None,
    pipeline: str = "test_pipeline",
) -> list[dict[str, Any]]:
    """Generate a realistic PipelineEvent stream for testing.

    Default: 2-stage pipeline (classify -> respond) with tool calls on classify.
    """
    if stages is None:
        stages = [
            {
                "name": "classify",
                "content": "intent: greeting",
                "tool_calls": [
                    {"id": "tc_1", "name": "lookup", "result": "found: user profile"},
                ],
                "metrics": {
                    "duration_ms": 800,
                    "llm_calls": 1,
                    "tool_calls": 1,
                    "tokens_in": 200,
                    "tokens_out": 50,
                    "tool_results": [{"name": "lookup", "success": True, "latency_ms": 150}],
                    "success": True,
                },
                "routing": {
                    "from_stage": "classify",
                    "to_stage": "respond",
                    "reason": "DefaultRoute",
                },
            },
            {
                "name": "respond",
                "content": "Hello! How can I help you today?",
                "tool_calls": [],
                "metrics": {
                    "duration_ms": 1200,
                    "llm_calls": 1,
                    "tool_calls": 0,
                    "tokens_in": 300,
                    "tokens_out": 100,
                    "tool_results": [],
                    "success": True,
                },
                "routing": None,
            },
        ]

    events: list[dict[str, Any]] = []
    for stage in stages:
        events.append({"type": "stage_started", "stage": stage["name"], "pipeline": pipeline})
        if stage.get("content"):
            events.append({"type": "delta", "content": stage["content"], "stage": stage["name"], "pipeline": pipeline})
        for tc in stage.get("tool_calls", []):
            events.append({
                "type": "tool_call_start",
                "id": tc["id"],
                "name": tc["name"],
                "stage": stage["name"],
                "pipeline": pipeline,
            })
            events.append({
                "type": "tool_result",
                "id": tc["id"],
                "content": tc.get("result", "ok"),
                "stage": stage["name"],
                "pipeline": pipeline,
            })
        events.append({
            "type": "stage_completed",
            "stage": stage["name"],
            "pipeline": pipeline,
            "metrics": stage.get("metrics", {}),
        })
        if stage.get("routing"):
            events.append({
                "type": "routing_decision",
                "pipeline": pipeline,
                **stage["routing"],
            })

    events.append({
        "type": "done",
        "process_id": "p_test_001",
        "terminated": True,
        "terminal_reason": "Completed",
        "outputs": {"final": "Hello! How can I help you today?"},
        "pipeline": pipeline,
        "aggregate_metrics": {
            "total_duration_ms": 2000,
            "total_llm_calls": 2,
            "total_tool_calls": 1,
            "total_tokens_in": 500,
            "total_tokens_out": 150,
            "stages_executed": [s["name"] for s in stages],
        },
    })
    return events


class MockRunner:
    """Mock PipelineRunner that returns pre-built events."""

    def __init__(self, events: list[dict[str, Any]] | None = None):
        self._events = events or make_events()

    def stream(self, input: str, *, user_id: str = "", session_id=None, pipeline_name=None, metadata=None):
        return iter(self._events)

    def run(self, input: str, **kwargs):
        for e in self._events:
            if e.get("type") == "done":
                return e.get("outputs", {})
        return {}
