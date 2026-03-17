//! ModelComparison — compare baseline vs candidate EvalResults.

use std::collections::{HashMap, HashSet};

use serde::Serialize;

use crate::eval::harness::EvalResult;

/// Side-by-side comparison of baseline vs candidate EvalResults.
///
/// Reports reward delta, win rate, tie rate, and per-stage metric deltas.
#[derive(Debug, Serialize)]
pub struct ModelComparison {
    pub baseline_mean_reward: f64,
    pub candidate_mean_reward: f64,
    pub reward_delta: f64,
    pub win_rate: f64,
    pub tie_rate: f64,
    pub num_compared: usize,
    pub per_stage_delta: HashMap<String, HashMap<String, f64>>,
}

impl ModelComparison {
    pub fn compare(baseline: &EvalResult, candidate: &EvalResult) -> Self {
        let b_rewards: Vec<f64> = baseline.trajectories.iter().map(|t| t.total_reward()).collect();
        let c_rewards: Vec<f64> = candidate.trajectories.iter().map(|t| t.total_reward()).collect();

        let total = b_rewards.len().min(c_rewards.len());
        let wins = b_rewards
            .iter()
            .zip(c_rewards.iter())
            .filter(|(b, c)| c > b)
            .count();
        let ties = b_rewards
            .iter()
            .zip(c_rewards.iter())
            .filter(|(b, c)| (**c - **b).abs() < f64::EPSILON)
            .count();

        // Per-stage deltas
        let all_stages: HashSet<&String> = baseline
            .per_stage_metrics
            .keys()
            .chain(candidate.per_stage_metrics.keys())
            .collect();

        let mut per_stage_delta = HashMap::new();
        for stage in all_stages {
            let b_metrics = baseline.per_stage_metrics.get(stage.as_str());
            let c_metrics = candidate.per_stage_metrics.get(stage.as_str());

            let all_keys: HashSet<&String> = b_metrics
                .into_iter()
                .flat_map(|m| m.keys())
                .chain(c_metrics.into_iter().flat_map(|m| m.keys()))
                .collect();

            let deltas: HashMap<String, f64> = all_keys
                .into_iter()
                .map(|k| {
                    let b_val = b_metrics.and_then(|m| m.get(k.as_str())).copied().unwrap_or(0.0);
                    let c_val = c_metrics.and_then(|m| m.get(k.as_str())).copied().unwrap_or(0.0);
                    (k.clone(), c_val - b_val)
                })
                .collect();
            per_stage_delta.insert(stage.clone(), deltas);
        }

        Self {
            baseline_mean_reward: baseline.reward_stats.mean,
            candidate_mean_reward: candidate.reward_stats.mean,
            reward_delta: candidate.reward_stats.mean - baseline.reward_stats.mean,
            win_rate: if total > 0 { wins as f64 / total as f64 } else { 0.0 },
            tie_rate: if total > 0 { ties as f64 / total as f64 } else { 0.0 },
            num_compared: total,
            per_stage_delta,
        }
    }
}
