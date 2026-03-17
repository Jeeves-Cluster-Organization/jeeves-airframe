//! Trajectory capture from pipeline event streams.

pub mod collector;
pub mod storage;
pub mod types;

pub use collector::TrajectoryCollector;
pub use storage::TrajectoryStore;
pub use types::{Step, StageTrace, StepAction, ToolEvent, Trajectory};

/// Build a user-facing context string from a step's prior outputs.
///
/// Format: `"Input: {input}\n\n[stage_a]: {content}\n\n[stage_b]: {content}"`
pub fn build_context(trajectory: &Trajectory, step: &Step) -> String {
    let mut parts = vec![format!("Input: {}", trajectory.input)];
    if let Some(prior) = step.observation.get("prior_outputs").and_then(|v| v.as_object()) {
        for (stage_name, output) in prior {
            let content = output.get("content").and_then(|v| v.as_str()).unwrap_or("");
            if !content.is_empty() {
                parts.push(format!("[{stage_name}]: {content}"));
            }
        }
    }
    parts.join("\n\n")
}

/// Resolve target step: specific stage if named, otherwise last step.
pub fn resolve_target_step<'a>(
    trajectory: &'a Trajectory,
    target_stage: Option<&str>,
) -> Option<&'a Step> {
    match target_stage {
        Some(stage) => trajectory.step_for_stage(stage),
        None => trajectory.steps.last(),
    }
}
