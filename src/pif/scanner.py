"""Orchestration: PDF -> spans -> visibility + semantic detection -> findings."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

import pymupdf

from .detect.base import Detector
from .detect.patterns import PatternDetector
from .extract.normalize import NormText, normalize, normalize_string
from .extract.pdf_structure import iter_carriers
from .extract.pdf_text import extract_spans, page_char_stream
from .model import HIDING_TECHNIQUES, Finding, Match, Report, Severity, Span, Technique
from .visibility.render import PageRenderer
from .visibility.rules import apply_rules

pymupdf.TOOLS.mupdf_display_errors(False)


@dataclass
class ScanOptions:
    render: bool = True  # pixel-diff visibility check (catches colour matching, covering, clipping)
    zoom: float = 2.0
    contrast_threshold: int = 40  # 0..255 per-channel difference counted as "visible"
    min_visible_fraction: float = 0.02  # fraction of bbox pixels that must change
    tiny_font_pt: float = 2.5
    min_hidden_run_chars: int = 15  # report hidden text without injection language above this length
    semantic_threshold: float = 0.5
    context_chars: int = 80
    detectors: list[Detector] = field(default_factory=lambda: [PatternDetector()])
    ml: Any = None  # pif.ml.cascade.MLCascade, optional
    glyph_checker: Any = None  # pif.visibility.ocr.GlyphChecker, optional (OCR)


def scan(source: str | Path | bytes, options: ScanOptions | None = None) -> Report:
    """Scan a PDF file path or PDF bytes."""
    options = options or ScanOptions()
    name = "<bytes>" if isinstance(source, bytes) else str(source)
    report = Report(path=name)
    t0 = time.perf_counter()
    try:
        head = source[:1024] if isinstance(source, bytes) else Path(source).open("rb").read(1024)
        if b"%PDF" not in head:
            report.errors.append("not a PDF file (no %PDF header)")
            report.seconds = time.perf_counter() - t0
            return report
        doc = pymupdf.open("pdf", source) if isinstance(source, bytes) else pymupdf.open(source, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"cannot open: {e}")
        return report
    try:
        if doc.needs_pass and not doc.authenticate(""):
            report.errors.append("encrypted PDF (password required)")
            return report
        _scan_doc(doc, options, report)
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"scan failed: {type(e).__name__}: {e}")
    finally:
        doc.close()
        report.seconds = time.perf_counter() - t0
    report.sort()
    return report


def _scan_doc(doc: pymupdf.Document, opt: ScanOptions, report: Report) -> None:
    report.pages = doc.page_count
    spans_by_page = extract_spans(doc)
    # 1) visibility: structural rules + pixel diff, 2) OCR glyph check on what is visible,
    # 3) semantic analysis per page.
    renderer = PageRenderer(doc, opt.zoom, opt.contrast_threshold) if opt.render else None
    try:
        for pno, spans in spans_by_page.items():
            _apply_structural_rules(doc[pno], spans, opt)
            if renderer is not None and spans:
                _apply_render_check(renderer, pno, spans, opt)
    finally:
        if renderer:
            renderer.close()
    if opt.glyph_checker is not None:
        report.findings.extend(_check_glyphs(doc, spans_by_page, opt))
    for pno in range(doc.page_count):
        spans = spans_by_page.get(pno, [])
        if spans:
            report.findings.extend(_scan_page(pno, spans, opt))
    report.findings.extend(_scan_carriers(doc, opt))


# --------------------------------------------------------------------------------------- page


def _apply_structural_rules(page, spans: list[Span], opt: ScanOptions) -> None:
    try:
        image_rects = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    except Exception:
        image_rects = []
    for sp in spans:
        apply_rules(sp, page.rect, image_rects, opt.tiny_font_pt)


def _check_glyphs(doc, spans_by_page: dict[int, list[Span]], opt: ScanOptions) -> list[Finding]:
    """OCR-verify fonts; mark every span of a remapped font as hidden (GLYPH_REMAP)."""
    findings = []
    for font, v in opt.glyph_checker.check(doc, spans_by_page).items():
        if not v.remapped:
            continue
        pages = set()
        for spans in spans_by_page.values():
            for sp in spans:
                if sp.font == font:
                    sp.techniques.add(Technique.GLYPH_REMAP)
                    pages.add(sp.page + 1)
        page, extracted, shown, ratio = v.samples[0]
        findings.append(
            Finding(
                severity=Severity.LOW,
                carrier="font",
                text=f"extracted: {extracted!r} | displayed (OCR): {shown!r}",
                page=page,
                techniques=[Technique.GLYPH_REMAP],
                detail=(
                    f"font {font!r} displays different text than it extracts (OCR agreement {v.ratio:.0%}, "
                    f"pages {', '.join(map(str, sorted(pages)[:10]))}): a malicious font/ToUnicode map, "
                    "or a broken one that feeds garbage to LLMs"
                ),
            )
        )
    return findings


def _apply_render_check(renderer: PageRenderer, pno: int, spans: list[Span], opt: ScanOptions) -> None:
    candidates = [
        s for s in spans
        if not (s.techniques & (HIDING_TECHNIQUES | {Technique.OCR_LAYER})) and s.text.strip()
    ]
    renderer.score_spans(pno, candidates)
    for s in candidates:
        if s.visibility is not None and s.visibility < opt.min_visible_fraction:
            s.techniques.add(Technique.NOT_RENDERED)


def _scan_page(pno: int, spans: list[Span], opt: ScanOptions) -> list[Finding]:
    norm = normalize(page_char_stream(spans))
    findings: list[Finding] = []
    findings.extend(_invisible_unicode_finding(norm, spans, pno, opt, carrier="page_text"))

    hidden_mask = [o >= 0 and spans[o].hidden for o in norm.owners]
    covered = [False] * len(norm.text)
    ml_matches = opt.ml.score_segments(_page_segments(norm.text, hidden_mask)) if opt.ml else []

    for start, end, matches in _merged_matches(norm.text, opt, ml_matches):
        idx = [i for i in range(start, end) if norm.owners[i] >= 0 and not norm.text[i].isspace()]
        if not idx:
            continue
        hidden_frac = sum(hidden_mask[i] for i in idx) / len(idx)
        owners = sorted({norm.owners[i] for i in idx})
        techniques = _techniques(spans, owners, hidden_only=hidden_frac >= 0.5)
        if hidden_frac >= 0.5:
            start, end = _expand_run(hidden_mask, start, end)
            severity = Severity.HIGH
            detail = f"injection-like text hidden from readers ({hidden_frac:.0%} of characters hidden)"
        elif any(Technique.OCR_LAYER in spans[o].techniques for o in owners):
            severity = Severity.MEDIUM
            detail = "injection-like text in an invisible OCR layer over an image; verify the image shows it"
        elif _is_quoted(norm.text, start, end):
            severity = Severity.LOW
            detail = "visible injection-like text inside quotation marks (likely discussion, not an attack)"
        else:
            severity = Severity.MEDIUM
            detail = "injection-like text visible on the page"
        for i in range(start, end):
            covered[i] = True
        text = norm.text[start:end] if hidden_frac >= 0.5 else _with_context(norm.text, start, end, opt.context_chars)
        findings.append(
            Finding(
                severity=severity,
                carrier="page_text",
                text=text.strip(),
                page=pno + 1,
                bboxes=_bboxes(spans, sorted({norm.owners[i] for i in range(start, end) if norm.owners[i] >= 0})),
                techniques=techniques,
                semantic_score=max(m.score for m in matches),
                rules=sorted({f"{m.rule_id}:{m.label}" for m in matches}),
                detail=detail,
            )
        )

    # Hidden text without injection language: report as LOW so humans can judge.
    for start, end in _runs(hidden_mask):
        if any(covered[start:end]):
            continue
        owners = sorted({norm.owners[i] for i in range(start, end) if norm.owners[i] >= 0})
        if all(spans[o].techniques & HIDING_TECHNIQUES == {Technique.GLYPH_REMAP} for o in owners):
            continue  # reported once per font by _check_glyphs
        chunk = norm.text[start:end].strip()
        words = [w for w in chunk.split() if sum(c.isalpha() for c in w) >= 2]
        if sum(c.isalpha() for c in chunk) < opt.min_hidden_run_chars or len(words) < 3:
            continue  # dotted leaders, tick labels, stray glyphs
        findings.append(
            Finding(
                severity=Severity.LOW,
                carrier="page_text",
                text=chunk[:2000],
                page=pno + 1,
                bboxes=_bboxes(spans, owners),
                techniques=_techniques(spans, owners, hidden_only=True),
                detail="hidden text without known injection language",
            )
        )
    return findings


def _page_segments(text: str, hidden_mask: list[bool]):
    """Sentence segments that never straddle a hidden/visible boundary."""
    from .ml.cascade import split_segments

    segments = []
    start = 0
    for i in range(1, len(text) + 1):
        if i == len(text) or (hidden_mask[i] != hidden_mask[start] and not text[i].isspace()):
            segments.extend(split_segments(text[start:i], force=hidden_mask[start], offset=start))
            start = i
    return segments


def _merged_matches(text: str, opt: ScanOptions, extra: list[Match] | None = None) -> list[tuple[int, int, list[Match]]]:
    matches = [m for d in opt.detectors for m in d.detect(text)] + list(extra or [])
    matches = [m for m in matches if m.score >= opt.semantic_threshold]
    matches.sort(key=lambda m: m.start)
    groups: list[tuple[int, int, list[Match]]] = []
    for m in matches:
        if groups and m.start <= groups[-1][1] + 40:
            s, e, ms = groups[-1]
            groups[-1] = (s, max(e, m.end), ms + [m])
        else:
            groups.append((m.start, m.end, [m]))
    return groups


def _runs(mask: list[bool]) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, v in enumerate(mask + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    # merge runs separated only by synthetic whitespace
    merged: list[tuple[int, int]] = []
    for s, e in runs:
        if merged and s - merged[-1][1] <= 1:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def _expand_run(mask: list[bool], start: int, end: int) -> tuple[int, int]:
    """Grow a hit to the whole contiguous hidden region (tolerating 1-char gaps)."""
    while start > 0 and (mask[start - 1] or (start > 1 and mask[start - 2])):
        start -= 1
    while end < len(mask) and (mask[end] or (end + 1 < len(mask) and mask[end + 1])):
        end += 1
    return start, end


_OPEN_QUOTES = "\"“„«‘‚'"
_CLOSE_QUOTES = "\"”»’'"


def _is_quoted(text: str, start: int, end: int, reach: int = 30) -> bool:
    """True if [start, end) sits inside a quotation that opens shortly before the hit."""
    before = text[max(0, start - reach) : start]
    opens = [i for i, c in enumerate(before) if c in _OPEN_QUOTES and (i == 0 or not before[i - 1].isalnum())]
    if not opens:
        return False
    tail = before[opens[-1] + 1 :]
    if any(c in "”»" for c in tail):
        return False
    after = text[end : end + 200]
    return any(c in _CLOSE_QUOTES for c in after)


def _with_context(text: str, start: int, end: int, n: int) -> str:
    s, e = max(0, start - n), min(len(text), end + n)
    return ("…" if s > 0 else "") + text[s:e].replace("\n", " ") + ("…" if e < len(text) else "")


def _techniques(spans: list[Span], owners: list[int], hidden_only: bool) -> list[Technique]:
    found: set[Technique] = set()
    for o in owners:
        found |= spans[o].techniques
    if hidden_only:
        found &= HIDING_TECHNIQUES | {Technique.OCR_LAYER}
    return sorted(found, key=lambda t: t.value)


def _bboxes(spans: list[Span], owners: list[int], limit: int = 50) -> list[tuple[float, float, float, float]]:
    rects: list[pymupdf.Rect] = []
    for o in owners:
        r = pymupdf.Rect(spans[o].bbox)
        for i, existing in enumerate(rects):
            if abs(existing.y0 - r.y0) < 2 and abs(existing.y1 - r.y1) < 2 and r.x0 - existing.x1 < 20:
                rects[i] = existing | r
                break
        else:
            rects.append(r)
    return [tuple(r) for r in rects[:limit]]


# ------------------------------------------------------------------------- invisible unicode


def _invisible_unicode_finding(norm: NormText, spans, pno, opt: ScanOptions, carrier: str, location: str = ""):
    inv = norm.invisible
    if inv.tag_payload.strip():
        payload_matches = _merged_matches(normalize_string(inv.tag_payload).text, opt)
        score = max((m.score for _, _, ms in payload_matches for m in ms), default=0.0)
        yield Finding(
            severity=Severity.HIGH if payload_matches else Severity.MEDIUM,
            carrier=carrier,
            text=inv.tag_payload[:2000],
            page=None if pno is None else pno + 1,
            bboxes=_bboxes(spans, sorted(o for o in inv.owners if o >= 0)) if spans else [],
            techniques=[Technique.INVISIBLE_UNICODE],
            semantic_score=score,
            rules=sorted({f"{m.rule_id}:{m.label}" for _, _, ms in payload_matches for m in ms}),
            detail=f"text smuggled in invisible Unicode tag characters {location}".strip(),
        )
    elif inv.invisible_count >= 10:
        yield Finding(
            severity=Severity.LOW,
            carrier=carrier,
            text=f"{inv.invisible_count} zero-width/format characters",
            page=None if pno is None else pno + 1,
            techniques=[Technique.INVISIBLE_UNICODE],
            detail=f"many invisible Unicode characters (possible obfuscation) {location}".strip(),
        )


# ---------------------------------------------------------------------------------- carriers


def _scan_carriers(doc: pymupdf.Document, opt: ScanOptions) -> list[Finding]:
    findings: list[Finding] = []
    for c in iter_carriers(doc):
        if c.carrier == "javascript":
            findings.append(
                Finding(
                    severity=Severity.LOW,
                    carrier="javascript",
                    text=c.text[:500],
                    page=c.page,
                    techniques=[Technique.JAVASCRIPT],
                    detail=f"document contains JavaScript ({c.location})",
                )
            )
        norm = normalize_string(c.text)
        pno = None if c.page is None else c.page - 1
        findings.extend(_invisible_unicode_finding(norm, [], pno, opt, carrier=c.carrier, location=f"in {c.location}"))
        ml_matches = opt.ml.detect(norm.text) if opt.ml and c.carrier != "javascript" else []
        for start, end, matches in _merged_matches(norm.text, opt, ml_matches):
            # The classifier alone over-fires on short labels about prompts ("prompt data details").
            classifier_only = all(m.rule_id == "ML-CLS" for m in matches)
            findings.append(
                Finding(
                    severity=Severity.LOW if classifier_only else Severity.MEDIUM,
                    carrier=c.carrier,
                    text=_with_context(norm.text, start, end, opt.context_chars),
                    page=c.page,
                    techniques=[Technique.NON_VISUAL],
                    semantic_score=max(m.score for m in matches),
                    rules=sorted({f"{m.rule_id}:{m.label}" for m in matches}),
                    detail=f"injection-like text in {c.location} (not shown as page content)"
                    + (" — classifier only, unconfirmed" if classifier_only else ""),
                )
            )
    return findings
