"""Image quality measurement (stub)."""

from __future__ import annotations

from typing import Any

from .config import PipelineConfig


def measure_quality(_image: Any, config: PipelineConfig) -> dict[str, Any]:
    """Estimate blur, glare, contrast. Not implemented in the skeleton."""
    raise NotImplementedError(
        "Implement quality.measure_quality with OpenCV Laplacian blur, "
        f"glare/clipping checks; config={config.pipeline_version}"
    )
