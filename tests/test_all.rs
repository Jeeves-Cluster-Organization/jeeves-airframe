//! Integration tests for jeeves-airframe.
//!
//! Uses mock PipelineEvent streams to test trajectory collection,
//! reward scoring, dataset building, and eval — without a live kernel.

use std::sync::Arc;

use jeeves_airframe::trajectory::*;
use jeeves_airframe::reward::*;
use jeeves_airframe::dataset::*;

use jeeves_core::kernel::orchestrator_types::ToolCallResult;
use jeeves_core::kernel::routing::RoutingReason;
use jeeves_core::worker::llm::{AggregateMetrics, PipelineEvent, StageMetrics};
use tokio::sync::mpsc;

/// Build a realistic 2-stage event stream (classify → respond).
fn mock_events() -> Vec<PipelineEvent> {
    let pipeline: Arc<str> = Arc::from("test_pipeline");
    vec![
        PipelineEvent::StageStarted {
            stage: "classify".into(),
            pipeline: pipeline.clone(),
        },
        PipelineEvent::Delta {
            content: "intent: greeting".into(),
            stage: Some("classify".into()),
            pipeline: pipeline.clone(),
        },
        PipelineEvent::ToolCallStart {
            id: "tc_1".into(),
            name: "lookup".into(),
            stage: Some("classify".into()),
            pipeline: pipeline.clone(),
        },
        PipelineEvent::ToolResult {
            id: "tc_1".into(),
            content: "found: user profile".into(),
            stage: Some("classify".into()),
            pipeline: pipeline.clone(),
        },
        PipelineEvent::StageCompleted {
            stage: "classify".into(),
            pipeline: pipeline.clone(),
            metrics: Some(StageMetrics {
                duration_ms: 800,
                llm_calls: 1,
                tool_calls: 1,
                tokens_in: 200,
                tokens_out: 50,
                tool_results: vec![ToolCallResult {
                    name: "lookup".into(),
                    success: true,
                    latency_ms: 150,
                    error_type: None,
                }],
                success: true,
            }),
        },
        PipelineEvent::RoutingDecision {
            from_stage: "classify".into(),
            to_stage: Some("respond".into()),
            reason: RoutingReason::DefaultRoute,
            pipeline: pipeline.clone(),
        },
        PipelineEvent::StageStarted {
            stage: "respond".into(),
            pipeline: pipeline.clone(),
        },
        PipelineEvent::Delta {
            content: "Hello! How can I help?".into(),
            stage: Some("respond".into()),
            pipeline: pipeline.clone(),
        },
        PipelineEvent::StageCompleted {
            stage: "respond".into(),
            pipeline: pipeline.clone(),
            metrics: Some(StageMetrics {
                duration_ms: 1200,
                llm_calls: 1,
                tool_calls: 0,
                tokens_in: 300,
                tokens_out: 100,
                tool_results: vec![],
                success: true,
            }),
        },
        PipelineEvent::Done {
            process_id: "p_test_001".into(),
            terminated: true,
            terminal_reason: Some("Completed".into()),
            outputs: Some(serde_json::json!({"final": "Hello! How can I help?"})),
            pipeline: pipeline.clone(),
            aggregate_metrics: Some(AggregateMetrics {
                total_duration_ms: 2000,
                total_llm_calls: 2,
                total_tool_calls: 1,
                total_tokens_in: 500,
                total_tokens_out: 150,
                stages_executed: vec!["classify".into(), "respond".into()],
            }),
        },
    ]
}

/// Send mock events through a channel and collect.
async fn collect_mock(
    collector: &TrajectoryCollector,
    events: Vec<PipelineEvent>,
) -> Trajectory {
    let (tx, mut rx) = mpsc::channel(64);
    for event in events {
        tx.send(event).await.unwrap();
    }
    drop(tx);
    collector
        .collect_from_channel(&mut rx, "hello".into(), "test_pipeline".into())
        .await
}

// ==========================================================================
// Trajectory Collection
// ==========================================================================

#[tokio::test]
async fn test_collect_basic() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    assert_eq!(t.pipeline_name, "test_pipeline");
    assert_eq!(t.input, "hello");
    assert_eq!(t.terminal_reason.as_deref(), Some("Completed"));
    assert_eq!(t.steps.len(), 2);
}

#[tokio::test]
async fn test_step_stage_names() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;
    assert_eq!(t.stage_names(), vec!["classify", "respond"]);
}

#[tokio::test]
async fn test_step_actions_capture_content() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    assert_eq!(t.steps[0].action.content, "intent: greeting");
    assert_eq!(t.steps[1].action.content, "Hello! How can I help?");
}

#[tokio::test]
async fn test_tool_events_captured() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    assert_eq!(t.steps[0].action.tool_events.len(), 2);
    match &t.steps[0].action.tool_events[0] {
        ToolEvent::Start { name, .. } => assert_eq!(name, "lookup"),
        _ => panic!("Expected Start event"),
    }
}

#[tokio::test]
async fn test_stage_trace_metrics() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    let trace = &t.steps[0].stage_trace;
    assert_eq!(trace.duration_ms, 800);
    assert_eq!(trace.llm_calls, 1);
    assert_eq!(trace.tool_calls, 1);
    assert_eq!(trace.tokens_in, 200);
    assert_eq!(trace.tokens_out, 50);
    assert!(trace.success);
    assert_eq!(trace.tool_results.len(), 1);
    assert_eq!(trace.tool_results[0].name, "lookup");
}

#[tokio::test]
async fn test_routing_captured() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    let routing = &t.steps[0].stage_trace.routing_reason;
    assert!(routing.is_some());
    assert_eq!(
        t.steps[0].stage_trace.routing_target.as_deref(),
        Some("respond")
    );
}

#[tokio::test]
async fn test_terminal_step_marked() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    assert!(!t.steps[0].terminal);
    assert!(t.steps[1].terminal);
}

#[tokio::test]
async fn test_include_deltas() {
    let collector = TrajectoryCollector::new(None, true);
    let t = collect_mock(&collector, mock_events()).await;

    assert_eq!(t.steps[0].stage_trace.deltas, vec!["intent: greeting"]);
}

#[tokio::test]
async fn test_deltas_excluded_by_default() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    assert!(t.steps[0].stage_trace.deltas.is_empty());
}

#[tokio::test]
async fn test_collect_with_reward() {
    let reward = Box::new(CallableRewardFn::new("always_one", |_| 1.0));
    let collector = TrajectoryCollector::new(Some(reward), false);
    let t = collect_mock(&collector, mock_events()).await;

    assert_eq!(t.steps[0].reward, 1.0);
    assert_eq!(t.steps[1].reward, 1.0);
    assert_eq!(t.total_reward(), 2.0);
}

#[tokio::test]
async fn test_step_for_stage() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    assert!(t.step_for_stage("classify").is_some());
    assert!(t.step_for_stage("nonexistent").is_none());
}

// ==========================================================================
// Storage
// ==========================================================================

#[tokio::test]
async fn test_storage_roundtrip() {
    let collector = TrajectoryCollector::new(None, true);
    let t = collect_mock(&collector, mock_events()).await;

    let dir = tempfile::tempdir().unwrap();
    let store = TrajectoryStore::new(dir.path().join("test.jsonl")).unwrap();

    store.save(&t).unwrap();
    assert_eq!(store.count().unwrap(), 1);

    let loaded = store.load().unwrap();
    assert_eq!(loaded.len(), 1);
    assert_eq!(loaded[0].trajectory_id, t.trajectory_id);
    assert_eq!(loaded[0].steps.len(), 2);
    assert_eq!(loaded[0].steps[0].stage_trace.deltas, vec!["intent: greeting"]);
}

#[tokio::test]
async fn test_storage_batch() {
    let collector = TrajectoryCollector::new(None, false);
    let t1 = collect_mock(&collector, mock_events()).await;
    let t2 = collect_mock(&collector, mock_events()).await;

    let dir = tempfile::tempdir().unwrap();
    let store = TrajectoryStore::new(dir.path().join("test.jsonl")).unwrap();

    store.save_batch(&[t1, t2]).unwrap();
    assert_eq!(store.count().unwrap(), 2);
}

// ==========================================================================
// Reward Functions
// ==========================================================================

fn make_step(tokens_in: i64, tokens_out: i64, duration_ms: i64, tool_results: Vec<ToolCallResult>) -> Step {
    Step {
        stage_name: "test".into(),
        observation: serde_json::Value::Null,
        action: StepAction {
            content: "test output".into(),
            tool_events: vec![],
        },
        reward: 0.0,
        stage_trace: StageTrace {
            stage_name: "test".into(),
            duration_ms,
            llm_calls: 1,
            tool_calls: tool_results.len() as i32,
            tokens_in,
            tokens_out,
            tool_results,
            success: true,
            routing_reason: None,
            routing_target: None,
            deltas: vec![],
        },
        terminal: true,
    }
}

#[test]
fn test_token_efficiency_reward() {
    let reward = TokenEfficiencyReward::new(1000, 1.0);
    let step = make_step(200, 100, 500, vec![]);
    assert!((reward.score(&step) - (-0.3)).abs() < f64::EPSILON);
}

#[test]
fn test_latency_reward() {
    let reward = LatencyReward::new(1000, 0.5);
    let step = make_step(0, 0, 500, vec![]);
    assert!((reward.score(&step) - (-0.25)).abs() < f64::EPSILON);
}

#[test]
fn test_tool_success_rate() {
    let reward = ToolSuccessRateReward::new(1.0);
    let step = make_step(0, 0, 0, vec![
        ToolCallResult { name: "a".into(), success: true, latency_ms: 100, error_type: None },
        ToolCallResult { name: "b".into(), success: false, latency_ms: 50, error_type: Some("timeout".into()) },
    ]);
    assert!((reward.score(&step) - 0.5).abs() < f64::EPSILON);
}

#[test]
fn test_tool_success_no_tools() {
    let reward = ToolSuccessRateReward::new(1.0);
    let step = make_step(0, 0, 0, vec![]);
    assert!((reward.score(&step) - 1.0).abs() < f64::EPSILON);
}

#[test]
fn test_composite_reward() {
    let r1 = Box::new(CallableRewardFn::new("a", |_| 1.0));
    let r2 = Box::new(CallableRewardFn::new("b", |_| 2.0));
    let composite = CompositeReward::new(vec![r1, r2]);
    let step = make_step(0, 0, 0, vec![]);
    assert!((composite.score(&step) - 3.0).abs() < f64::EPSILON);
}

#[test]
fn test_weighted_reward() {
    let r1 = Box::new(CallableRewardFn::new("a", |_| 1.0)) as Box<dyn RewardFn>;
    let r2 = Box::new(CallableRewardFn::new("b", |_| 1.0)) as Box<dyn RewardFn>;
    let weighted = WeightedReward::new(vec![
        ("a".into(), r1, 2.0),
        ("b".into(), r2, 0.5),
    ]);
    let step = make_step(0, 0, 0, vec![]);
    assert!((weighted.score(&step) - 2.5).abs() < f64::EPSILON);
}

// ==========================================================================
// Dataset Builders
// ==========================================================================

#[tokio::test]
async fn test_sft_builder() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    let mut sft = SftBuilder::new(None, None, None);
    let added = sft.add_trajectory(&t);
    assert_eq!(added, 2);
    assert_eq!(sft.len(), 2);

    let examples = sft.build();
    assert_eq!(examples[0].messages.last().unwrap().role, "assistant");
}

#[tokio::test]
async fn test_sft_include_stages() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    let mut sft = SftBuilder::new(None, Some(vec!["respond".into()]), None);
    sft.add_trajectory(&t);
    assert_eq!(sft.len(), 1);
}

#[tokio::test]
async fn test_sft_min_reward() {
    let reward = Box::new(CallableRewardFn::new("test", |s: &Step| {
        if s.stage_name == "respond" { 0.9 } else { 0.1 }
    }));
    let collector = TrajectoryCollector::new(Some(reward), false);
    let t = collect_mock(&collector, mock_events()).await;

    let mut sft = SftBuilder::new(Some(0.5), None, None);
    sft.add_trajectory(&t);
    assert_eq!(sft.len(), 1); // Only "respond" passes
}

#[tokio::test]
async fn test_sft_system_prompt() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    let mut sft = SftBuilder::new(None, None, Some("You are helpful.".into()));
    sft.add_trajectory(&t);
    assert_eq!(sft.build()[0].messages[0].role, "system");
}

#[tokio::test]
async fn test_sft_export_jsonl() {
    let collector = TrajectoryCollector::new(None, false);
    let t = collect_mock(&collector, mock_events()).await;

    let mut sft = SftBuilder::new(None, None, None);
    sft.add_trajectory(&t);

    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("sft.jsonl");
    let count = sft.export_jsonl(&path).unwrap();
    assert_eq!(count, 2);
}

#[tokio::test]
async fn test_dpo_builder() {
    let good_reward = Box::new(CallableRewardFn::new("good", |_| 1.0));
    let bad_reward = Box::new(CallableRewardFn::new("bad", |_| 0.0));

    let good_collector = TrajectoryCollector::new(Some(good_reward), false);
    let bad_collector = TrajectoryCollector::new(Some(bad_reward), false);

    let t_good = collect_mock(&good_collector, mock_events()).await;
    let t_bad = collect_mock(&bad_collector, mock_events()).await;

    let mut dpo = DpoBuilder::new(None, 0.0, None);
    let added = dpo.add_trajectory_group(&[t_good, t_bad]);
    assert_eq!(added, 1);
    assert_eq!(dpo.len(), 1);
}

#[tokio::test]
async fn test_dpo_margin_filter() {
    let collector = TrajectoryCollector::new(None, false);
    let t1 = collect_mock(&collector, mock_events()).await;
    let t2 = collect_mock(&collector, mock_events()).await;

    let mut dpo = DpoBuilder::new(None, 999.0, None); // Margin too high
    assert_eq!(dpo.add_trajectory_group(&[t1, t2]), 0);
}

#[tokio::test]
async fn test_grpo_builder() {
    let collector = TrajectoryCollector::new(None, false);
    let trajectories: Vec<_> = futures::future::join_all(
        (0..4).map(|_| collect_mock(&collector, mock_events()))
    ).await;

    let mut grpo = GrpoBuilder::new(None, None, None);
    let added = grpo.add_trajectory_group(&trajectories);
    assert_eq!(added, 1);

    let examples = grpo.build();
    assert_eq!(examples[0].completions.len(), 4);
    assert_eq!(examples[0].rewards.len(), 4);
}

#[tokio::test]
async fn test_grpo_group_size() {
    let collector = TrajectoryCollector::new(None, false);
    let trajectories: Vec<_> = futures::future::join_all(
        (0..8).map(|_| collect_mock(&collector, mock_events()))
    ).await;

    let mut grpo = GrpoBuilder::new(None, Some(4), None);
    grpo.add_trajectory_group(&trajectories);
    assert_eq!(grpo.build()[0].completions.len(), 4);
}

// ==========================================================================
// Eval
// ==========================================================================

// Note: Full eval tests require a live PipelineRunner (kernel + LLM).
// Tested here via EvalResult construction from trajectories.

#[tokio::test]
async fn test_eval_result_stats() {
    use jeeves_airframe::eval::EvalResult;

    let reward = Box::new(CallableRewardFn::new("test", |_| 1.0));
    let collector = TrajectoryCollector::new(Some(reward), false);
    let t1 = collect_mock(&collector, mock_events()).await;
    let t2 = collect_mock(&collector, mock_events()).await;

    let result = EvalResult::from_trajectories(vec![t1, t2]);
    assert_eq!(result.reward_stats.mean, 2.0); // 2 steps * 1.0
    assert!(result.per_stage_metrics.contains_key("classify"));
    assert!(result.per_stage_metrics.contains_key("respond"));
}

#[tokio::test]
async fn test_model_comparison() {
    use jeeves_airframe::eval::{EvalResult, ModelComparison};

    let good = Box::new(CallableRewardFn::new("good", |_| 1.0));
    let bad = Box::new(CallableRewardFn::new("bad", |_| 0.0));

    let good_collector = TrajectoryCollector::new(Some(good), false);
    let bad_collector = TrajectoryCollector::new(Some(bad), false);

    let baseline = EvalResult::from_trajectories(vec![
        collect_mock(&bad_collector, mock_events()).await,
    ]);
    let candidate = EvalResult::from_trajectories(vec![
        collect_mock(&good_collector, mock_events()).await,
    ]);

    let comparison = ModelComparison::compare(&baseline, &candidate);
    assert!(comparison.reward_delta > 0.0);
    assert_eq!(comparison.win_rate, 1.0);
}
