"""Cheap structural visibility checks on a single span."""

from __future__ import annotations

import pymupdf

from ..extract.pdf_text import median_advance
from ..model import Span, Technique


def apply_rules(
    span: Span,
    page_rect: pymupdf.Rect,
    image_rects: list[pymupdf.Rect],
    tiny_font_pt: float = 2.5,
) -> None:
    """Add structural hiding techniques to `span.techniques`."""
    if span.in_hidden_layer:
        span.techniques.add(Technique.HIDDEN_LAYER)

    if span.render_mode in (3, 7):
        if _over_scan_image(span, page_rect, image_rects):
            span.techniques.add(Technique.OCR_LAYER)
        else:
            span.techniques.add(Technique.INVISIBLE_RENDER_MODE)

    if span.opacity < 0.05:
        span.techniques.add(Technique.ZERO_OPACITY)

    # Effective (rendered) size, not the nominal Tf size: figures are often scaled XObjects.
    if span.text.strip() and 0 <= span.effective_size < tiny_font_pt:
        span.techniques.add(Technique.TINY_FONT)
    elif len(span.text.strip()) > 3:
        # Horizontally squashed text (e.g. Tz 1): glyphs far narrower than they are tall.
        if span.effective_size > 0 and median_advance(span) < 0.05 * span.effective_size:
            span.techniques.add(Technique.TINY_FONT)

    r = pymupdf.Rect(span.bbox)
    if r.is_empty or r.is_infinite:
        inter_area = 0.0
    else:
        inter = r & page_rect
        inter_area = 0.0 if inter.is_empty else inter.get_area()
    area = max(r.get_area(), 1e-6) if not r.is_empty else 1e-6
    if inter_area / area < 0.2:
        span.techniques.add(Technique.OFF_PAGE)


def _over_scan_image(span: Span, page_rect: pymupdf.Rect, image_rects: list[pymupdf.Rect]) -> bool:
    """Invisible text over a large image is the classic OCR text layer of a scanned page."""
    page_area = max(page_rect.get_area(), 1.0)
    r = pymupdf.Rect(span.bbox)
    for ir in image_rects:
        if ir.get_area() >= 0.3 * page_area and ir.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
            return True
    return False
