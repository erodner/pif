"""Text carriers that a PDF viewer does not show as page content but LLM pipelines may ingest."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

MAX_EMBEDDED_BYTES = 2_000_000


@dataclass
class CarrierText:
    carrier: str  # metadata, xmp, annotation, form_field, bookmark, embedded_file, javascript
    location: str
    text: str
    page: int | None = None  # 1-based


def iter_carriers(doc: pymupdf.Document):
    """Yield every non-page-content text in the document."""
    for key, value in (doc.metadata or {}).items():
        if value and key not in ("format", "encryption"):
            yield CarrierText("metadata", f"Info/{key}", str(value))

    try:
        xmp = doc.get_xml_metadata()
    except Exception:
        xmp = ""
    if xmp:
        text = re.sub(r"<[^>]+>", " ", xmp)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            yield CarrierText("xmp", "XMP", text)

    for pno in range(doc.page_count):
        page = doc[pno]
        for annot in page.annots() or []:
            info = annot.info or {}
            parts = [info.get(k, "") for k in ("content", "title", "subject")]
            text = " ".join(p for p in parts if p).strip()
            if text:
                yield CarrierText("annotation", f"page {pno + 1} {annot.type[1]}", text, pno + 1)
        for w in page.widgets() or []:
            parts = [w.field_name or "", str(w.field_value or ""), w.field_label or ""]
            text = " ".join(p for p in parts if p).strip()
            if text:
                yield CarrierText("form_field", f"page {pno + 1} field {w.field_name}", text, pno + 1)

    for level, title, pno, *_ in doc.get_toc(simple=False) or []:
        if title:
            yield CarrierText("bookmark", f"outline level {level}", title, pno if pno > 0 else None)

    for name in doc.embfile_names() or []:
        try:
            info = doc.embfile_info(name)
            desc = " ".join(str(info.get(k, "")) for k in ("filename", "description")).strip()
            if desc:
                yield CarrierText("embedded_file", f"embedded {name}", desc)
            if info.get("size", 0) <= MAX_EMBEDDED_BYTES:
                data = doc.embfile_get(name)
                text = _decode_if_text(data)
                if text:
                    yield CarrierText("embedded_file", f"embedded {name} content", text)
        except Exception:
            continue

    yield from _javascript(doc)


def _javascript(doc: pymupdf.Document):
    for xref in range(1, doc.xref_length()):
        try:
            kind, value = doc.xref_get_key(xref, "JS")
        except Exception:
            continue
        if kind == "null":
            continue
        code = ""
        if kind == "xref":
            try:
                code = doc.xref_stream(int(value.split()[0])).decode("latin-1", "replace")
            except Exception:
                code = ""
        elif kind == "string":
            code = value
        yield CarrierText("javascript", f"xref {xref}", code or "(JavaScript action)")


def _decode_if_text(data: bytes) -> str:
    if not data:
        return ""
    sample = data[:4096]
    if b"\x00" in sample and not sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return ""
    for enc in ("utf-8", "utf-16"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return ""
    printable = sum(c.isprintable() or c.isspace() for c in text[:4096])
    return text if printable / max(1, min(len(text), 4096)) > 0.9 else ""
