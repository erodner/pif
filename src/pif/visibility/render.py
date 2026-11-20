"""Render-based visibility: does drawing this text change any pixel a human could see?

Each page is rendered twice, as-is and with all text removed (redaction with images and
vector graphics kept). For every span the pixels inside its bbox are compared. If drawing
the text barely changes the image, the text is effectively invisible, whatever the trick:
same colour as the background, covered by an image or shape, clipped away, etc.
"""

from __future__ import annotations

import numpy as np
import pymupdf

from ..model import Span


class PageRenderer:
    def __init__(self, doc: pymupdf.Document, zoom: float = 2.0, contrast_threshold: int = 40):
        self.doc = doc
        self.zoom = zoom
        self.contrast_threshold = contrast_threshold
        self._textless: pymupdf.Document | None = None

    def _textless_doc(self) -> pymupdf.Document:
        if self._textless is None:
            self._textless = pymupdf.open("pdf", self.doc.tobytes())
        return self._textless

    def _render(self, page: pymupdf.Page) -> np.ndarray:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(self.zoom, self.zoom), colorspace=pymupdf.csRGB, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
        return arr[:, : pix.width * pix.n].reshape(pix.height, pix.width, pix.n).astype(np.int16)

    def page_diff(self, pno: int) -> np.ndarray:
        """Per-pixel max channel difference between the page with and without text."""
        with_text = self._render(self.doc[pno])
        tl = self._textless_doc()[pno]
        tl.add_redact_annot(tl.rect, fill=False)
        tl.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        without = self._render(tl)
        h = min(with_text.shape[0], without.shape[0])
        w = min(with_text.shape[1], without.shape[1])
        return np.abs(with_text[:h, :w] - without[:h, :w]).max(axis=2)

    def score_spans(self, pno: int, spans: list[Span]) -> None:
        """Set `span.visibility` = fraction of bbox pixels visibly changed by the text."""
        if not spans:
            return
        page = self.doc[pno]
        diff = self.page_diff(pno)
        mat = page.rotation_matrix * pymupdf.Matrix(self.zoom, self.zoom)
        strong = diff >= self.contrast_threshold
        H, W = strong.shape
        for sp in spans:
            r = pymupdf.Rect(sp.bbox) & page.rect
            if r.is_empty:
                sp.visibility = 0.0
                continue
            r = (r * mat).irect
            x0, y0 = max(0, r.x0 - 1), max(0, r.y0 - 1)
            x1, y1 = min(W, r.x1 + 1), min(H, r.y1 + 1)
            if x1 <= x0 or y1 <= y0:
                sp.visibility = 0.0
                continue
            region = strong[y0:y1, x0:x1]
            sp.visibility = float(region.mean())

    def close(self) -> None:
        if self._textless is not None:
            self._textless.close()
            self._textless = None
