//! DpoBuilder — preference datasets from trajectory groups.
//!
//! Output: `{"prompt": [{"role": "user", ...}], "chosen": "...", "rejected": "..."}`

use std::path::Path;

use serde::Serialize;

use crate::reward::RewardFn;
use crate::trajectory::Trajectory;

/// Build DPO preference datasets from trajectory groups.
#[derive(Debug)]
pub struct DpoBuilder {
    reward_fn: Option<Box<dyn RewardFn>>,
    margin: f64,
    target_stage: Option<String>,
    pairs: Vec<DpoPair>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DpoPair {
    pub prompt: Vec<serde_json::Value>,
    pub chosen: String,
    pub rejected: String,
}

impl DpoBuilder {
    pub fn new(
        reward_fn: Option<Box<dyn RewardFn>>,
        margin: f64,
        target_stage: Option<String>,
    ) -> Self {
        Self {
            reward_fn,
            margin,
            target_stage,
            pairs: Vec::new(),
        }
    }

    pub fn add_trajectory_group(&mut self, trajectories: &[Trajectory]) -> usize {
        if trajectories.len() < 2 {
            return 0;
        }

        let mut scored: Vec<(&Trajectory, f64)> = trajectories
            .iter()
            .map(|t| {
                let score = if let Some(ref rf) = self.reward_fn {
                    t.steps.iter().map(|s| rf.score(s)).sum()
                } else {
                    t.total_reward()
                };
                (t, score)
            })
            .collect();

        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let (best, best_score) = scored[0];
        let (worst, worst_score) = scored[scored.len() - 1];

        if best_score - worst_score < self.margin {
            return 0;
        }

        if let Some(pair) = self.build_pair(best, worst) {
            self.pairs.push(pair);
            return 1;
        }
        0
    }

    pub fn build(&self) -> &[DpoPair] {
        &self.pairs
    }

    pub fn len(&self) -> usize {
        self.pairs.len()
    }

    pub fn is_empty(&self) -> bool {
        self.pairs.is_empty()
    }

    pub fn export_jsonl(&self, path: &Path) -> std::io::Result<usize> {
        super::export_jsonl(&self.pairs, path)
    }

    fn get_target_step<'a>(&self, trajectory: &'a Trajectory) -> Option<&'a crate::trajectory::Step> {
        if let Some(ref stage) = self.target_stage {
            trajectory.step_for_stage(stage)
        } else {
            trajectory.steps.last()
        }
    }

    fn build_pair(&self, chosen: &Trajectory, rejected: &Trajectory) -> Option<DpoPair> {
        let chosen_step = self.get_target_step(chosen)?;
        let rejected_step = self.get_target_step(rejected)?;

        let mut context_parts = vec![format!("Input: {}", chosen.input)];
        if let Some(prior) = chosen_step.observation.get("prior_outputs").and_then(|v| v.as_object()) {
            for (stage_name, output) in prior {
                let content = output.get("content").and_then(|v| v.as_str()).unwrap_or("");
                if !content.is_empty() {
                    context_parts.push(format!("[{stage_name}]: {content}"));
                }
            }
        }

        let prompt = vec![serde_json::json!({"role": "user", "content": context_parts.join("\n\n")})];

        Some(DpoPair {
            prompt,
            chosen: chosen_step.action.content.clone(),
            rejected: rejected_step.action.content.clone(),
        })
    }
}
