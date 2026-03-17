//! PyO3 bindings for jeeves-airframe.
//!
//! Thin wrappers over Rust types. Python callable reward functions
//! are bridged to the Rust RewardFn trait via PyRewardFn.

mod rewards;

use pyo3::prelude::*;

use crate::dataset;
use crate::reward;
use crate::trajectory;
use rewards::PyRewardFn;

/// Build a Rust RewardFn from a Python reward spec.
///
/// Accepts:
///   - None → no reward
///   - A Python callable(step_dict) → f64
///   - A dict {"name": (callable, weight), ...} → WeightedReward
fn build_reward_fn(py: Python<'_>, obj: Option<PyObject>) -> PyResult<Option<Box<dyn reward::RewardFn>>> {
    let Some(obj) = obj else { return Ok(None) };
    if obj.is_none(py) {
        return Ok(None);
    }

    // If it's a dict, build a WeightedReward
    if let Ok(dict) = obj.downcast_bound::<pyo3::types::PyDict>(py) {
        let mut weights = Vec::new();
        for (key, value) in dict.iter() {
            let name: String = key.extract()?;
            let tuple = value.downcast::<pyo3::types::PyTuple>()?;
            let callable: PyObject = tuple.get_item(0)?.into();
            let weight: f64 = tuple.get_item(1)?.extract()?;
            let rf = Box::new(PyRewardFn::new(callable.into_py(py), name.clone()))
                as Box<dyn reward::RewardFn>;
            weights.push((name, rf, weight));
        }
        return Ok(Some(Box::new(reward::WeightedReward::new(weights))));
    }

    // Otherwise treat as a callable
    Ok(Some(Box::new(PyRewardFn::new(obj, "custom".into()))))
}

// -- TrajectoryCollector --

#[pyclass(name = "TrajectoryCollector")]
struct PyTrajectoryCollector {
    inner: trajectory::TrajectoryCollector,
}

#[pymethods]
impl PyTrajectoryCollector {
    #[new]
    #[pyo3(signature = (reward_fn=None, include_deltas=false))]
    fn new(py: Python<'_>, reward_fn: Option<PyObject>, include_deltas: bool) -> PyResult<Self> {
        let rf = build_reward_fn(py, reward_fn)?;
        Ok(Self {
            inner: trajectory::TrajectoryCollector::new(rf, include_deltas),
        })
    }

    /// collect(runner, input) → dict
    #[pyo3(signature = (runner, input, user_id="airframe"))]
    fn collect(
        &self,
        py: Python<'_>,
        runner: &jeeves_core::python::runner::PyPipelineRunner,
        input: &str,
        user_id: &str,
    ) -> PyResult<PyObject> {
        let trajectory = py
            .allow_threads(|| {
                runner
                    .runtime()
                    .block_on(self.inner.collect(runner.runner(), input, user_id))
            })
            .map_err(|e| {
                pyo3::exceptions::PyRuntimeError::new_err(format!("Collection error: {e}"))
            })?;
        json_to_pyobject(py, &trajectory)
    }
}

// -- TrajectoryStore --

#[pyclass(name = "TrajectoryStore")]
struct PyTrajectoryStore {
    inner: trajectory::TrajectoryStore,
}

#[pymethods]
impl PyTrajectoryStore {
    #[new]
    fn new(path: &str) -> PyResult<Self> {
        let inner = trajectory::TrajectoryStore::new(path)
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
        Ok(Self { inner })
    }

    fn save(&self, py: Python<'_>, trajectory: PyObject) -> PyResult<()> {
        let t: trajectory::Trajectory = pyobject_to_json(py, trajectory)?;
        self.inner
            .save(&t)
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }

    fn load(&self, py: Python<'_>) -> PyResult<PyObject> {
        let trajectories = self
            .inner
            .load()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
        json_to_pyobject(py, &trajectories)
    }

    fn count(&self) -> PyResult<usize> {
        self.inner
            .count()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }
}

// -- Dataset Builders --

#[pyclass(name = "SftBuilder")]
struct PySftBuilder {
    inner: dataset::SftBuilder,
}

#[pymethods]
impl PySftBuilder {
    #[new]
    #[pyo3(signature = (min_reward=None, include_stages=None, system_prompt=None))]
    fn new(
        min_reward: Option<f64>,
        include_stages: Option<Vec<String>>,
        system_prompt: Option<String>,
    ) -> Self {
        Self {
            inner: dataset::SftBuilder::new(min_reward, include_stages, system_prompt),
        }
    }

    fn add_trajectory(&mut self, py: Python<'_>, trajectory: PyObject) -> PyResult<usize> {
        let t: trajectory::Trajectory = pyobject_to_json(py, trajectory)?;
        Ok(self.inner.add_trajectory(&t))
    }

    fn build(&self, py: Python<'_>) -> PyResult<PyObject> {
        json_to_pyobject(py, self.inner.build())
    }

    fn export_jsonl(&self, path: &str) -> PyResult<usize> {
        self.inner
            .export_jsonl(std::path::Path::new(path))
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }
}

#[pyclass(name = "DpoBuilder")]
struct PyDpoBuilder {
    inner: dataset::DpoBuilder,
}

#[pymethods]
impl PyDpoBuilder {
    #[new]
    #[pyo3(signature = (reward_fn=None, margin=0.0, target_stage=None))]
    fn new(
        py: Python<'_>,
        reward_fn: Option<PyObject>,
        margin: f64,
        target_stage: Option<String>,
    ) -> PyResult<Self> {
        let rf = build_reward_fn(py, reward_fn)?;
        Ok(Self {
            inner: dataset::DpoBuilder::new(rf, margin, target_stage),
        })
    }

    fn add_trajectory_group(&mut self, py: Python<'_>, trajectories: PyObject) -> PyResult<usize> {
        let ts: Vec<trajectory::Trajectory> = pyobject_to_json(py, trajectories)?;
        Ok(self.inner.add_trajectory_group(&ts))
    }

    fn build(&self, py: Python<'_>) -> PyResult<PyObject> {
        json_to_pyobject(py, self.inner.build())
    }

    fn export_jsonl(&self, path: &str) -> PyResult<usize> {
        self.inner
            .export_jsonl(std::path::Path::new(path))
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }
}

#[pyclass(name = "GrpoBuilder")]
struct PyGrpoBuilder {
    inner: dataset::GrpoBuilder,
}

#[pymethods]
impl PyGrpoBuilder {
    #[new]
    #[pyo3(signature = (reward_fn=None, group_size=None, target_stage=None))]
    fn new(
        py: Python<'_>,
        reward_fn: Option<PyObject>,
        group_size: Option<usize>,
        target_stage: Option<String>,
    ) -> PyResult<Self> {
        let rf = build_reward_fn(py, reward_fn)?;
        Ok(Self {
            inner: dataset::GrpoBuilder::new(rf, group_size, target_stage),
        })
    }

    fn add_trajectory_group(&mut self, py: Python<'_>, trajectories: PyObject) -> PyResult<usize> {
        let ts: Vec<trajectory::Trajectory> = pyobject_to_json(py, trajectories)?;
        Ok(self.inner.add_trajectory_group(&ts))
    }

    fn build(&self, py: Python<'_>) -> PyResult<PyObject> {
        json_to_pyobject(py, self.inner.build())
    }

    fn export_jsonl(&self, path: &str) -> PyResult<usize> {
        self.inner
            .export_jsonl(std::path::Path::new(path))
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }

    fn __len__(&self) -> usize {
        self.inner.len()
    }
}

// -- Module Registration --

#[pymodule]
fn jeeves_airframe(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyTrajectoryCollector>()?;
    m.add_class::<PyTrajectoryStore>()?;
    m.add_class::<PySftBuilder>()?;
    m.add_class::<PyDpoBuilder>()?;
    m.add_class::<PyGrpoBuilder>()?;
    Ok(())
}

// -- Helpers --

fn json_to_pyobject(py: Python<'_>, value: &(impl serde::Serialize + ?Sized)) -> PyResult<PyObject> {
    let json_str = serde_json::to_string(value)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    let json_mod = py.import_bound("json")?;
    Ok(json_mod.call_method1("loads", (json_str,))?.into())
}

fn pyobject_to_json<T: serde::de::DeserializeOwned>(py: Python<'_>, obj: PyObject) -> PyResult<T> {
    let json_mod = py.import_bound("json")?;
    let json_str: String = json_mod.call_method1("dumps", (obj,))?.extract()?;
    serde_json::from_str(&json_str)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}
