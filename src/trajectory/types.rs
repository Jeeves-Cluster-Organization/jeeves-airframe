//! Core trajectory data types. Reuses jeeves-core types directly.

use jeeves_core::kernel::orchestrator_types::ToolCallResult;
use jeeves_core::kernel::routing::RoutingReason;
use jeeves_core::worker::llm::{AggregateMetrics, StageMetrics};
use serde::{Deserialize, Serialize};

/// Data captured from a single pipeline stage execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageTrace {
    pub stage_name: String,
    pub duration_ms: i64,
    pub llm_calls: i32,
    pub tool_calls: i32,
    pub tokens_in: i64,
    pub tokens_out: i64,
    pub tool_results: Vec<ToolCallResult>,
    pub success: bool,
    pub routing_reason: Option<RoutingReason>,
    pub routing_target: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub deltas: Vec<String>,
}

impl StageTrace {
    /// Build directly from kernel's StageMetrics.
    pub fn from_metrics(stage_name: String, metrics: &StageMetrics) -> Self {
        Self {
            stage_name,
            duration_ms: metrics.duration_ms,
            llm_calls: metrics.llm_calls,
            tool_calls: metrics.tool_calls,
            tokens_in: metrics.tokens_in,
            tokens_out: metrics.tokens_out,
            tool_results: metrics.tool_results.clone(),
            success: metrics.success,
            routing_reason: None,
            routing_target: None,
            deltas: Vec::new(),
        }
    }
}

/// Model output from a stage: text content + tool interactions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepAction {
    pub content: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tool_events: Vec<ToolEvent>,
}

/// A tool interaction event during stage execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ToolEvent {
    Start { id: String, name: String },
    Result { id: String, content: String },
}

/// Single stage transition in a trajectory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Step {
    pub stage_name: String,
    pub observation: serde_json::Value,
    pub action: StepAction,
    pub reward: f64,
    pub stage_trace: StageTrace,
    pub terminal: bool,
}

/// Complete pipeline execution trajectory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trajectory {
    pub trajectory_id: String,
    pub pipeline_name: String,
    pub input: String,
    pub steps: Vec<Step>,
    pub terminal_reason: Option<String>,
    pub aggregate_metrics: Option<AggregateMetrics>,
    pub outputs: serde_json::Value,
    #[serde(default)]
    pub metadata: serde_json::Value,
    #[serde(default)]
    pub timestamp: String,
}

impl Trajectory {
    pub fn total_reward(&self) -> f64 {
        self.steps.iter().map(|s| s.reward).sum()
    }

    pub fn stage_names(&self) -> Vec<&str> {
        self.steps.iter().map(|s| s.stage_name.as_str()).collect()
    }

    pub fn step_for_stage(&self, stage_name: &str) -> Option<&Step> {
        self.steps.iter().find(|s| s.stage_name == stage_name)
    }
}
