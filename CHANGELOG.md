# Changelog

## 0.0.2 — 2026-03-17

Complete rewrite: Rust crate with PyO3 bindings (matching jeeves-core's architecture).

### Changed
- **Rewritten in Rust** — all modules now Rust with typed PipelineEvent consumption
- Types reuse jeeves-core directly: `ToolCallResult`, `RoutingReason`, `StageMetrics`, `AggregateMetrics`
- `TrajectoryCollector` consumes `mpsc::Receiver<PipelineEvent>` — zero JSON serialization
- PyO3 bindings behind `py-bindings` feature flag (same pattern as jeeves-core)
- Build via maturin: `pip install -e .`

### Added
- `trajectory/` — `TrajectoryCollector`, `TrajectoryStore`, typed `Trajectory`/`Step`/`StageTrace`
- `reward/` — `RewardFn` trait, `CompositeReward`, `WeightedReward`, built-in rewards
- `dataset/` — `SftBuilder`, `DpoBuilder`, `GrpoBuilder` with JSONL export
- `eval/` — `EvalHarness`, `EvalResult`, `ModelComparison`
- `python/` — PyO3 module with `PyRewardFn` bridge (Python callable → Rust trait)
- 30 Rust integration tests + 1 doc-test

### Removed
- Previous Python implementation (replaced by Rust)
