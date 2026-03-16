"""Export utilities — JSONL, Parquet, HuggingFace datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_jsonl(data: list[dict[str, Any]], path: str | Path) -> int:
    """Write a list of dicts as JSONL. Returns count written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")
    return len(data)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dicts."""
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def export_parquet(data: list[dict[str, Any]], path: str | Path) -> int:
    """Write data as Parquet. Requires pyarrow."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as e:
        raise ImportError("Parquet export requires pyarrow: pip install pyarrow") from e

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Flatten nested structures to JSON strings for Parquet compatibility
    flat = []
    for item in data:
        flat_item = {}
        for k, v in item.items():
            if isinstance(v, (dict, list)):
                flat_item[k] = json.dumps(v)
            else:
                flat_item[k] = v
        flat.append(flat_item)

    table = pa.Table.from_pylist(flat)
    pq.write_table(table, str(path))
    return len(data)


def export_hf_dataset(data: list[dict[str, Any]]):
    """Convert to a HuggingFace Dataset. Requires datasets package."""
    try:
        from datasets import Dataset
    except ImportError as e:
        raise ImportError("HF export requires datasets: pip install datasets") from e

    return Dataset.from_list(data)
