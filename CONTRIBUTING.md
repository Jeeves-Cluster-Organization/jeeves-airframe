# Contributing to jeeves-airframe

## Scope

jeeves-airframe is a **pipeline training data generator** — a Rust crate with PyO3 bindings.

### airframe MUST own

| Domain | Description |
|--------|-------------|
| **Trajectory capture** | Consuming typed `PipelineEvent` stream, building `Trajectory` objects |
| **Reward scoring** | `RewardFn` trait and built-in implementations |
| **Dataset building** | SFT, DPO, GRPO format conversion and JSONL export |
| **Eval harness** | Running pipelines against eval datasets, comparing model versions |
| **PyO3 bindings** | Python-facing wrappers (`py-bindings` feature) |

### airframe MUST NOT own

| Concern | Belongs To |
|---------|------------|
| Pipeline execution, orchestration, routing | jeeves-core |
| LLM provider implementation | jeeves-core |
| Tool execution | jeeves-core |
| `PipelineRunner` facade | jeeves-core (`worker/runner.rs`) |
| Model training (torch, transformers, RL loops) | Consumer |
| Live training environments (skyrl-gym) | Deferred to v2 |

## Architecture Principles (inherited from jeeves-core)

- **`#![deny(unsafe_code)]`** — no unsafe except where PyO3 requires it (gated behind `py-bindings`)
- **Types over dicts** — Rust structs with `Serialize`/`Deserialize`, not `serde_json::Value` bags
- **Reuse kernel types** — `use jeeves_core::...` for `ToolCallResult`, `RoutingReason`, `StageMetrics`, etc.
- **`RewardFn` is a trait** — same pattern as jeeves-core's `ToolExecutor` trait
- **PyO3 bridge follows `PyToolExecutor` pattern** — `Python::with_gil()` per-call, JSON at boundary only
- **Feature-gated PyO3** — `#[cfg(feature = "py-bindings")]` keeps the rlib clean for Rust consumers

## Development

```bash
cargo test                          # 30 integration tests
cargo clippy --all-features         # Lint (including py-bindings)
cargo check                         # rlib only (no PyO3)
cargo check --all-features          # With PyO3

# Python
pip install -e .                    # Build via maturin
python -c "from jeeves_airframe import TrajectoryCollector"
```

## Making Changes

1. Create a branch from `main`
2. Write Rust tests in `tests/test_all.rs`
3. Implement the feature
4. `cargo test` + `cargo clippy --all-features` clean
5. Open a PR against `main`
