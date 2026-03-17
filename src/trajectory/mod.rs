//! Trajectory capture from pipeline event streams.

pub mod collector;
pub mod storage;
pub mod types;

pub use collector::TrajectoryCollector;
pub use storage::TrajectoryStore;
pub use types::{Step, StageTrace, StepAction, ToolEvent, Trajectory};
