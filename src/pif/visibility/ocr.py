"""Glyph-remapping check: is the text a PDF *extracts* the text it *displays*?

Malicious fonts (an edited cmap or glyph table) or a lying /ToUnicode CMap can show
benign text to a reader while text extraction, and so the LLM, gets an injection. This
cannot be seen in the content stream. We render sample lines and OCR them.

Remapping is a property of a font, so the check runs per font and per document. For each
font a few visible single-line samples are OCR'd in recognition-only mode (~20-40 ms per
line). A font whose samples clearly disagree with their extracted text is "remapped". All
of its text then counts as hidden from the reader.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

import numpy as np
import pymupdf

from ..model import Span


@dataclass
class FontVerdict:
    font: str
    remapped: bool
    ratio: float  # best agreement between OCR and extraction across samples (0..1)
    samples: list[tuple[int, str, str, float]] = field(default_factory=list)  # (page, extracted, ocr, ratio)


class GlyphChecker:
    def __init__(
        self,
        target_px: float = 36.0,
        min_letters: int = 12,
        max_samples: int = 3,
        mismatch_ratio: float = 0.5,
        match_ratio: float = 0.8,
    ):
        from rapidocr_onnxruntime import RapidOCR  # optional dependency ([ocr] extra)

        self.engine = RapidOCR()
        self.target_px = target_px
        self.min_letters = min_letters
        self.max_samples = max_samples
        self.mismatch_ratio = mismatch_ratio
        self.match_ratio = match_ratio

    @classmethod
    def load(cls) -> "GlyphChecker | None":
        try:
            return cls()
        except Exception:  # noqa: BLE001 - not installed or model load failure
            return None

    def check(self, doc: pymupdf.Document, spans_by_page: dict[int, list[Span]]) -> dict[str, FontVerdict]:
        by_font: dict[str, list[Span]] = {}
        for spans in spans_by_page.values():
            for sp in spans:
                if self._usable(sp):
                    by_font.setdefault(sp.font, []).append(sp)

        verdicts: dict[str, FontVerdict] = {}
        for font, spans in by_font.items():
            spans.sort(key=lambda s: -len(_letters(s.text)))
            # Longest clean lines first (nothing drawn over them), spread over pages.
            clean: list[Span] = []
            for sp in spans:
                if not _overlapped(sp, spans_by_page[sp.page]):
                    clean.append(sp)
                if len(clean) >= 4 * self.max_samples:
                    break
            picked, pages = [], set()
            for sp in clean:
                if sp.page not in pages:
                    picked.append(sp)
                    pages.add(sp.page)
            chosen = {id(sp) for sp in picked}
            picked = (picked + [sp for sp in clean if id(sp) not in chosen])[: self.max_samples]
            verdict = FontVerdict(font, False, 0.0)
            mismatches = 0
            for sp in picked:
                extracted = _letters(sp.text)
                ocr = _letters(self._ocr(doc[sp.page], sp))
                if not 0.6 * len(extracted) <= len(ocr) <= 1.6 * len(extracted):
                    continue  # inconclusive: OCR saw too little, or neighbouring text (remaps keep length)
                ratio = difflib.SequenceMatcher(None, extracted, ocr, autojunk=False).ratio()
                verdict.samples.append((sp.page + 1, sp.text.strip()[:120], ocr[:120], round(ratio, 3)))
                verdict.ratio = max(verdict.ratio, ratio)
                if ratio >= self.match_ratio:
                    break  # one clean agreement is enough
                if ratio < self.mismatch_ratio:
                    mismatches += 1
            conclusive = len(verdict.samples)
            verdict.remapped = conclusive > 0 and mismatches > conclusive / 2 and verdict.ratio < self.match_ratio
            verdicts[font] = verdict
        return verdicts

    def _usable(self, sp: Span) -> bool:
        if sp.hidden or sp.font.startswith("Type3"):
            return False
        letters = _letters(sp.text)
        if len(letters) < self.min_letters:
            return False
        ascii_letters = sum(c.isascii() for c in letters)
        if ascii_letters < 0.8 * len(letters):
            return False  # OCR model is tuned for Latin (and Chinese); skip other scripts
        size = sp.effective_size or sp.size
        height = sp.bbox[3] - sp.bbox[1] if abs(sp.direction[0]) >= abs(sp.direction[1]) else sp.bbox[2] - sp.bbox[0]
        return size >= 4 and height <= 2.2 * size and abs(sp.direction[1]) < 0.01  # single horizontal line

    def _ocr(self, page: pymupdf.Page, sp: Span) -> str:
        size = sp.effective_size or sp.size
        rect = pymupdf.Rect(sp.bbox) + (-1, -1, 1, 1)
        rect &= page.rect
        if rect.is_empty:
            return ""
        zoom = max(1.5, min(8.0, self.target_px / max(size, 1.0)))
        pix = page.get_pixmap(clip=rect, matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, : pix.width * 3]
        img = np.ascontiguousarray(img.reshape(pix.height, pix.width, 3))
        result, _ = self.engine(img, use_det=False, use_cls=False, use_rec=True)
        return " ".join(r[0] for r in result or [] if r and r[0])


def _overlapped(sp: Span, page_spans: list[Span]) -> bool:
    """Another span drawn over/under this one would pollute the OCR crop."""
    r = pymupdf.Rect(sp.bbox)
    area = max(r.get_area(), 1e-6)
    for other in page_spans:
        if other is sp or not other.text.strip():
            continue
        inter = r & pymupdf.Rect(other.bbox)
        if not inter.is_empty and inter.get_area() > 0.1 * area:
            return True
    return False


def _letters(text: str) -> str:
    return "".join(c.lower() for c in text if c.isalnum())
