//! Dataset builders — convert trajectories to SFT/DPO/GRPO training formats.

pub mod dpo;
pub mod grpo;
pub mod sft;

pub use dpo::DpoBuilder;
pub use grpo::GrpoBuilder;
pub use sft::SftBuilder;

use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;

/// Export a list of serde-serializable items as JSONL.
pub fn export_jsonl(data: &[impl serde::Serialize], path: &Path) -> std::io::Result<usize> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let file = File::create(path)?;
    let mut writer = BufWriter::new(file);
    for item in data {
        serde_json::to_writer(&mut writer, item)?;
        writeln!(writer)?;
    }
    Ok(data.len())
}
