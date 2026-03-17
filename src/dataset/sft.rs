//! SftBuilder — supervised finetuning datasets from trajectories.
//!
//! Output format (TRL-compatible):
//! ```json
//! {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
//! ```

use std::collections::HashSet;
use std::path::Path;

use serde::Serialize;

use crate::trajectory::{build_context, Step, Trajectory};

/// Supervised finetuning dataset builder.
///
/// Extracts (system_prompt + context, model_completion) message pairs
/// from trajectory steps that meet the minimum reward threshold.
#[derive(Debug)]
pub struct SftBuilder {
    min_reward: Option<f64>,
    include_stages: Option<HashSet<String>>,
    system_prompt: Option<String>,
    examples: Vec<SftExample>,
}

/// Single SFT training example with conversation history.
#[derive(Debug, Clone, Serialize)]
pub struct SftExample {
    pub messages: Vec<Message>,
}

/// Chat message with role and content.
#[derive(Debug, Clone, Serialize)]
pub struct Message {
    pub role: String,
    pub content: String,
}

impl SftBuilder {
    /// Create a new SFT dataset builder.
    ///
    /// - `min_reward`: Only include steps scoring at or above this threshold.
    /// - `include_stages`: Filter to specific stage names (None = all stages).
    /// - `system_prompt`: Optional system message prepended to every example.
    pub fn new(
        min_reward: Option<f64>,
        include_stages: Option<Vec<String>>,
        system_prompt: Option<String>,
    ) -> Self {
        Self {
            min_reward,
            include_stages: include_stages.map(|v| v.into_iter().collect()),
            system_prompt,
            examples: Vec::new(),
        }
    }

    /// Add steps from a trajectory. Returns the number of examples added.
    pub fn add_trajectory(&mut self, trajectory: &Trajectory) -> usize {
        let mut added = 0;
        for step in &trajectory.steps {
            if !self.should_include(step) {
                continue;
            }
            let mut messages = Vec::new();
            if let Some(ref sys) = self.system_prompt {
                messages.push(Message { role: "system".into(), content: sys.clone() });
            }
            messages.push(Message { role: "user".into(), content: build_context(trajectory, step) });
            messages.push(Message { role: "assistant".into(), content: step.action.content.clone() });
            self.examples.push(SftExample { messages });
            added += 1;
        }
        added
    }

    /// Add steps from multiple trajectories. Returns total examples added.
    pub fn add_trajectories(&mut self, trajectories: &[Trajectory]) -> usize {
        trajectories.iter().map(|t| self.add_trajectory(t)).sum()
    }

    /// Get the built examples.
    pub fn build(&self) -> &[SftExample] {
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

    fn should_include(&self, step: &Step) -> bool {
        if let Some(ref stages) = self.include_stages {
            if !stages.contains(&step.stage_name) {
                return false;
            }
        }
        if let Some(min) = self.min_reward {
            if step.reward < min {
                return false;
            }
        }
        true
    }
}
