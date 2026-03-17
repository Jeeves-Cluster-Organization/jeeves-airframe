//! ToolSuccessRateReward — fraction of successful tool calls.

use crate::reward::RewardFn;
use crate::trajectory::Step;

/// Scores the fraction of successful tool calls.
#[derive(Debug)]
pub struct ToolSuccessRateReward {
    no_tools_score: f64,
}

impl ToolSuccessRateReward {
    pub fn new(no_tools_score: f64) -> Self {
        Self { no_tools_score }
    }
}

impl RewardFn for ToolSuccessRateReward {
    fn name(&self) -> &str {
        "tool_success_rate"
    }

    fn score(&self, step: &Step) -> f64 {
        let results = &step.stage_trace.tool_results;
        if results.is_empty() {
            return self.no_tools_score;
        }
        let successes = results.iter().filter(|r| r.success).count() as f64;
        successes / results.len() as f64
    }
}
