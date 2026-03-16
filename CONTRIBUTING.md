# Contributing to jeeves-airframe

## Scope

jeeves-airframe is a **pipeline training data generator**. It captures trajectories from jeeves-core pipeline runs and exports datasets for SLM finetuning.

### airframe MUST own

| Domain | Description |
|--------|-------------|
| **Trajectory capture** | Consuming `PipelineRunner.stream()`, structuring events into `Trajectory` objects |
| **Reward scoring** | Composable `RewardFn` implementations that score pipeline steps |
| **Dataset building** | SFT, DPO, GRPO format conversion and export |
| **Eval harness** | Running pipelines against eval sets, comparing model versions |

### airframe MUST NOT own

| Concern | Belongs To |
|---------|------------|
| Pipeline execution, orchestration, routing | jeeves-core |
| LLM provider implementation | jeeves-core |
| Tool execution | jeeves-core |
| Model training (torch, transformers, RL loops) | Consumer |
| SkyRL/TRL integration wrappers | Consumer (v1), possibly airframe v2 |
| Live training environments | Deferred to v2 |

## Development Setup

```bash
git clone https://github.com/Jeeves-Cluster-Organization/jeeves-airframe.git
cd jeeves-airframe
pip install -e ".[dev]"
pytest tests/ -v
```

## Code Standards

- **Python 3.11+** — use `X | Y` union syntax, not `Union[X, Y]`
- **Frozen dataclasses** with immutable containers (`tuple`, not `list`) for all value types
- **`RewardFn` protocol** — all reward functions must implement `name` property and `score(step)` method
- **Safe event parsing** — always use `.get()` with defaults when reading PipelineEvent dicts
- **No kernel changes** — airframe consumes only the existing jeeves-core Python API
- **No training deps** — core package must not depend on torch, transformers, skyrl, or any GPU library
- **Type hints** on all public methods, including return types

## Testing

```bash
pytest tests/ -v              # All tests
pytest tests/test_reward.py   # Single module
```

Tests use `MockRunner` from `tests/_helpers.py` to simulate pipeline event streams without requiring jeeves-core.

## Making Changes

1. Create a branch from `main`
2. Write tests first — use `_helpers.MockRunner` for pipeline simulation
3. Implement the feature
4. Ensure `pytest tests/ -v` passes (all 71+ tests)
5. Open a PR against `main`
