"""Tests for reward functions."""

from __future__ import annotations

from jeeves_airframe.reward.base import CompositeReward, RewardFn, WeightedReward
from jeeves_airframe.reward.custom import CustomReward
from jeeves_airframe.reward.efficiency import LatencyReward, TokenEfficiencyReward
from jeeves_airframe.reward.schema import SchemaComplianceReward
from jeeves_airframe.reward.tool_success import ToolSuccessRateReward
from jeeves_airframe.trajectory.types import Step, StageTrace, ToolResult


def _make_step(
    *,
    content: str = "test output",
    tokens_in: int = 100,
    tokens_out: int = 50,
    duration_ms: int = 500,
    tool_results: list[ToolResult] | None = None,
    success: bool = True,
) -> Step:
    return Step(
        stage_name="test_stage",
        observation={"input": "test"},
        action={"content": content},
        reward=0.0,
        stage_trace=StageTrace(
            stage_name="test_stage",
            duration_ms=duration_ms,
            llm_calls=1,
            tool_calls=len(tool_results or []),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tool_results=tool_results or [],
            success=success,
        ),
        terminal=True,
    )


class TestSchemaComplianceReward:
    def test_valid_output(self):
        schema = {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}
        reward = SchemaComplianceReward(schema)
        step = _make_step(content="hello")
        assert reward.score(step) == 1.0

    def test_invalid_output(self):
        schema = {"type": "object", "required": ["nonexistent_field"]}
        reward = SchemaComplianceReward(schema)
        step = _make_step()
        assert reward.score(step) == -1.0

    def test_custom_values(self):
        schema = {"type": "object", "required": ["content"]}
        reward = SchemaComplianceReward(schema, reward=5.0, penalty=-2.0)
        step = _make_step()
        assert reward.score(step) == 5.0

    def test_name(self):
        reward = SchemaComplianceReward({"type": "object"})
        assert reward.name == "schema_compliance"


class TestTokenEfficiencyReward:
    def test_basic(self):
        reward = TokenEfficiencyReward(budget=1000)
        step = _make_step(tokens_in=200, tokens_out=100)
        assert reward.score(step) == -0.3  # -(200+100)/1000

    def test_alpha(self):
        reward = TokenEfficiencyReward(budget=1000, alpha=2.0)
        step = _make_step(tokens_in=200, tokens_out=100)
        assert reward.score(step) == -0.6  # -2*(200+100)/1000

    def test_name(self):
        assert TokenEfficiencyReward(budget=1000).name == "token_efficiency"


class TestLatencyReward:
    def test_basic(self):
        reward = LatencyReward(target_ms=1000)
        step = _make_step(duration_ms=500)
        assert reward.score(step) == -0.25  # -0.5 * 500/1000

    def test_beta(self):
        reward = LatencyReward(target_ms=1000, beta=1.0)
        step = _make_step(duration_ms=500)
        assert reward.score(step) == -0.5  # -1.0 * 500/1000

    def test_name(self):
        assert LatencyReward(target_ms=1000).name == "latency"


class TestToolSuccessRateReward:
    def test_all_success(self):
        reward = ToolSuccessRateReward()
        step = _make_step(tool_results=[
            ToolResult("search", True, 100),
            ToolResult("calc", True, 50),
        ])
        assert reward.score(step) == 1.0

    def test_mixed(self):
        reward = ToolSuccessRateReward()
        step = _make_step(tool_results=[
            ToolResult("search", True, 100),
            ToolResult("calc", False, 50, error_type="timeout"),
        ])
        assert reward.score(step) == 0.5

    def test_no_tools(self):
        reward = ToolSuccessRateReward()
        step = _make_step(tool_results=[])
        assert reward.score(step) == 1.0

    def test_no_tools_custom_score(self):
        reward = ToolSuccessRateReward(no_tools_score=0.0)
        step = _make_step(tool_results=[])
        assert reward.score(step) == 0.0

    def test_name(self):
        assert ToolSuccessRateReward().name == "tool_success_rate"


class TestCustomReward:
    def test_basic(self):
        reward = CustomReward("len", lambda s: len(s.action.get("content", "")) / 100.0)
        step = _make_step(content="hello")
        assert reward.score(step) == 0.05

    def test_name(self):
        reward = CustomReward("my_reward", lambda s: 0.0)
        assert reward.name == "my_reward"


class TestCompositeReward:
    def test_sum(self):
        r1 = CustomReward("a", lambda s: 1.0)
        r2 = CustomReward("b", lambda s: 2.0)
        composite = CompositeReward(r1, r2)
        step = _make_step()
        assert composite.score(step) == 3.0

    def test_breakdown(self):
        r1 = CustomReward("a", lambda s: 1.0)
        r2 = CustomReward("b", lambda s: 2.0)
        composite = CompositeReward(r1, r2)
        step = _make_step()
        breakdown = composite.score_breakdown(step)
        assert breakdown == {"a": 1.0, "b": 2.0}

    def test_name(self):
        r1 = CustomReward("a", lambda s: 0)
        r2 = CustomReward("b", lambda s: 0)
        assert CompositeReward(r1, r2).name == "a+b"


class TestWeightedReward:
    def test_weighted(self):
        r1 = CustomReward("a", lambda s: 1.0)
        r2 = CustomReward("b", lambda s: 1.0)
        weighted = WeightedReward({"a": (r1, 2.0), "b": (r2, 0.5)})
        step = _make_step()
        assert weighted.score(step) == 2.5

    def test_breakdown(self):
        r1 = CustomReward("a", lambda s: 1.0)
        r2 = CustomReward("b", lambda s: 1.0)
        weighted = WeightedReward({"a": (r1, 2.0), "b": (r2, 0.5)})
        step = _make_step()
        breakdown = weighted.score_breakdown(step)
        assert breakdown == {"a": 2.0, "b": 0.5}

    def test_protocol_compliance(self):
        r = CustomReward("test", lambda s: 0)
        assert isinstance(r, RewardFn)
