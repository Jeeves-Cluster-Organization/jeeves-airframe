//! EvalHarness — run a pipeline against an eval dataset and collect metrics.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::reward::RewardFn;
use crate::trajectory::{Trajectory, TrajectoryCollector};
use jeeves_core::worker::runner::PipelineRunner;

/// Results from evaluating a pipeline on a dataset.
#[derive(Debug, Clone, Serialize)]
pub struct EvalResult {
    pub reward_stats: RewardStats,
    pub per_stage_metrics: HashMap<String, HashMap<String, f64>>,
    pub aggregate: HashMap<String, f64>,
    #[serde(skip)]
    pub trajectories: Vec<Trajectory>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RewardStats {
    pub mean: f64,
    pub median: f64,
    pub stdev: f64,
    pub min: f64,
    pub max: f64,
}

/// Run a pipeline against an eval dataset, collect trajectories and metrics.
#[derive(Debug)]
pub struct EvalHarness {
    collector: TrajectoryCollector,
}

impl EvalHarness {
    pub fn new(reward_fn: Option<Box<dyn RewardFn>>) -> Self {
        Self {
            collector: TrajectoryCollector::new(reward_fn, false),
        }
    }

    pub async fn evaluate(
        &self,
        runner: &PipelineRunner,
        examples: &[EvalExample],
    ) -> jeeves_core::Result<EvalResult> {
        let mut trajectories = Vec::with_capacity(examples.len());
        for example in examples {
            let t = self
                .collector
                .collect(runner, &example.input, "eval")
                .await?;
            trajectories.push(t);
        }
        Ok(EvalResult::from_trajectories(trajectories))
    }
}

/// Single eval example.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvalExample {
    pub input: String,
    #[serde(default)]
    pub expected: Option<String>,
    #[serde(default)]
    pub metadata: serde_json::Value,
}

impl EvalResult {
    pub fn from_trajectories(trajectories: Vec<Trajectory>) -> Self {
        let rewards: Vec<f64> = trajectories.iter().map(|t| t.total_reward()).collect();
        let reward_stats = compute_stats(&rewards);

        // Per-stage metrics
        let mut stage_data: HashMap<String, HashMap<String, Vec<f64>>> = HashMap::new();
        for t in &trajectories {
            for step in &t.steps {
                let entry = stage_data
                    .entry(step.stage_name.clone())
                    .or_default();
                entry
                    .entry("duration_ms".into())
                    .or_default()
                    .push(step.stage_trace.duration_ms as f64);
                entry
                    .entry("tokens_in".into())
                    .or_default()
                    .push(step.stage_trace.tokens_in as f64);
                entry
                    .entry("tokens_out".into())
                    .or_default()
                    .push(step.stage_trace.tokens_out as f64);
                entry
                    .entry("llm_calls".into())
                    .or_default()
                    .push(step.stage_trace.llm_calls as f64);
                entry
                    .entry("tool_calls".into())
                    .or_default()
                    .push(step.stage_trace.tool_calls as f64);
                entry
                    .entry("success_rate".into())
                    .or_default()
                    .push(if step.stage_trace.success { 1.0 } else { 0.0 });
            }
        }
        let per_stage_metrics: HashMap<String, HashMap<String, f64>> = stage_data
            .into_iter()
            .map(|(stage, metrics)| {
                let avgs = metrics
                    .into_iter()
                    .map(|(k, v)| (k, mean(&v)))
                    .collect();
                (stage, avgs)
            })
            .collect();

        // Aggregate
        let mut aggregate = HashMap::new();
        aggregate.insert(
            "num_examples".into(),
            trajectories.len() as f64,
        );

        Self {
            reward_stats,
            per_stage_metrics,
            aggregate,
            trajectories,
        }
    }
}

fn compute_stats(values: &[f64]) -> RewardStats {
    if values.is_empty() {
        return RewardStats::default();
    }
    let n = values.len() as f64;
    let mean_val = values.iter().sum::<f64>() / n;
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let median = if sorted.len() % 2 == 0 {
        (sorted[sorted.len() / 2 - 1] + sorted[sorted.len() / 2]) / 2.0
    } else {
        sorted[sorted.len() / 2]
    };
    let variance = values.iter().map(|v| (v - mean_val).powi(2)).sum::<f64>() / (n - 1.0).max(1.0);
    let stdev = variance.sqrt();

    RewardStats {
        mean: mean_val,
        median,
        stdev,
        min: sorted[0],
        max: sorted[sorted.len() - 1],
    }
}

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}
