//! Composable reward functions for scoring pipeline steps.

pub mod custom;
pub mod efficiency;
pub mod schema;
pub mod tool_success;

use crate::trajectory::Step;

pub use custom::CallableRewardFn;
pub use efficiency::{LatencyReward, TokenEfficiencyReward};
pub use schema::SchemaComplianceReward;
pub use tool_success::ToolSuccessRateReward;

/// Trait for scoring a pipeline step. All reward functions implement this.
pub trait RewardFn: Send + Sync + std::fmt::Debug {
    fn name(&self) -> &str;
    fn score(&self, step: &Step) -> f64;
}

/// Sum of multiple reward functions.
#[derive(Debug)]
pub struct CompositeReward {
    fns: Vec<Box<dyn RewardFn>>,
}

impl CompositeReward {
    pub fn new(fns: Vec<Box<dyn RewardFn>>) -> Self {
        Self { fns }
    }

    pub fn score_breakdown(&self, step: &Step) -> Vec<(&str, f64)> {
        self.fns.iter().map(|f| (f.name(), f.score(step))).collect()
    }
}

impl RewardFn for CompositeReward {
    fn name(&self) -> &str {
        "composite"
    }

    fn score(&self, step: &Step) -> f64 {
        self.fns.iter().map(|f| f.score(step)).sum()
    }
}

/// Weighted combination of reward functions.
#[derive(Debug)]
pub struct WeightedReward {
    weights: Vec<(String, Box<dyn RewardFn>, f64)>,
}

impl WeightedReward {
    pub fn new(weights: Vec<(String, Box<dyn RewardFn>, f64)>) -> Self {
        Self { weights }
    }

    pub fn score_breakdown(&self, step: &Step) -> Vec<(&str, f64)> {
        self.weights
            .iter()
            .map(|(name, f, w)| (name.as_str(), f.score(step) * w))
            .collect()
    }
}

impl RewardFn for WeightedReward {
    fn name(&self) -> &str {
        "weighted"
    }

    fn score(&self, step: &Step) -> f64 {
        self.weights.iter().map(|(_, f, w)| f.score(step) * w).sum()
    }
}
