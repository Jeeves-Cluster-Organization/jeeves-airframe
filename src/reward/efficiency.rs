//! Efficiency-based reward functions.

use crate::reward::RewardFn;
use crate::trajectory::Step;

/// Penalizes token usage: reward = -alpha * (tokens_in + tokens_out) / budget.
#[derive(Debug)]
pub struct TokenEfficiencyReward {
    budget: f64,
    alpha: f64,
}

impl TokenEfficiencyReward {
    pub fn new(budget: i64, alpha: f64) -> Self {
        Self {
            budget: budget as f64,
            alpha,
        }
    }
}

impl RewardFn for TokenEfficiencyReward {
    fn name(&self) -> &str {
        "token_efficiency"
    }

    fn score(&self, step: &Step) -> f64 {
        let total = (step.stage_trace.tokens_in + step.stage_trace.tokens_out) as f64;
        -self.alpha * total / self.budget
    }
}

/// Penalizes latency: reward = -beta * duration_ms / target_ms.
#[derive(Debug)]
pub struct LatencyReward {
    target_ms: f64,
    beta: f64,
}

impl LatencyReward {
    pub fn new(target_ms: i64, beta: f64) -> Self {
        Self {
            target_ms: target_ms as f64,
            beta,
        }
    }
}

impl RewardFn for LatencyReward {
    fn name(&self) -> &str {
        "latency"
    }

    fn score(&self, step: &Step) -> f64 {
        -self.beta * step.stage_trace.duration_ms as f64 / self.target_ms
    }
}
