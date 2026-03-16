"""Tests for dataset builders (SFT, DPO, GRPO)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from _helpers import MockRunner

from jeeves_airframe.dataset.dpo import DpoBuilder
from jeeves_airframe.dataset.export import export_jsonl, load_jsonl
from jeeves_airframe.dataset.grpo import GrpoBuilder
from jeeves_airframe.dataset.sft import SftBuilder
from jeeves_airframe.reward.custom import CustomReward
from jeeves_airframe.trajectory.collector import TrajectoryCollector


def _collect_trajectory(input: str = "hello", reward_fn=None):
    runner = MockRunner()
    collector = TrajectoryCollector(reward_fn=reward_fn)
    return collector.collect(runner, input)


class TestSftBuilder:
    def test_basic(self):
        sft = SftBuilder()
        t = _collect_trajectory()
        added = sft.add_trajectory(t)
        assert added == 2  # Two stages

        examples = sft.build()
        assert len(examples) == 2
        for ex in examples:
            assert "messages" in ex
            msgs = ex["messages"]
            assert msgs[-1]["role"] == "assistant"
            assert msgs[-2]["role"] == "user"

    def test_include_stages_filter(self):
        sft = SftBuilder(include_stages=["respond"])
        t = _collect_trajectory()
        sft.add_trajectory(t)

        examples = sft.build()
        assert len(examples) == 1

    def test_min_reward_filter(self):
        reward = CustomReward("test", lambda s: 0.5 if s.stage_name == "respond" else 0.1)
        t = _collect_trajectory(reward_fn=reward)

        sft = SftBuilder(min_reward=0.3)
        sft.add_trajectory(t)

        examples = sft.build()
        assert len(examples) == 1  # Only "respond" step passes

    def test_system_prompt(self):
        sft = SftBuilder(system_prompt="You are a helpful assistant.")
        t = _collect_trajectory()
        sft.add_trajectory(t)

        examples = sft.build()
        assert examples[0]["messages"][0]["role"] == "system"
        assert examples[0]["messages"][0]["content"] == "You are a helpful assistant."

    def test_export_jsonl(self):
        sft = SftBuilder()
        t = _collect_trajectory()
        sft.add_trajectory(t)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sft.jsonl"
            count = sft.export_jsonl(str(path))
            assert count == 2

            lines = load_jsonl(path)
            assert len(lines) == 2
            assert "messages" in lines[0]

    def test_add_trajectories(self):
        sft = SftBuilder()
        t1 = _collect_trajectory("hello")
        t2 = _collect_trajectory("world")
        added = sft.add_trajectories([t1, t2])
        assert added == 4
        assert len(sft) == 4

    def test_prior_outputs_in_context(self):
        sft = SftBuilder()
        t = _collect_trajectory()
        sft.add_trajectory(t)

        # Second step (respond) should have classify's output in context
        respond_example = sft.build()[1]
        user_msg = respond_example["messages"][-2]["content"]
        assert "[classify]" in user_msg


class TestDpoBuilder:
    def test_basic_pair(self):
        good_reward = CustomReward("good", lambda s: 1.0)
        bad_reward = CustomReward("bad", lambda s: 0.0)

        t_good = _collect_trajectory("hello", reward_fn=good_reward)
        t_bad = _collect_trajectory("hello", reward_fn=bad_reward)

        dpo = DpoBuilder(margin=0.0)
        added = dpo.add_trajectory_group([t_good, t_bad])
        assert added == 1

        pairs = dpo.build()
        assert len(pairs) == 1
        assert "prompt" in pairs[0]
        assert "chosen" in pairs[0]
        assert "rejected" in pairs[0]

    def test_margin_filtering(self):
        r1 = CustomReward("r1", lambda s: 0.5)
        r2 = CustomReward("r2", lambda s: 0.4)

        t1 = _collect_trajectory("hello", reward_fn=r1)
        t2 = _collect_trajectory("hello", reward_fn=r2)

        dpo = DpoBuilder(margin=0.5)  # Margin too high
        added = dpo.add_trajectory_group([t1, t2])
        assert added == 0

    def test_needs_at_least_two(self):
        t = _collect_trajectory()
        dpo = DpoBuilder()
        assert dpo.add_trajectory_group([t]) == 0

    def test_export_jsonl(self):
        r1 = CustomReward("good", lambda s: 1.0)
        r2 = CustomReward("bad", lambda s: 0.0)
        t1 = _collect_trajectory("hello", reward_fn=r1)
        t2 = _collect_trajectory("hello", reward_fn=r2)

        dpo = DpoBuilder()
        dpo.add_trajectory_group([t1, t2])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dpo.jsonl"
            count = dpo.export_jsonl(str(path))
            assert count == 1

            data = load_jsonl(path)
            assert "chosen" in data[0]


class TestGrpoBuilder:
    def test_basic_group(self):
        rewards = [0.2, 0.8, 0.5, 0.9]
        trajectories = []
        for r in rewards:
            reward_fn = CustomReward("r", lambda s, r=r: r)
            trajectories.append(_collect_trajectory("hello", reward_fn=reward_fn))

        grpo = GrpoBuilder()
        added = grpo.add_trajectory_group(trajectories)
        assert added == 1

        examples = grpo.build()
        assert len(examples) == 1
        assert len(examples[0]["completions"]) == 4
        assert len(examples[0]["rewards"]) == 4
        assert "prompt" in examples[0]

    def test_group_size_limit(self):
        trajectories = [_collect_trajectory("hello") for _ in range(8)]

        grpo = GrpoBuilder(group_size=4)
        grpo.add_trajectory_group(trajectories)

        examples = grpo.build()
        assert len(examples[0]["completions"]) == 4

    def test_needs_at_least_two(self):
        grpo = GrpoBuilder()
        assert grpo.add_trajectory_group([_collect_trajectory()]) == 0

    def test_export_jsonl(self):
        trajectories = [_collect_trajectory("hello") for _ in range(3)]

        grpo = GrpoBuilder()
        grpo.add_trajectory_group(trajectories)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "grpo.jsonl"
            count = grpo.export_jsonl(str(path))
            assert count == 1

            data = load_jsonl(path)
            assert "completions" in data[0]
            assert "rewards" in data[0]

    def test_with_reward_fn(self):
        reward_fn = CustomReward("score", lambda s: len(s.action.get("content", "")) / 100.0)

        trajectories = [_collect_trajectory("hello") for _ in range(3)]

        grpo = GrpoBuilder(reward_fn=reward_fn)
        grpo.add_trajectory_group(trajectories)

        examples = grpo.build()
        # All rewards should be computed by reward_fn, not from trajectory
        assert all(r > 0 for r in examples[0]["rewards"])


class TestExport:
    def test_export_and_load_jsonl(self):
        data = [{"a": 1, "b": "test"}, {"a": 2, "b": "hello"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.jsonl"
            count = export_jsonl(data, path)
            assert count == 2

            loaded = load_jsonl(path)
            assert loaded == data
