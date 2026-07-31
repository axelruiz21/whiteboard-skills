"""Board perspective rectification (stub)."""

from __future__ import annotations

from typing import Any

from .config import PipelineConfig


def rectify_board(_image: Any, config: PipelineConfig) -> Any:
    raise NotImplementedError(
        "Implement quadrilateral detection + perspective transform; "
        f"retain inverse transform for provenance (config={config.pipeline_version})"
    )
