from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class LabelMap:
    labels: Dict[str, str]
    annotations: Optional[Dict[str, str]] = None
