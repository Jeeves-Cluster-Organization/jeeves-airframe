//! DpoBuilder — preference datasets from trajectory groups.
//!
//! Output format (TRL-compatible):
//! ```json
//! {"prompt": [{"role": "user", ...}], "chosen": "...", "rejected": "..."}
//! ```

use std::path::Path;

use serde::Serialize;

use crate::reward::RewardFn;
use crate::trajectory::{build_context, resolve_target_step, Trajectory};

/// DPO preference dataset builder.
///
/// For each trajectory group (same input, multiple runs), pairs the
/// highest-reward trajectory (chosen) with the lowest (rejected).
#[derive(Debug)]
pub struct DpoBuilder {
    reward_fn: Option<Box<dyn RewardFn>>,
    margin: f64,
    target_stage: Option<String>,
    pairs: Vec<DpoPair>,
}

/// Single DPO preference pair.
#[derive(Debug, Clone, Serialize)]
pub struct DpoPair {
    pub prompt: Vec<serde_json::Value>,
    pub chosen: String,
    pub rejected: String,
}

impl DpoBuilder {
    /// Create a new DPO dataset builder.
    ///
    /// - `reward_fn`: Reward function for scoring (None = use pre-computed step rewards).
    /// - `margin`: Minimum reward gap between chosen and rejected.
    /// - `target_stage`: Stage to extract completions from (None = last stage).
    pub fn new(
        reward_fn: Option<Box<dyn RewardFn>>,
        margin: f64,
        target_stage: Option<String>,
    ) -> Self {
        Self { reward_fn, margin, target_stage, pairs: Vec::new() }
    }

    /// Add a group of trajectories for the same input. Returns pairs added (0 or 1).
    pub fn add_trajectory_group(&mut self, trajectories: &[Trajectory]) -> usize {
        if trajectories.len() < 2 {
            return 0;
        }

        let mut scored: Vec<_> = trajectories.iter().map(|t| (t, self.score(t))).collect();
        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let (best, best_score) = scored[0];
        let (worst, worst_score) = scored[scored.len() - 1];

        if best_score - worst_score < self.margin {
            return 0;
        }

        let target = self.target_stage.as_deref();
        let Some(chosen_step) = resolve_target_step(best, target) else { return 0 };
        let Some(rejected_step) = resolve_target_step(worst, target) else { return 0 };

        let prompt = vec![serde_json::json!({"role": "user", "content": build_context(best, chosen_step)})];
        self.pairs.push(DpoPair {
            prompt,
            chosen: chosen_step.action.content.clone(),
            rejected: rejected_step.action.content.clone(),
        });
        1
    }

    /// Get the built pairs.
    pub fn build(&self) -> &[DpoPair] {
        &self.pairs
    }

    /// Number of pairs collected.
    pub fn len(&self) -> usize {
        self.pairs.len()
    }

    /// Whether no pairs have been collected.
    pub fn is_empty(&self) -> bool {
        self.pairs.is_empty()
    }

    /// Export pairs as JSONL. Returns count written.
    pub fn export_jsonl(&self, path: &Path) -> std::io::Result<usize> {
        super::export_jsonl(&self.pairs, path)
    }

    fn score(&self, trajectory: &Trajectory) -> f64 {
        match &self.reward_fn {
            Some(rf) => trajectory.steps.iter().map(|s| rf.score(s)).sum(),
            None => trajectory.total_reward(),
        }
    }
}
