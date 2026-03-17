//! TrajectoryStore — JSONL persistence via serde.

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};

use crate::trajectory::types::Trajectory;

/// Append-only JSONL store for trajectory persistence.
///
/// Uses serde_json + BufWriter for efficient serialization.
/// Supports save, batch save, load, filtered load, and count.
#[derive(Debug)]
pub struct TrajectoryStore {
    path: PathBuf,
}

impl TrajectoryStore {
    pub fn new(path: impl Into<PathBuf>) -> std::io::Result<Self> {
        let path = path.into();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        Ok(Self { path })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn save(&self, trajectory: &Trajectory) -> std::io::Result<()> {
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        let mut writer = BufWriter::new(file);
        serde_json::to_writer(&mut writer, trajectory)?;
        writeln!(writer)?;
        Ok(())
    }

    pub fn save_batch(&self, trajectories: &[Trajectory]) -> std::io::Result<()> {
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        let mut writer = BufWriter::new(file);
        for t in trajectories {
            serde_json::to_writer(&mut writer, t)?;
            writeln!(writer)?;
        }
        Ok(())
    }

    pub fn load(&self) -> std::io::Result<Vec<Trajectory>> {
        if !self.path.exists() {
            return Ok(Vec::new());
        }
        let file = File::open(&self.path)?;
        let reader = BufReader::new(file);
        let mut trajectories = Vec::new();
        for line in reader.lines() {
            let line = line?;
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            let t: Trajectory = serde_json::from_str(trimmed)
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
            trajectories.push(t);
        }
        Ok(trajectories)
    }

    pub fn load_filtered(
        &self,
        filter_fn: impl Fn(&serde_json::Value) -> bool,
    ) -> std::io::Result<Vec<Trajectory>> {
        if !self.path.exists() {
            return Ok(Vec::new());
        }
        let file = File::open(&self.path)?;
        let reader = BufReader::new(file);
        let mut trajectories = Vec::new();
        for line in reader.lines() {
            let line = line?;
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            let value: serde_json::Value = serde_json::from_str(trimmed)
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
            if filter_fn(&value) {
                let t: Trajectory = serde_json::from_value(value)
                    .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
                trajectories.push(t);
            }
        }
        Ok(trajectories)
    }

    pub fn count(&self) -> std::io::Result<usize> {
        if !self.path.exists() {
            return Ok(0);
        }
        let file = File::open(&self.path)?;
        let reader = BufReader::new(file);
        Ok(reader.lines().filter(|l| l.as_ref().is_ok_and(|s| !s.trim().is_empty())).count())
    }
}
