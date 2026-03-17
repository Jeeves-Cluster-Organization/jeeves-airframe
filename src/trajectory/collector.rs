//! TrajectoryCollector — builds Trajectory from typed PipelineEvent stream.

use std::collections::HashMap;

use jeeves_core::worker::llm::PipelineEvent;
use jeeves_core::worker::runner::PipelineRunner;
use tokio::sync::mpsc;

use crate::reward::RewardFn;
use crate::trajectory::types::*;

/// Collects trajectory data from pipeline event streams.
#[derive(Debug)]
pub struct TrajectoryCollector {
    reward_fn: Option<Box<dyn RewardFn>>,
    include_deltas: bool,
}

impl TrajectoryCollector {
    pub fn new(reward_fn: Option<Box<dyn RewardFn>>, include_deltas: bool) -> Self {
        Self {
            reward_fn,
            include_deltas,
        }
    }

    /// Collect a trajectory by running a pipeline via PipelineRunner.
    pub async fn collect(
        &self,
        runner: &PipelineRunner,
        input: &str,
        user_id: &str,
    ) -> jeeves_core::Result<Trajectory> {
        let (jh, mut rx) = runner.stream(input, user_id, None, None, None).await?;
        let pipeline_name = runner
            .default_pipeline()
            .to_string();
        let trajectory = self.collect_from_channel(&mut rx, input.to_string(), pipeline_name).await;
        // Wait for pipeline task to complete
        let _ = jh.await;
        Ok(trajectory)
    }

    /// Collect from a raw typed event channel.
    pub async fn collect_from_channel(
        &self,
        rx: &mut mpsc::Receiver<PipelineEvent>,
        input: String,
        pipeline_name: String,
    ) -> Trajectory {
        let mut stages: Vec<StageAccumulator> = Vec::new();
        let mut current: Option<StageAccumulator> = None;
        let mut done_event: Option<DoneData> = None;

        while let Some(event) = rx.recv().await {
            match event {
                PipelineEvent::StageStarted { stage, .. } => {
                    current = Some(StageAccumulator::new(stage));
                }
                PipelineEvent::Delta { content, .. } => {
                    if let Some(ref mut acc) = current {
                        acc.deltas.push(content);
                    }
                }
                PipelineEvent::ToolCallStart { id, name, .. } => {
                    if let Some(ref mut acc) = current {
                        acc.tool_events.push(ToolEvent::Start { id, name });
                    }
                }
                PipelineEvent::ToolResult { id, content, .. } => {
                    if let Some(ref mut acc) = current {
                        acc.tool_events.push(ToolEvent::Result { id, content });
                    }
                }
                PipelineEvent::StageCompleted { stage, metrics, .. } => {
                    if let Some(mut acc) = current.take() {
                        if let Some(m) = &metrics {
                            acc.trace = Some(StageTrace::from_metrics(stage, m));
                        } else {
                            acc.trace = Some(StageTrace {
                                stage_name: stage,
                                duration_ms: 0,
                                llm_calls: 0,
                                tool_calls: 0,
                                tokens_in: 0,
                                tokens_out: 0,
                                tool_results: Vec::new(),
                                success: true,
                                routing_reason: None,
                                routing_target: None,
                                deltas: Vec::new(),
                            });
                        }
                        stages.push(acc);
                    }
                }
                PipelineEvent::RoutingDecision {
                    from_stage,
                    to_stage,
                    reason,
                    ..
                } => {
                    for acc in stages.iter_mut().rev() {
                        if acc.stage_name == from_stage {
                            if let Some(ref mut trace) = acc.trace {
                                trace.routing_reason = Some(reason);
                                trace.routing_target = to_stage;
                            }
                            break;
                        }
                    }
                }
                PipelineEvent::Done {
                    terminal_reason,
                    outputs,
                    aggregate_metrics,
                    ..
                } => {
                    done_event = Some(DoneData {
                        terminal_reason,
                        outputs,
                        aggregate_metrics,
                    });
                    break;
                }
                PipelineEvent::Error { .. } | PipelineEvent::InterruptPending { .. } => {}
                _ => {} // Forward-compat for #[non_exhaustive]
            }
        }

        // Build steps from accumulated stage data
        let mut steps: Vec<Step> = Vec::with_capacity(stages.len());
        let mut accumulated_outputs: HashMap<String, serde_json::Value> = HashMap::new();
        let num_stages = stages.len();

        for (i, acc) in stages.into_iter().enumerate() {
            let is_terminal = i == num_stages - 1;
            let observation = serde_json::json!({
                "prior_outputs": accumulated_outputs.clone(),
                "input": input,
            });

            let content = acc.deltas.join("");
            let action = StepAction {
                content: content.clone(),
                tool_events: acc.tool_events,
            };

            let mut trace = acc.trace.unwrap_or_else(|| StageTrace {
                stage_name: acc.stage_name.clone(),
                duration_ms: 0,
                llm_calls: 0,
                tool_calls: 0,
                tokens_in: 0,
                tokens_out: 0,
                tool_results: Vec::new(),
                success: true,
                routing_reason: None,
                routing_target: None,
                deltas: Vec::new(),
            });

            if self.include_deltas {
                trace.deltas = acc.deltas;
            }

            let mut step = Step {
                stage_name: acc.stage_name.clone(),
                observation,
                action: action.clone(),
                reward: 0.0,
                stage_trace: trace,
                terminal: is_terminal,
            };

            if let Some(ref reward_fn) = self.reward_fn {
                step.reward = reward_fn.score(&step);
            }

            accumulated_outputs.insert(
                acc.stage_name,
                serde_json::to_value(&action).unwrap_or_default(),
            );
            steps.push(step);
        }

        let done = done_event.unwrap_or_default();

        Trajectory {
            trajectory_id: uuid::Uuid::new_v4().to_string()[..16].to_string(),
            pipeline_name,
            input,
            steps,
            terminal_reason: done.terminal_reason,
            aggregate_metrics: done.aggregate_metrics,
            outputs: done.outputs.unwrap_or(serde_json::Value::Null),
            metadata: serde_json::Value::Null,
            timestamp: chrono::Utc::now().to_rfc3339(),
        }
    }
}

// -- internal accumulators --

struct StageAccumulator {
    stage_name: String,
    deltas: Vec<String>,
    tool_events: Vec<ToolEvent>,
    trace: Option<StageTrace>,
}

impl StageAccumulator {
    fn new(stage_name: String) -> Self {
        Self {
            stage_name,
            deltas: Vec::new(),
            tool_events: Vec::new(),
            trace: None,
        }
    }
}

#[derive(Default)]
struct DoneData {
    terminal_reason: Option<String>,
    outputs: Option<serde_json::Value>,
    aggregate_metrics: Option<jeeves_core::worker::llm::AggregateMetrics>,
}
