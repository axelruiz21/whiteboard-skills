"""OCR adapter (stub). Keep engines behind this boundary."""

from __future__ import annotations

from typing import Any, Protocol

from .config import PipelineConfig


class OcrEngine(Protocol):
    def run(self, image: Any, *, psm: int) -> list[dict[str, Any]]: ...


def run_ocr(_image: Any, config: PipelineConfig, engine: OcrEngine | None = None) -> list[dict[str, Any]]:
    raise NotImplementedError(
        "Implement OCR adapter (Tesseract default) returning word text, confidence, "
        f"bbox, line/block ids, and variant id (config={config.pipeline_version})"
    )
