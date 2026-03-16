"""Tests for trajectory collection and storage."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _helpers import MockRunner, make_events

from jeeves_airframe.trajectory.collector import TrajectoryCollector
from jeeves_airframe.trajectory.storage import TrajectoryStore
from jeeves_airframe.trajectory.types import Trajectory


class TestTrajectoryCollector:
    def test_collect_basic(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        assert isinstance(trajectory, Trajectory)
        assert trajectory.input == "hello"
        assert trajectory.pipeline_name == "test_pipeline"
        assert trajectory.terminal_reason == "Completed"
        assert len(trajectory.steps) == 2

    def test_step_stage_names(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        assert trajectory.stage_names == ["classify", "respond"]

    def test_step_observations_accumulate(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        # First step has empty prior outputs
        assert trajectory.steps[0].observation["prior_outputs"] == {}

        # Second step has classify's output
        prior = trajectory.steps[1].observation["prior_outputs"]
        assert "classify" in prior

    def test_step_actions_capture_content(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        assert trajectory.steps[0].action["content"] == "intent: greeting"
        assert trajectory.steps[1].action["content"] == "Hello! How can I help you today?"

    def test_step_tool_events_captured(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        tool_events = trajectory.steps[0].action["tool_events"]
        assert len(tool_events) == 2
        assert tool_events[0]["type"] == "start"
        assert tool_events[0]["name"] == "lookup"
        assert tool_events[1]["type"] == "result"

    def test_stage_trace_metrics(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        trace = trajectory.steps[0].stage_trace
        assert trace.duration_ms == 800
        assert trace.llm_calls == 1
        assert trace.tool_calls == 1
        assert trace.tokens_in == 200
        assert trace.tokens_out == 50
        assert trace.success is True
        assert len(trace.tool_results) == 1
        assert trace.tool_results[0].name == "lookup"
        assert trace.tool_results[0].success is True

    def test_routing_captured(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        routing = trajectory.steps[0].stage_trace.routing
        assert routing is not None
        assert routing.from_stage == "classify"
        assert routing.to_stage == "respond"
        assert routing.reason == "DefaultRoute"

    def test_aggregate_metrics(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        agg = trajectory.aggregate_metrics
        assert agg["total_duration_ms"] == 2000
        assert agg["total_llm_calls"] == 2

    def test_terminal_step_marked(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        assert trajectory.steps[0].terminal is False
        assert trajectory.steps[1].terminal is True

    def test_include_deltas(self, mock_runner):
        collector = TrajectoryCollector(include_deltas=True)
        trajectory = collector.collect(mock_runner, "hello")

        assert trajectory.steps[0].stage_trace.deltas == ("intent: greeting",)

    def test_deltas_excluded_by_default(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        assert trajectory.steps[0].stage_trace.deltas == ()

    def test_collect_with_reward_fn(self, mock_runner):
        from jeeves_airframe.reward.custom import CustomReward

        reward = CustomReward("always_one", lambda step: 1.0)
        collector = TrajectoryCollector(reward_fn=reward)
        trajectory = collector.collect(mock_runner, "hello")

        assert all(s.reward == 1.0 for s in trajectory.steps)
        assert trajectory.total_reward == 2.0

    def test_collect_batch(self, mock_runner):
        collector = TrajectoryCollector()
        trajectories = collector.collect_batch(mock_runner, ["hello", "world"])

        assert len(trajectories) == 2
        assert trajectories[0].input == "hello"
        assert trajectories[1].input == "world"

    def test_build_from_raw_events(self, default_events):
        collector = TrajectoryCollector()
        trajectory = collector.build_trajectory(default_events, input="test")

        assert trajectory.input == "test"
        assert len(trajectory.steps) == 2

    def test_outputs_captured(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        assert trajectory.outputs == {"final": "Hello! How can I help you today?"}

    def test_step_for_stage(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        step = trajectory.step_for_stage("classify")
        assert step is not None
        assert step.stage_name == "classify"

        assert trajectory.step_for_stage("nonexistent") is None


class TestTrajectoryStore:
    def test_save_and_load(self, mock_runner):
        collector = TrajectoryCollector()
        trajectory = collector.collect(mock_runner, "hello")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TrajectoryStore(Path(tmpdir) / "test.jsonl")
            store.save(trajectory)

            loaded = store.load_all()
            assert len(loaded) == 1
            assert loaded[0].trajectory_id == trajectory.trajectory_id
            assert loaded[0].input == "hello"
            assert len(loaded[0].steps) == 2

    def test_save_batch_and_count(self, mock_runner):
        collector = TrajectoryCollector()
        trajectories = collector.collect_batch(mock_runner, ["a", "b", "c"])

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TrajectoryStore(Path(tmpdir) / "test.jsonl")
            store.save_batch(trajectories)

            assert store.count() == 3

    def test_load_filtered(self, mock_runner):
        collector = TrajectoryCollector()
        trajectories = collector.collect_batch(mock_runner, ["hello", "world"])

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TrajectoryStore(Path(tmpdir) / "test.jsonl")
            store.save_batch(trajectories)

            filtered = list(store.load_filtered(lambda d: d["input"] == "hello"))
            assert len(filtered) == 1
            assert filtered[0].input == "hello"

    def test_roundtrip_preserves_types(self, mock_runner):
        collector = TrajectoryCollector(include_deltas=True)
        trajectory = collector.collect(mock_runner, "hello")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TrajectoryStore(Path(tmpdir) / "test.jsonl")
            store.save(trajectory)

            loaded = store.load_all()[0]

            # Verify step types
            step = loaded.steps[0]
            assert isinstance(step.stage_trace.tool_results[0].name, str)
            assert isinstance(step.stage_trace.tool_results[0].success, bool)
            assert isinstance(step.stage_trace.routing.from_stage, str)
            assert step.stage_trace.deltas == ("intent: greeting",)

    def test_empty_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TrajectoryStore(Path(tmpdir) / "nonexistent.jsonl")
            assert store.count() == 0
            assert store.load_all() == []
