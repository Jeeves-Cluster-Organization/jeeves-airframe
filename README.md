# jeeves-airframe

Pipeline training data generator for [jeeves-core](https://github.com/Jeeves-Cluster-Organization/jeeves-core). Rust crate with PyO3 bindings.

Captures pipeline execution trajectories, scores them with composable reward functions, and exports SFT/DPO/GRPO datasets for SLM finetuning.

## Architecture

```
Pipeline runs (jeeves-core PipelineRunner)
  → TrajectoryCollector (Rust, typed mpsc::Receiver<PipelineEvent>)
    → RewardFn scoring (Rust trait, composable)
      → Dataset export (SFT / DPO / GRPO — serde JSONL)
        → Training (consumer's choice: TRL, SkyRL, etc.)
```

Airframe consumes `PipelineEvent` directly from jeeves-core — no JSON serialization roundtrip. The Python boundary exists only at the PyO3 edge.

## Rust Usage

```rust
use jeeves_core::prelude::PipelineRunner;
use jeeves_airframe::trajectory::TrajectoryCollector;
use jeeves_airframe::reward::TokenEfficiencyReward;
use jeeves_airframe::dataset::SftBuilder;

let runner = PipelineRunner::from_json("pipeline.json", "prompts/", None).await?;
let reward = Box::new(TokenEfficiencyReward::new(2000, 1.0));
let collector = TrajectoryCollector::new(Some(reward), false);
let trajectory = collector.collect(&runner, "hello", "user1").await?;

let mut sft = SftBuilder::new(Some(0.8), None, None);
sft.add_trajectory(&trajectory);
sft.export_jsonl(Path::new("sft.jsonl"))?;
```

## Python Usage

```python
from jeeves_core import PipelineRunner
from jeeves_airframe import TrajectoryCollector, TrajectoryStore, SftBuilder

runner = PipelineRunner.from_json("pipeline.json", "prompts/")
collector = TrajectoryCollector()
trajectory = collector.collect(runner, "hello")

store = TrajectoryStore("runs.jsonl")
store.save(trajectory)
```

## Modules

### `trajectory/` — Pipeline event capture

- **`TrajectoryCollector`** — Consumes typed `mpsc::Receiver<PipelineEvent>`, builds `Trajectory`
- **`TrajectoryStore`** — JSONL persistence via serde + BufWriter
- Types: `Trajectory`, `Step`, `StageTrace`, `StepAction`, `ToolEvent`
- Reuses jeeves-core types: `ToolCallResult`, `RoutingReason`, `StageMetrics`, `AggregateMetrics`

### `reward/` — Composable reward scoring

All implement the `RewardFn` trait. Combine with `CompositeReward` or `WeightedReward`.

| Reward | Signal |
|--------|--------|
| `SchemaComplianceReward` | Binary: output validates against JSON Schema |
| `TokenEfficiencyReward` | `-alpha * (tokens_in + tokens_out) / budget` |
| `LatencyReward` | `-beta * duration_ms / target_ms` |
| `ToolSuccessRateReward` | `successful_tools / total_tools` |
| `CallableRewardFn` | Wraps any `Fn(&Step) -> f64` |

### `dataset/` — Training dataset export

| Builder | Format | Use Case |
|---------|--------|----------|
| `SftBuilder` | `{"messages": [...]}` | Supervised finetuning |
| `DpoBuilder` | `{"prompt", "chosen", "rejected"}` | Preference learning |
| `GrpoBuilder` | `{"prompt", "completions", "rewards"}` | Group relative policy optimization |

### `eval/` — Model comparison

- **`EvalHarness`** — Run pipeline against eval dataset, collect per-stage metrics
- **`ModelComparison`** — Baseline vs candidate: reward delta, win rate

## Build

```bash
# Rust library
cargo test                          # 30 tests
cargo clippy --all-features         # Lint

# Python module (PyO3)
pip install -e .                    # Build via maturin
python -c "from jeeves_airframe import TrajectoryCollector"
```

## Feature Flags

| Feature | Dependencies | Purpose |
|---------|-------------|---------|
| `py-bindings` | pyo3 | Python importable module |

Default: none. `cargo test` uses rlib only. `pip install -e .` activates `py-bindings`.

## License

Apache-2.0 — see [LICENSE](LICENSE).
