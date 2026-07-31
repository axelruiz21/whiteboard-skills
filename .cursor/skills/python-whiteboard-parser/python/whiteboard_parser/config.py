"""Explicit pipeline configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PipelineConfig:
    pipeline_version: str = "0.1.0-skeleton"
    max_bytes: int = 40 * 1024 * 1024
    max_megapixels: float = 40.0
    warn_long_side_below: int = 2000
    unusable_long_side_below: int = 1200
    seed: int = 0
    run_ocr: bool = False  # skeleton default: ingest-only

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
