# Changelog

## 0.0.2 — 2026-03-17

Complete rewrite. Replaced jeeves-infra (Python gateway/orchestration layer, superseded by Rust kernel) with jeeves-airframe (pipeline training data generator).

### Added
- `trajectory/` — `TrajectoryCollector`, `TrajectoryStore`, frozen dataclass types (`Trajectory`, `Step`, `StageTrace`, `ToolResult`, `RoutingDecision`)
- `reward/` — `RewardFn` protocol, `CompositeReward`, `WeightedReward`, built-in rewards: `SchemaComplianceReward`, `TokenEfficiencyReward`, `LatencyReward`, `ToolSuccessRateReward`, `CustomReward`
- `dataset/` — `SftBuilder`, `DpoBuilder`, `GrpoBuilder` with JSONL export, optional Parquet/HF
- `eval/` — `EvalHarness`, `EvalResult`, `EvalDataset`, `ModelComparison`
- 71 tests covering all modules

### Removed
- Entire jeeves-infra package (gateway, LLM providers, database, redis, middleware, etc.)
