//! GrpoBuilder — group relative policy optimization datasets.
//!
//! Output format:
//! ```json
//! {"prompt": [{"role": "user", ...}], "completions": [...], "rewards": [...]}
//! ```

use std::path::Path;

use serde::Serialize;

use crate::reward::RewardFn;
use crate::trajectory::{build_context, resolve_target_step, Trajectory};

/// GRPO dataset builder.
///
/// Each trajectory group (same input, multiple runs) produces one example
/// with multiple completions and rewards for relative ranking.
#[derive(Debug)]
pub struct GrpoBuilder {
    reward_fn: Option<Box<dyn RewardFn>>,
    group_size: Option<usize>,
    target_stage: Option<String>,
    examples: Vec<GrpoExample>,
}

/// Single GRPO training example with grouped completions.
#[derive(Debug, Clone, Serialize)]
pub struct GrpoExample {
    pub prompt: Vec<serde_json::Value>,
    pub completions: Vec<String>,
    pub rewards: Vec<f64>,
}

impl GrpoBuilder {
    /// Create a new GRPO dataset builder.
    ///
    /// - `reward_fn`: Reward function (None = use pre-computed step rewards).
    /// - `group_size`: Max completions per prompt (None = use all).
    /// - `target_stage`: Stage to extract completions from (None = last stage).
    pub fn new(
        reward_fn: Option<Box<dyn RewardFn>>,
        group_size: Option<usize>,
        target_stage: Option<String>,
    ) -> Self {
        Self { reward_fn, group_size, target_stage, examples: Vec::new() }
    }

    /// Add a group of trajectories for the same input. Returns 1 if example added, 0 otherwise.
    pub fn add_trajectory_group(&mut self, trajectories: &[Trajectory]) -> usize {
        if trajectories.is_empty() {
            return 0;
        }

        let group = match self.group_size {
            Some(size) => &trajectories[..trajectories.len().min(size)],
            None => trajectories,
        };

        let target = self.target_stage.as_deref();
        let mut completions = Vec::new();
        let mut rewards = Vec::new();

        for t in group {
            let Some(step) = resolve_target_step(t, target) else { continue };
            completions.push(step.action.content.clone());
            rewards.push(match &self.reward_fn {
                Some(rf) => rf.score(step),
                None => step.reward,
            });
        }

        if completions.len() < 2 {
            return 0;
        }

        let first_step = resolve_target_step(&group[0], target);
        let prompt = match first_step {
            Some(step) => vec![serde_json::json!({"role": "user", "content": build_context(&group[0], step)})],
            None => vec![serde_json::json!({"role": "user", "content": group[0].input})],
        };

        self.examples.push(GrpoExample { prompt, completions, rewards });
        1
    }

    /// Get the built examples.
    pub fn build(&self) -> &[GrpoExample] {
        &self.examples
    }

    /// Number of examples collected.
    pub fn len(&self) -> usize {
        self.examples.len()
    }

    /// Whether no examples have been collected.
    pub fn is_empty(&self) -> bool {
        self.examples.is_empty()
    }

    /// Export examples as JSONL. Returns count written.
    pub fn export_jsonl(&self, path: &Path) -> std::io::Result<usize> {
        super::export_jsonl(&self.examples, path)
    }
}
