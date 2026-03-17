//! PyRewardFn — bridges Python callable to Rust RewardFn trait.
//!
//! Follows the exact pattern of PyToolExecutor in jeeves-core.

use pyo3::prelude::*;

use crate::reward::RewardFn;
use crate::trajectory::Step;

/// Wraps a Python callable(step_dict) → float as a Rust RewardFn.
pub struct PyRewardFn {
    py_fn: PyObject,
    name: String,
}

impl PyRewardFn {
    pub fn new(py_fn: PyObject, name: String) -> Self {
        Self { py_fn, name }
    }
}

impl std::fmt::Debug for PyRewardFn {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PyRewardFn")
            .field("name", &self.name)
            .finish()
    }
}

impl RewardFn for PyRewardFn {
    fn name(&self) -> &str {
        &self.name
    }

    fn score(&self, step: &Step) -> f64 {
        Python::with_gil(|py| -> Option<f64> {
            let json_mod = py.import_bound("json").ok()?;
            let step_str = serde_json::to_string(step).ok()?;
            let step_dict = json_mod.call_method1("loads", (step_str,)).ok()?;
            self.py_fn
                .call1(py, (step_dict,))
                .ok()?
                .extract::<f64>(py)
                .ok()
        })
        .unwrap_or(0.0)
    }
}

// Safety: PyObject is Send+Sync in PyO3 0.22
unsafe impl Send for PyRewardFn {}
unsafe impl Sync for PyRewardFn {}
