# jeeves-airframe

Pipeline training data generator for [jeeves-core](https://github.com/Jeeves-Cluster-Organization/jeeves-core).

Captures pipeline execution trajectories, scores them with composable reward functions, and exports SFT/DPO/GRPO datasets for SLM finetuning.

## Architecture

```
Pipeline runs (jeeves-core, strong LLMs)
  → Trajectory collection (airframe)
    → Reward scoring (airframe)
      → Dataset export (SFT / DPO / GRPO)
        → Training (consumer's choice: TRL, SkyRL, etc.)
```

This package is a **data generator**, not a training framework. It owns capture and formatting — consumers own model training.

## Installation

```bash
pip install -e "."          # Core
pip install -e ".[dev]"     # + pytest, ruff
pip install -e ".[hf]"     # + HuggingFace datasets export
```

## Quick Start

```python
from jeeves_core import PipelineRunner
from jeeves_airframe.trajectory import TrajectoryCollector, TrajectoryStore
from jeeves_airframe.reward import WeightedReward, SchemaComplianceReward, TokenEfficiencyReward
from jeeves_airframe.dataset import SftBuilder

# 1. Collect trajectories from pipeline runs
runner = PipelineRunner.from_json("pipeline.json", prompts_dir="prompts/")
collector = TrajectoryCollector(reward_fn=WeightedReward({
    "schema": (SchemaComplianceReward({"type": "object", "required": ["intent"]}), 2.0),
    "efficiency": (TokenEfficiencyReward(budget=2000), 0.5),
}))

trajectory = collector.collect(runner, "Hello, can you help me?")

# 2. Persist
store = TrajectoryStore("trajectories/runs.jsonl")
store.save(trajectory)

# 3. Build SFT dataset from high-quality runs
sft = SftBuilder(min_reward=0.8, include_stages=["respond"])
sft.add_trajectories(store.load())
sft.export_jsonl("datasets/sft.jsonl")
```

## Modules

### `trajectory/` — Pipeline event capture

- **`TrajectoryCollector`** — Consumes `PipelineRunner.stream()`, builds structured `Trajectory` objects with per-stage `Step` and `StageTrace` data
- **`TrajectoryStore`** — Append-only JSONL persistence with filtered loading
- Types: `Trajectory`, `Step`, `StageTrace`, `ToolResult`, `RoutingDecision` (all frozen dataclasses with immutable containers)

### `reward/` — Composable reward scoring

All implement the `RewardFn` protocol. Combine with `CompositeReward` (sum) or `WeightedReward` (weighted + breakdown).

| Reward | Signal |
|--------|--------|
| `SchemaComplianceReward` | Binary: output validates against JSON Schema |
| `TokenEfficiencyReward` | `-alpha * (tokens_in + tokens_out) / budget` |
| `LatencyReward` | `-beta * duration_ms / target_ms` |
| `ToolSuccessRateReward` | `successful_tools / total_tools` |
| `CustomReward` | Wraps any `Callable[[Step], float]` |

### `dataset/` — Training dataset export

| Builder | Format | Use Case |
|---------|--------|----------|
| `SftBuilder` | `{"messages": [...]}` | Supervised finetuning from good trajectories |
| `DpoBuilder` | `{"prompt": ..., "chosen": ..., "rejected": ...}` | Preference learning from trajectory pairs |
| `GrpoBuilder` | `{"prompt": ..., "completions": [...], "rewards": [...]}` | Group relative policy optimization |

All export JSONL. Optional Parquet and HuggingFace `datasets` export via `jeeves_airframe.dataset.export`.

### `eval/` — Model comparison

- **`EvalHarness`** — Run a pipeline against an eval dataset, collect per-stage metrics and reward stats
- **`ModelComparison`** — Baseline vs candidate: reward delta, win rate, per-stage metric diff

## jeeves-core API Surface

Airframe consumes only the existing Python API — no kernel changes required:

| API | Used By |
|-----|---------|
| `runner.stream(input)` | `TrajectoryCollector` |
| `runner.run(input)` | `EvalHarness` |
| `runner.describe_pipeline()` | Observation context |
| `PipelineRunner.get_schema()` | `SchemaComplianceReward` |

## Testing

```bash
pytest tests/ -v    # 71 tests
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
