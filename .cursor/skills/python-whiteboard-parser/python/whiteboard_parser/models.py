"""Serializable public models for whiteboard extraction output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

QualityStatus = Literal["ok", "warning", "unusable"]

try:
    from pydantic import BaseModel, Field

    class SourceInfo(BaseModel):
        id: str
        width: int = 0
        height: int = 0
        path: str | None = None
        bytes: int | None = None

    class QualityInfo(BaseModel):
        status: QualityStatus = "ok"
        warnings: list[str] = Field(default_factory=list)

    class Diagram(BaseModel):
        nodes: list[dict[str, Any]] = Field(default_factory=list)
        edges: list[dict[str, Any]] = Field(default_factory=list)

    class Section(BaseModel):
        id: str
        title: str | None = None
        text_lines: list[dict[str, Any]] = Field(default_factory=list)
        lists: list[dict[str, Any]] = Field(default_factory=list)
        action_items: list[dict[str, Any]] = Field(default_factory=list)
        tables: list[dict[str, Any]] = Field(default_factory=list)
        diagram: Diagram = Field(default_factory=Diagram)
        bbox: list[int] = Field(default_factory=lambda: [0, 0, 0, 0])
        confidence: float = 0.0
        needs_review: bool = False

    class BoardDocument(BaseModel):
        pipeline_version: str = "0.1.0-skeleton"
        source: SourceInfo
        quality: QualityInfo
        sections: list[Section] = Field(default_factory=list)
        unresolved: list[dict[str, Any]] = Field(default_factory=list)

        def to_dict(self) -> dict[str, Any]:
            if hasattr(self, "model_dump"):
                return self.model_dump()
            return self.dict()

except ImportError:

    @dataclass
    class SourceInfo:
        id: str
        width: int = 0
        height: int = 0
        path: str | None = None
        bytes: int | None = None

    @dataclass
    class QualityInfo:
        status: QualityStatus = "ok"
        warnings: list[str] = field(default_factory=list)

    @dataclass
    class Diagram:
        nodes: list[dict[str, Any]] = field(default_factory=list)
        edges: list[dict[str, Any]] = field(default_factory=list)

    @dataclass
    class Section:
        id: str
        title: str | None = None
        text_lines: list[dict[str, Any]] = field(default_factory=list)
        lists: list[dict[str, Any]] = field(default_factory=list)
        action_items: list[dict[str, Any]] = field(default_factory=list)
        tables: list[dict[str, Any]] = field(default_factory=list)
        diagram: Diagram = field(default_factory=Diagram)
        bbox: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
        confidence: float = 0.0
        needs_review: bool = False

    @dataclass
    class BoardDocument:
        pipeline_version: str
        source: SourceInfo
        quality: QualityInfo
        sections: list[Section] = field(default_factory=list)
        unresolved: list[dict[str, Any]] = field(default_factory=list)

        def to_dict(self) -> dict[str, Any]:
            return asdict(self)
