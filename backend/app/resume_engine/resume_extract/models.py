"""Lossless reader intermediate representation; source IDs survive all transforms."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass
class Run:
    text: str
    bold: bool = False
    size: float | None = None
    color: str | None = None
    caps: bool = False
    font: str | None = None
    hyperlink: str | None = None
    original_text: str | None = None

@dataclass
class Line:
    id: str
    text: str
    runs: list[Run] = field(default_factory=list)
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    part: str = 'body'
    flow: str = 'body'
    table: str | None = None
    row: int | None = None
    cell: int | None = None
    style: str | None = None
    bullet: bool = False
    tag: str = 'TEXT'
    source_ids: list[str] = field(default_factory=list)
    duplicate_of: str | None = None
    heading_confidence: float | None = None

    @property
    def size(self) -> float:
        return max((r.size or 0 for r in self.runs), default=0)

    @property
    def bold(self) -> bool:
        return any(r.bold for r in self.runs if r.text.strip())

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["bbox"] = list(self.bbox) if self.bbox is not None else None
        return result

@dataclass
class Document:
    lines: list[Line]
    source_text: str
    source_method: str
    ocr: bool = False
    warnings: list[str] = field(default_factory=list)
    pages: int | None = None
    ocr_pages: list[int] = field(default_factory=list)

    @property
    def raw_text(self) -> str:
        return '\n'.join(line.text for line in self.lines)
