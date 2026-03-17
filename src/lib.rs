//! # jeeves-airframe — Pipeline Training Data Generator
//!
//! Captures pipeline execution trajectories from jeeves-core, scores them
//! with composable reward functions, and exports SFT/DPO/GRPO datasets
//! for SLM finetuning.
//!
//! ## Rust usage
//!
//! ```rust,no_run
//! use jeeves_core::prelude::PipelineRunner;
//! use jeeves_airframe::trajectory::TrajectoryCollector;
//! use jeeves_airframe::reward::TokenEfficiencyReward;
//!
//! # async fn example() -> jeeves_core::Result<()> {
//! let runner = PipelineRunner::from_json("pipeline.json", "prompts/", None).await?;
//! let reward = Box::new(TokenEfficiencyReward::new(2000, 1.0));
//! let collector = TrajectoryCollector::new(Some(reward), false);
//! let trajectory = collector.collect(&runner, "hello", "user1").await?;
//! # Ok(())
//! # }
//! ```

#![deny(unsafe_code)]
#![warn(missing_debug_implementations)]
#![warn(rust_2018_idioms)]

pub mod dataset;
pub mod eval;
pub mod reward;
pub mod trajectory;

#[cfg(feature = "py-bindings")]
#[allow(unsafe_code, clippy::useless_conversion)]
pub mod python;
