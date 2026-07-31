"""Pipeline entry: ingest + validated empty document when OCR is off."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import PipelineConfig
from .ingest import ingest_image
from .models import BoardDocument, QualityInfo, SourceInfo


def run_pipeline(path: str | Path, config: PipelineConfig | None = None) -> dict[str, Any]:
    """Run the extraction pipeline.

    Skeleton behavior:
    - Always runs hardened ingest.
    - If ingest rejects → return document with quality.unusable and no sections.
    - If `config.run_ocr` is False (default) → return empty sections with ingest quality.
    - If `config.run_ocr` is True → raise NotImplementedError until OCR stages exist.
    """
    config = config or PipelineConfig()
    path = Path(path)
    report = ingest_image(path, config)

    source = SourceInfo(
        id=(report.get("source") or {}).get("id") or "sha256:unknown",
        width=int(report.get("width") or 0),
        height=int(report.get("height") or 0),
        path=str(path),
        bytes=report.get("bytes"),
    )
    q = report.get("quality") or {}
    quality = QualityInfo(
        status=q.get("status") or "unusable",
        warnings=list(q.get("warnings") or []),
    )
    if report.get("reject_reason"):
        quality.warnings = [*quality.warnings, str(report["reject_reason"])]
        quality.status = "unusable"

    doc = BoardDocument(
        pipeline_version=config.pipeline_version,
        source=source,
        quality=quality,
        sections=[],
        unresolved=[],
    )

    if not report.get("ok", False) or quality.status == "unusable":
        return doc.to_dict()

    if config.run_ocr:
        raise NotImplementedError(
            "OCR stages (rectify/variants/segment/ocr/reconcile/structure) "
            "are stubs in this skeleton. Set run_ocr=False for ingest-only, "
            "or implement stages per REFERENCE.md."
        )

    if quality.status == "ok":
        quality.warnings = [
            *quality.warnings,
            "skeleton ingest-only run; OCR stages not executed",
        ]
        # Keep status ok but note skeleton — agents should not treat as extraction.
    return doc.to_dict()


__all__ = ["run_pipeline"]
