"""Local-first whiteboard extraction package skeleton.

Heavy OCR stages are stubs in this pass. Use `run_pipeline` for ingest +
validated empty structure, then implement quality/rectify/OCR against fixtures.
"""

from .config import PipelineConfig
from .pipeline import run_pipeline

__all__ = ["PipelineConfig", "run_pipeline"]
__version__ = "0.1.0"
