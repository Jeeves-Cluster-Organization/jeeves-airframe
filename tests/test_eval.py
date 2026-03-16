"""Tests for eval harness and model comparison."""

from __future__ import annotations

import tempfile
from pathlib import Path

from _helpers import MockRunner

from jeeves_airframe.eval.compare import ModelComparison
from jeeves_airframe.eval.harness import EvalDataset, EvalHarness, EvalResult
from jeeves_airframe.reward.custom import CustomReward


class TestEvalDataset:
    def test_from_list(self):
        ds = EvalDataset.from_list([
            {"input": "hello", "expected": "greeting"},
            {"input": "bye", "expected": "farewell"},
        ])
        assert len(ds) == 2

    def test_from_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "eval.jsonl"
            path.write_text('{"input": "hello"}\n{"input": "world"}\n')

            ds = EvalDataset.from_jsonl(path)
            assert len(ds) == 2

    def test_iterable(self):
        ds = EvalDataset.from_list([{"input": "a"}, {"input": "b"}])
        assert [e["input"] for e in ds] == ["a", "b"]


class TestEvalHarness:
    def test_evaluate_basic(self):
        runner = MockRunner()
        harness = EvalHarness(runner)

        dataset = EvalDataset.from_list([
            {"input": "hello"},
            {"input": "world"},
        ])

        result = harness.evaluate(dataset)

        assert isinstance(result, EvalResult)
        assert len(result.trajectories) == 2
        assert result.aggregate["num_examples"] == 2

    def test_evaluate_with_reward(self):
        runner = MockRunner()
        reward = CustomReward("test", lambda s: 1.0)
        harness = EvalHarness(runner, reward_fn=reward)

        dataset = EvalDataset.from_list([{"input": "hello"}])
        result = harness.evaluate(dataset)

        assert result.reward_stats["mean"] == 2.0  # 2 steps * 1.0 each

    def test_per_stage_metrics(self):
        runner = MockRunner()
        harness = EvalHarness(runner)

        dataset = EvalDataset.from_list([{"input": "hello"}])
        result = harness.evaluate(dataset)

        assert "classify" in result.per_stage_metrics
        assert "respond" in result.per_stage_metrics
        assert result.per_stage_metrics["classify"]["duration_ms"] == 800
        assert result.per_stage_metrics["respond"]["tokens_out"] == 100

    def test_aggregate_metrics(self):
        runner = MockRunner()
        harness = EvalHarness(runner)

        dataset = EvalDataset.from_list([{"input": "hello"}])
        result = harness.evaluate(dataset)

        assert result.aggregate["avg_duration_ms"] == 2000


class TestModelComparison:
    def test_summary(self):
        runner = MockRunner()
        r_good = CustomReward("good", lambda s: 1.0)
        r_bad = CustomReward("bad", lambda s: 0.5)

        dataset = EvalDataset.from_list([{"input": "hello"}, {"input": "world"}])

        baseline = EvalHarness(runner, reward_fn=r_bad).evaluate(dataset)
        candidate = EvalHarness(runner, reward_fn=r_good).evaluate(dataset)

        comparison = ModelComparison(baseline=baseline, candidate=candidate)
        summary = comparison.summary()

        assert summary["reward_delta"] > 0
        assert summary["candidate_mean_reward"] > summary["baseline_mean_reward"]
        assert summary["num_compared"] == 2

    def test_win_rate(self):
        runner = MockRunner()
        r_good = CustomReward("good", lambda s: 1.0)
        r_bad = CustomReward("bad", lambda s: 0.0)

        dataset = EvalDataset.from_list([{"input": "hello"}])

        baseline = EvalHarness(runner, reward_fn=r_bad).evaluate(dataset)
        candidate = EvalHarness(runner, reward_fn=r_good).evaluate(dataset)

        comparison = ModelComparison(baseline=baseline, candidate=candidate)
        assert comparison.win_rate() == 1.0

    def test_per_stage_delta(self):
        runner = MockRunner()
        dataset = EvalDataset.from_list([{"input": "hello"}])

        result1 = EvalHarness(runner).evaluate(dataset)
        result2 = EvalHarness(runner).evaluate(dataset)

        comparison = ModelComparison(baseline=result1, candidate=result2)
        deltas = comparison.per_stage_delta()

        # Same runner → all deltas should be 0
        assert "classify" in deltas
        assert all(v == 0 for v in deltas["classify"].values())
