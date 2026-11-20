"""Self-contained HTML report with page crops that outline every finding.

All text pulled from PDFs is attacker-controlled and is HTML-escaped everywhere.
"""

from __future__ import annotations

import base64
import datetime as _dt
from html import escape
from pathlib import Path

import pymupdf

from .. import __version__
from ..model import Finding, Report, Severity

MAX_CROPS = 300
CROP_ZOOM = 2.0
CROP_PAD = 18.0
MAX_CROP_HEIGHT_PT = 260.0
MIN_CROP_W_PT = 320.0
MIN_CROP_H_PT = 90.0

_CSS = """
:root{--bg:#f7f7f8;--card:#fff;--fg:#1b1d21;--muted:#646a73;--line:#e3e5e8;--code:#f0f1f3;
--high:#c62828;--high-bg:#fdecea;--medium:#b26a00;--medium-bg:#fff4e0;--low:#2f6db5;--low-bg:#e8f0fb;
--info:#5f6b7a;--info-bg:#eef0f3;--ok:#2e7d32}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121316;--card:#1b1d21;--fg:#e7e9ec;
--muted:#9aa1ab;--line:#2c2f35;--code:#24272c;--high:#ff6b6b;--high-bg:#3a1d1d;--medium:#ffb547;
--medium-bg:#3a2c14;--low:#7fb0ff;--low-bg:#182a42;--info:#a5adb8;--info-bg:#25282d;--ok:#6fcf73}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}
.muted{color:var(--muted)}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px;margin:16px 0}.stats{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px}
.stat{flex:1 1 120px;border-radius:8px;padding:10px 12px;background:var(--info-bg)}
.stat b{display:block;font-size:22px}.stat.high{background:var(--high-bg);color:var(--high)}
.stat.medium{background:var(--medium-bg);color:var(--medium)}.stat.low{background:var(--low-bg);color:var(--low)}
.stat.clean{color:var(--ok)}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:6px 8px;
border-bottom:1px solid var(--line);vertical-align:top}th{font-weight:600;color:var(--muted);font-size:12px;
text-transform:uppercase;letter-spacing:.04em}.badge{display:inline-block;padding:1px 8px;border-radius:99px;
font-size:12px;font-weight:600}.badge.high{background:var(--high-bg);color:var(--high)}
.badge.medium{background:var(--medium-bg);color:var(--medium)}.badge.low{background:var(--low-bg);color:var(--low)}
.badge.info,.badge.none{background:var(--info-bg);color:var(--info)}.badge.error{background:var(--high-bg);color:var(--high)}
details>summary{cursor:pointer;list-style:none;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
details>summary::-webkit-details-marker{display:none}.path{font-weight:600;word-break:break-all}
.finding{border-top:1px solid var(--line);padding:14px 0}.finding:first-of-type{border-top:0}
.meta{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.tag{font-size:12px;padding:1px 6px;border-radius:4px;
background:var(--code);color:var(--muted)}pre{white-space:pre-wrap;word-break:break-word;background:var(--code);
padding:10px;border-radius:6px;margin:8px 0;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}
.crop{margin-top:8px}.crop img{max-width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}
.crop figcaption{font-size:12px;color:var(--muted)}a{color:var(--low)}
@media (max-width:600px){td:nth-child(3),th:nth-child(3){display:none}}
"""


def render(reports: list[Report], max_crops: int = MAX_CROPS) -> str:
    budget = [max_crops]
    total = len(reports)
    counts = {s: sum(1 for r in reports if r.max_severity is s) for s in Severity}
    clean = sum(1 for r in reports if r.max_severity is None and not r.errors)
    errors = sum(1 for r in reports if r.errors and not r.findings)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    out = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        "<meta name=viewport content='width=device-width,initial-scale=1'>",
        "<title>Prompt Injection Report</title>",
        f"<style>{_CSS}</style></head><body><main>",
        "<h1>Prompt injection scan</h1>",
        f"<div class=muted>{total} PDF(s) · generated {now} · promptinjectorfinder {escape(__version__)}</div>",
        "<div class=stats>",
        f"<div class='stat high'><b>{counts[Severity.HIGH]}</b>high</div>",
        f"<div class='stat medium'><b>{counts[Severity.MEDIUM]}</b>medium</div>",
        f"<div class='stat low'><b>{counts[Severity.LOW]}</b>low</div>",
        f"<div class='stat clean'><b>{clean}</b>clean</div>",
        f"<div class=stat><b>{errors}</b>errors</div>",
        "</div>",
    ]

    ordered = sorted(
        enumerate(reports),
        key=lambda ir: (-(ir[1].max_severity.rank if ir[1].max_severity else -1), ir[0]),
    )
    out.append("<div class=card><table><thead><tr><th>File</th><th>Result</th><th>Pages</th></tr></thead><tbody>")
    for i, r in ordered:
        out.append(f"<tr><td><a href='#f{i}'>{escape(Path(r.path).name)}</a></td><td>{_badge(r)}</td><td>{r.pages}</td></tr>")
    out.append("</tbody></table></div>")

    for i, r in ordered:
        out.append(_file_section(i, r, budget))
    if budget[0] <= 0:
        out.append(f"<p class=muted>Page previews limited to {max_crops}; later findings are shown without images.</p>")
    out.append("</main></body></html>")
    return "\n".join(out)


def _badge(r: Report) -> str:
    if r.errors and not r.findings:
        return "<span class='badge error'>error</span>"
    ms = r.max_severity
    if ms is None:
        return "<span class='badge none'>clean</span>"
    return f"<span class='badge {ms.value}'>{ms.value}</span> <span class=muted>{len(r.findings)} finding(s)</span>"


def _file_section(i: int, r: Report, budget: list[int]) -> str:
    parts = [f"<div class=card id='f{i}'><details{' open' if r.findings or r.errors else ''}><summary>"]
    parts.append(f"<span class=path>{escape(r.path)}</span>{_badge(r)}<span class=muted>{r.pages} pages · {r.seconds:.1f}s</span></summary>")
    for e in r.errors:
        parts.append(f"<pre>{escape(e)}</pre>")
    doc = None
    if r.findings and Path(r.path).is_file():
        try:
            doc = pymupdf.open(r.path, filetype="pdf")
        except Exception:  # noqa: BLE001
            doc = None
    try:
        for f in r.findings:
            parts.append(_finding(f, doc, budget))
    finally:
        if doc is not None:
            doc.close()
    parts.append("</details></div>")
    return "".join(parts)


def _finding(f: Finding, doc, budget: list[int]) -> str:
    where = f"page {f.page}" if f.page else ""
    tags = "".join(f"<span class=tag>{escape(t.value)}</span>" for t in f.techniques)
    rules = "".join(f"<span class=tag>{escape(x)}</span>" for x in f.rules)
    html = [
        "<div class=finding><div class=meta>",
        f"<span class='badge {f.severity.value}'>{f.severity.value}</span>",
        f"<b>{escape(f.carrier)}</b><span class=muted>{escape(where)}</span>{tags}</div>",
        f"<div class=muted>{escape(f.detail)}</div>",
    ]
    if rules:
        html.append(f"<div class=meta style='margin-top:4px'>{rules}</div>")
    html.append(f"<pre>{escape(f.text[:3000])}</pre>")
    if doc is not None and f.page and f.bboxes and budget[0] > 0:
        img = _crop(doc, f)
        if img:
            budget[0] -= 1
            html.append(
                "<figure class=crop><img alt='page region' src='data:image/png;base64,"
                f"{img}'><figcaption>What a reader sees on page {f.page}; the red boxes show where the extracted text is drawn.</figcaption></figure>"
            )
    html.append("</div>")
    return "".join(html)


def _crop(doc, f: Finding) -> str | None:
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
    zoom = min(CROP_ZOOM, 1400 / max(clip.width, 1))
    pix = tp.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    tmp.close()
    return base64.b64encode(pix.tobytes("png")).decode("ascii")
