"""Safe image ingest: hash, caps, MIME sniff, dimension gate."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from .config import PipelineConfig


def _load_validate_image():
    """Import validate_image from the sibling image-ingest-hardening skill when present."""
    here = Path(__file__).resolve()
    # .../python-whiteboard-parser/python/whiteboard_parser/ingest.py
    skills_root = here.parents[3]  # .cursor/skills
    candidate = skills_root / "image-ingest-hardening" / "scripts" / "validate_image.py"
    if candidate.is_file():
        spec = importlib.util.spec_from_file_location("validate_image", candidate)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules["validate_image"] = mod
            spec.loader.exec_module(mod)
            return mod
    return None


def ingest_image(path: Path, config: PipelineConfig) -> dict[str, Any]:
    """Return an ingest report compatible with image-ingest-hardening."""
    path = Path(path)
    mod = _load_validate_image()
    if mod is not None:
        return mod.validate_image(
            path,
            max_bytes=config.max_bytes,
            max_megapixels=config.max_megapixels,
            apply_exif=True,
        )

    # Minimal fallback without the sibling skill / Pillow
    if not path.is_file():
        return {
            "ok": False,
            "reject_reason": f"not a file: {path}",
            "quality": {"status": "unusable", "warnings": []},
        }
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return {
        "ok": True,
        "path": str(path),
        "bytes": len(data),
        "source": {"id": f"sha256:{digest}"},
        "width": 0,
        "height": 0,
        "quality": {
            "status": "warning",
            "warnings": [
                "image-ingest-hardening not found; using hash-only ingest fallback"
            ],
        },
        "mime": None,
        "exif_applied": False,
    }
