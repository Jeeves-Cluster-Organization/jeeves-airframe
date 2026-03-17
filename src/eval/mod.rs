//! Eval harness — run pipelines against eval datasets, compare model versions.

pub mod compare;
pub mod harness;

pub use compare::ModelComparison;
pub use harness::{EvalHarness, EvalResult};
