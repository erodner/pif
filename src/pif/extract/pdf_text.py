"""Character-level text extraction with full style information (via PyMuPDF texttrace)."""

from __future__ import annotations

import pymupdf

from ..model import Span


def extract_spans(doc: pymupdf.Document) -> dict[int, list[Span]]:
    """Extract every drawn text span per page, including text in OCG layers switched OFF.

    MuPDF skips text in hidden optional-content layers. We therefore extract from a copy
    with all layers switched on and mark spans from layers that were originally off. The
    original document is left untouched, so rendering still shows what a reader sees.
    """
    ocgs = doc.get_ocgs() or {}
    off_names = {info["name"] for info in ocgs.values() if not info.get("on", True)}
    source = doc
    if off_names:
        # The runtime layer state only changes on reload, so extract from a copy whose
        # default configuration has every layer switched on.
        tmp = pymupdf.open("pdf", doc.tobytes())
        tmp.set_layer(-1, basestate="ON", on=list(ocgs), off=[])
        source = pymupdf.open("pdf", tmp.tobytes())
        tmp.close()
    try:
        return {pno: _page_spans(source[pno], pno, off_names) for pno in range(source.page_count)}
    finally:
        if source is not doc:
            source.close()


def _page_spans(page: pymupdf.Page, pno: int, off_layer_names: set[str]) -> list[Span]:
    spans: list[Span] = []
    for tr in page.get_texttrace():
        chars = tr.get("chars") or []
        if not chars:
            continue
        text = "".join(chr(c[0]) if c[0] > 0 else "�" for c in chars)
        layer = tr.get("layer") or ""
        direction = tuple(tr.get("dir") or (1.0, 0.0))
        spans.append(
            Span(
                page=pno,
                text=text,
                bbox=tuple(tr["bbox"]),
                font=tr.get("font", ""),
                size=float(tr.get("size", 0.0)),
                color=tuple(tr.get("color") or ()),
                opacity=float(tr.get("opacity", 1.0) if tr.get("opacity") is not None else 1.0),
                render_mode=int(tr.get("type", 0)),
                layer=layer,
                seqno=int(tr.get("seqno", 0)),
                char_bboxes=[tuple(c[3]) for c in chars],
                in_hidden_layer=bool(layer) and layer in off_layer_names,
                direction=direction,
                effective_size=_effective_size(tr, direction),
            )
        )
    return spans


def _effective_size(tr: dict, direction: tuple[float, float]) -> float:
    """Median glyph height in page space. `size` is the nominal Tf size and ignores the CTM."""
    horizontal = abs(direction[0]) >= abs(direction[1])
    extents = sorted(
        (b[3] - b[1]) if horizontal else (b[2] - b[0])
        for b in (c[3] for c in tr["chars"])
    )
    if not extents:
        return 0.0
    extent = extents[len(extents) // 2]
    if str(tr.get("font", "")).startswith("Type3"):
        # Type3 glyph metrics are in arbitrary glyph space (matplotlib figures etc.), so
        # heights are unreliable. Estimate the size from the glyph advance instead.
        advances = sorted(
            (b[2] - b[0]) if horizontal else (b[3] - b[1])
            for b in (c[3] for c in tr["chars"])
        )
        return max(extent, advances[len(advances) // 2] * 1.8)
    em = (tr.get("ascender") or 0.8) - (tr.get("descender") or -0.2)
    return max(0.0, extent / em) if em > 0 else extent


def median_advance(span: Span) -> float:
    horizontal = abs(span.direction[0]) >= abs(span.direction[1])
    widths = sorted(
        (b[2] - b[0]) if horizontal else (b[3] - b[1])
        for ch, b in zip(span.text, span.char_bboxes)
        if not ch.isspace()
    )
    return widths[len(widths) // 2] if widths else 0.0


def _rotate(box, direction):
    """Express a bbox in a frame where the text direction is the +x axis."""
    dx, dy = direction
    xs, ys = [], []
    for px, py in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
        xs.append(px * dx + py * dy)
        ys.append(-px * dy + py * dx)
    return (min(xs), min(ys), max(xs), max(ys))


def page_char_stream(spans: list[Span]) -> list[tuple[str, int]]:
    """Linearise spans (content-stream order) into (char, span_index) pairs.

    Many PDF producers position words without emitting space characters, so spaces and
    newlines are synthesised from glyph geometry. Synthetic whitespace has owner -1.

    Exception: a span whose glyphs are each placed on their own "line" (microglyph
    steganography: one tiny glyph per position, stacked or scattered) would otherwise come
    out as single letters, which no detector can read. Text extractors used by LLM
    pipelines join such glyphs in drawing order, so inside such spans we do the same.
    """
    out: list[tuple[str, int]] = []
    prev_box = None
    prev_size = 0.0
    prev_dir = None
    for si, sp in enumerate(spans):
        size = sp.effective_size or sp.size
        boxes = sp.char_bboxes or [sp.bbox] * len(sp.text)
        rboxes = [_rotate(b, sp.direction) for b in boxes]
        scattered = _is_scattered(sp.text, rboxes, size)
        for k, (ch, rbox) in enumerate(zip(sp.text, rboxes)):
            if prev_box is not None and out and out[-1][0] not in " \n":
                if k > 0 and scattered:
                    sep = ""
                elif k == 0 and _glyph_by_glyph(spans, si):
                    sep = ""
                elif prev_dir != sp.direction:
                    sep = "\n"
                else:
                    sep = _separator(prev_box, rbox, max(prev_size, size, 0.1))
                if sep and ch != " ":
                    out.append((sep, -1))
            out.append((ch, si))
            prev_box, prev_size, prev_dir = rbox, size, sp.direction
    return out


def _glyph_by_glyph(spans: list[Span], si: int) -> bool:
    """Consecutive hidden spans of one or two glyphs each: text drawn glyph by glyph."""
    if si == 0:
        return False
    a, b = spans[si - 1], spans[si]
    return len(a.text.strip()) <= 2 and len(b.text.strip()) <= 2 and a.hidden and b.hidden


def _is_scattered(text: str, rboxes: list, size: float) -> bool:
    """True if most consecutive glyphs of a span would be split onto separate lines."""
    if len(text) < 8:
        return False
    breaks = sum(
        1
        for a, b in zip(rboxes, rboxes[1:])
        if abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2) > max(size, 0.1) * 0.6
    )
    return breaks > 0.6 * (len(text) - 1)


def _separator(a, b, size: float) -> str:
    ay = (a[1] + a[3]) / 2
    by = (b[1] + b[3]) / 2
    if abs(ay - by) > size * 0.6:
        return "\n"
    gap = b[0] - a[2]
    if gap > size * 0.2 or gap < -size * 2:
        return " "
    return ""
