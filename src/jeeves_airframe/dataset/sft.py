"""SftBuilder — build supervised finetuning datasets from trajectories.

Output format (TRL-compatible):
    {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
"""

from __future__ import annotations

from typing import Any, Iterable

from jeeves_airframe.trajectory.types import Step, Trajectory


class SftBuilder:
    """Build SFT datasets from pipeline trajectories.

    Extracts (system_prompt + context, model_completion) pairs from steps
    that meet the minimum reward threshold.

    Usage:
        sft = SftBuilder(min_reward=0.8, include_stages=["respond"])
        sft.add_trajectories(store.load())
        sft.export_jsonl("sft.jsonl")
    """

    def __init__(
        self,
        *,
        min_reward: float | None = None,
        include_stages: list[str] | None = None,
        system_prompt: str | None = None,
    ):
        self._min_reward = min_reward
        self._include_stages = set(include_stages) if include_stages else None
        self._system_prompt = system_prompt
        self._examples: list[dict[str, Any]] = []

    def add_trajectory(self, trajectory: Trajectory) -> int:
        """Add steps from a trajectory. Returns number of examples added."""
        added = 0
        for step in trajectory.steps:
            if not self._should_include(step):
                continue
            messages = self._build_messages(step, trajectory)
            self._examples.append({"messages": messages})
            added += 1
        return added

    def add_trajectories(self, trajectories: Iterable[Trajectory]) -> int:
        return sum(self.add_trajectory(t) for t in trajectories)

    def build(self) -> list[dict[str, Any]]:
        return list(self._examples)

    def export_jsonl(self, path: str) -> int:
        import json
        from pathlib import Path

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for ex in self._examples:
                f.write(json.dumps(ex) + "\n")
        return len(self._examples)

    def _should_include(self, step: Step) -> bool:
        if self._include_stages and step.stage_name not in self._include_stages:
            return False
        if self._min_reward is not None and step.reward < self._min_reward:
            return False
        return True

    def _build_messages(self, step: Step, trajectory: Trajectory) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        # User message: input + accumulated context from prior stages
        prior = step.observation.get("prior_outputs", {})
        context_parts = [f"Input: {trajectory.input}"]
        for stage_name, output in prior.items():
            content = output.get("content", "") if isinstance(output, dict) else str(output)
            if content:
                context_parts.append(f"[{stage_name}]: {content}")

        messages.append({"role": "user", "content": "\n\n".join(context_parts)})

        # Assistant message: what the model produced
        content = step.action.get("content", "")
        messages.append({"role": "assistant", "content": content})

        return messages

    def __len__(self) -> int:
        return len(self._examples)
