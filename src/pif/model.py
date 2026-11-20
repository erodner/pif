"""Core data model shared by extraction, detection and reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return ["info", "low", "medium", "high"].index(self.value)

    @classmethod
    def parse(cls, value: str) -> "Severity":
        return cls(value.lower())


class Technique(str, Enum):
    """How a piece of text is hidden from (or never shown to) a human reader."""

    INVISIBLE_RENDER_MODE = "invisible_render_mode"  # Tr 3 / 7
    ZERO_OPACITY = "zero_opacity"
    TINY_FONT = "tiny_font"
    OFF_PAGE = "off_page"  # outside CropBox
    HIDDEN_LAYER = "hidden_layer"  # optional content group switched OFF
    NOT_RENDERED = "not_rendered"  # renders to ~no visible pixels: same colour as background, covered, clipped
    OCR_LAYER = "ocr_layer"  # invisible text over a scanned image (usually benign)
    INVISIBLE_UNICODE = "invisible_unicode"  # zero-width / tag characters
    NON_VISUAL = "non_visual_carrier"  # metadata, annotations, form fields, bookmarks, embedded files
    JAVASCRIPT = "javascript"


HIDING_TECHNIQUES = {
    Technique.INVISIBLE_RENDER_MODE,
    Technique.ZERO_OPACITY,
    Technique.TINY_FONT,
    Technique.OFF_PAGE,
    Technique.HIDDEN_LAYER,
    Technique.NOT_RENDERED,
}


@dataclass
class Span:
    """A run of characters sharing one text style, as drawn by the content stream."""

    page: int  # 0-based
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    color: tuple[float, ...]
    opacity: float
    render_mode: int
    layer: str
    seqno: int
    char_bboxes: list[tuple[float, float, float, float]] = field(default_factory=list, repr=False)
    direction: tuple[float, float] = (1.0, 0.0)
    effective_size: float = 0.0  # rendered glyph height in points (after all transformations)
    in_hidden_layer: bool = False
    techniques: set[Technique] = field(default_factory=set)
    visibility: float | None = None  # fraction of bbox pixels changed by drawing this text

    @property
    def hidden(self) -> bool:
        return bool(self.techniques & HIDING_TECHNIQUES)


@dataclass
class Match:
    """A detector hit inside a text, as a half-open character range."""

    detector: str
    rule_id: str
    label: str
    score: float  # 0..1, how injection-like
    start: int
    end: int


@dataclass
class Finding:
    severity: Severity
    carrier: str  # page_text, metadata, xmp, annotation, form_field, bookmark, embedded_file, javascript
    text: str
    page: int | None = None  # 1-based for humans
    bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    techniques: list[Technique] = field(default_factory=list)
    semantic_score: float = 0.0
    rules: list[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["techniques"] = [t.value for t in self.techniques]
        d["bboxes"] = [[round(v, 1) for v in b] for b in self.bboxes]
        d["semantic_score"] = round(self.semantic_score, 3)
        return d


@dataclass
class Report:
    path: str
    pages: int = 0
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def max_severity(self) -> Severity | None:
        if not self.findings:
            return None
        return max((f.severity for f in self.findings), key=lambda s: s.rank)

    def sort(self) -> None:
        self.findings.sort(key=lambda f: (-f.severity.rank, f.page or 0, f.carrier))

    def to_dict(self) -> dict[str, Any]:
        ms = self.max_severity
        return {
            "path": self.path,
            "pages": self.pages,
            "max_severity": ms.value if ms else None,
            "seconds": round(self.seconds, 3),
            "findings": [f.to_dict() for f in self.findings],
            "errors": self.errors,
        }
