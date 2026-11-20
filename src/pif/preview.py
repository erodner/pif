"""Page previews for findings (shared by the HTML report and the desktop app)."""

from __future__ import annotations

import pymupdf

from .model import Finding

CROP_ZOOM = 2.0
CROP_PAD = 18.0
MAX_CROP_HEIGHT_PT = 260.0
MIN_CROP_W_PT = 320.0
MIN_CROP_H_PT = 90.0


def finding_png(doc: pymupdf.Document, f: Finding, zoom: float = CROP_ZOOM, max_width_px: int = 1400) -> bytes | None:
    """PNG of the page region around a finding, with its text boxes outlined in red."""
    try:
        page = doc[f.page - 1]
    except Exception:  # noqa: BLE001
        return None
    rects = [pymupdf.Rect(b) & page.rect for b in f.bboxes]
    rects = [r for r in rects if not r.is_empty]
    if not rects:
        return None  # e.g. text entirely off-page
    union = rects[0]
    for r in rects[1:]:
        union |= r
    clip = union + (-CROP_PAD, -CROP_PAD, CROP_PAD, CROP_PAD)
    # Tiny hits (e.g. 0.1pt text) still get readable surrounding context.
    cx, cy = (clip.x0 + clip.x1) / 2, (clip.y0 + clip.y1) / 2
    w, h = max(clip.width, MIN_CROP_W_PT), max(clip.height, MIN_CROP_H_PT)
    clip = pymupdf.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2) & page.rect
    if clip.height > MAX_CROP_HEIGHT_PT:
        clip.y1 = clip.y0 + MAX_CROP_HEIGHT_PT
    # Draw on a throw-away copy of the page so the document stays untouched.
    tmp = pymupdf.open()
    tmp.insert_pdf(doc, from_page=page.number, to_page=page.number)
    tp = tmp[0]
    shape = tp.new_shape()
    for r in rects:
        shape.draw_rect((r + (-1.5, -1.5, 1.5, 1.5)) * tp.derotation_matrix)
    shape.finish(color=(0.85, 0.1, 0.1), width=1.2, dashes="[3 2] 0")
    shape.commit(overlay=True)
    zoom = min(zoom, max_width_px / max(clip.width, 1))
    pix = tp.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    tmp.close()
    return pix.tobytes("png")
