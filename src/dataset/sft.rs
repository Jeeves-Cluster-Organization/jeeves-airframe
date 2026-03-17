//! SftBuilder — supervised finetuning datasets from trajectories.
//!
//! Output: `{"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}`

use std::collections::HashSet;
use std::path::Path;

use serde::Serialize;

use crate::trajectory::{Step, Trajectory};

/// Build SFT datasets from pipeline trajectories.
#[derive(Debug)]
pub struct SftBuilder {
    min_reward: Option<f64>,
    include_stages: Option<HashSet<String>>,
    system_prompt: Option<String>,
    examples: Vec<SftExample>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SftExample {
    pub messages: Vec<Message>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Message {
    pub role: String,
    pub content: String,
}

impl SftBuilder {
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

    pub fn add_trajectory(&mut self, trajectory: &Trajectory) -> usize {
        let mut added = 0;
        for step in &trajectory.steps {
            if !self.should_include(step) {
                continue;
            }
            let messages = self.build_messages(step, trajectory);
            self.examples.push(SftExample { messages });
            added += 1;
        }
        added
    }

    pub fn add_trajectories(&mut self, trajectories: &[Trajectory]) -> usize {
        trajectories.iter().map(|t| self.add_trajectory(t)).sum()
    }

    pub fn build(&self) -> &[SftExample] {
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

    fn build_messages(&self, step: &Step, trajectory: &Trajectory) -> Vec<Message> {
        let mut messages = Vec::new();

        if let Some(ref sys) = self.system_prompt {
            messages.push(Message {
                role: "system".into(),
                content: sys.clone(),
            });
        }

        // User message: input + prior stage outputs
        let mut context_parts = vec![format!("Input: {}", trajectory.input)];
        if let Some(prior) = step.observation.get("prior_outputs").and_then(|v| v.as_object()) {
            for (stage_name, output) in prior {
                let content = output
                    .get("content")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                if !content.is_empty() {
                    context_parts.push(format!("[{stage_name}]: {content}"));
                }
            }
        }
        messages.push(Message {
            role: "user".into(),
            content: context_parts.join("\n\n"),
        });

        // Assistant message
        messages.push(Message {
            role: "assistant".into(),
            content: step.action.content.clone(),
        });

        messages
    }
}
