//! GrpoBuilder — group relative policy optimization datasets.
//!
//! Output: `{"prompt": [{"role": "user", ...}], "completions": [...], "rewards": [...]}`

use std::path::Path;

use serde::Serialize;

use crate::reward::RewardFn;
use crate::trajectory::Trajectory;

/// Build GRPO datasets from trajectory groups.
#[derive(Debug)]
pub struct GrpoBuilder {
    reward_fn: Option<Box<dyn RewardFn>>,
    group_size: Option<usize>,
    target_stage: Option<String>,
    examples: Vec<GrpoExample>,
}

#[derive(Debug, Clone, Serialize)]
pub struct GrpoExample {
    pub prompt: Vec<serde_json::Value>,
    pub completions: Vec<String>,
    pub rewards: Vec<f64>,
}

impl GrpoBuilder {
    pub fn new(
        reward_fn: Option<Box<dyn RewardFn>>,
        group_size: Option<usize>,
        target_stage: Option<String>,
    ) -> Self {
        Self {
            reward_fn,
            group_size,
            target_stage,
            examples: Vec::new(),
        }
    }

    pub fn add_trajectory_group(&mut self, trajectories: &[Trajectory]) -> usize {
        if trajectories.is_empty() {
            return 0;
        }

        let group = if let Some(size) = self.group_size {
            &trajectories[..trajectories.len().min(size)]
        } else {
            trajectories
        };

        let mut completions = Vec::new();
        let mut rewards = Vec::new();

        for t in group {
            let step = self.get_target_step(t);
            let Some(step) = step else { continue };
            completions.push(step.action.content.clone());
            if let Some(ref rf) = self.reward_fn {
                rewards.push(rf.score(step));
            } else {
                rewards.push(step.reward);
            }
        }

        if completions.len() < 2 {
            return 0;
        }

        let first_step = self.get_target_step(&group[0]);
        let prompt = self.build_prompt(&group[0], first_step);

        self.examples.push(GrpoExample {
            prompt,
            completions,
            rewards,
        });
        1
    }

    pub fn build(&self) -> &[GrpoExample] {
        &self.examples
    }

    pub fn len(&self) -> usize {
        self.examples.len()
    }

    pub fn is_empty(&self) -> bool {
        self.examples.is_empty()
    }

    pub fn export_jsonl(&self, path: &Path) -> std::io::Result<usize> {
        super::export_jsonl(&self.examples, path)
    }

    fn get_target_step<'a>(&self, trajectory: &'a Trajectory) -> Option<&'a crate::trajectory::Step> {
        if let Some(ref stage) = self.target_stage {
            trajectory.step_for_stage(stage)
        } else {
            trajectory.steps.last()
        }
    }

    fn build_prompt(
        &self,
        trajectory: &Trajectory,
        step: Option<&crate::trajectory::Step>,
    ) -> Vec<serde_json::Value> {
        let Some(step) = step else {
            return vec![serde_json::json!({"role": "user", "content": trajectory.input})];
        };

        let mut context_parts = vec![format!("Input: {}", trajectory.input)];
        if let Some(prior) = step.observation.get("prior_outputs").and_then(|v| v.as_object()) {
            for (stage_name, output) in prior {
                let content = output.get("content").and_then(|v| v.as_str()).unwrap_or("");
                if !content.is_empty() {
                    context_parts.push(format!("[{stage_name}]: {content}"));
                }
            }
        }

        vec![serde_json::json!({"role": "user", "content": context_parts.join("\n\n")})]
    }
}
