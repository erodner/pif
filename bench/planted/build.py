"""Build PlantedPI-PDF: real-world prompt-injection and hard-benign texts planted into PDFs.

Sources (pinned revision + SHA-256):
  * deepset/prompt-injections (Apache-2.0): 662 prompts labelled injection / benign, ~31% German.
  * leolee99/NotInject (MIT): 339 *benign* prompts full of injection trigger words
    ("ignore", "bypass", "uncensored", …); a quarter in Chinese. These are hard negatives.

Every evaluation unit is a **triad** built from one synthetic host document (English or German;
paper, CV, memo or datasheet):
  clean    – host only                                             label 0
  benign   – host + benign text, planted with technique T           label 0  (matched confounder)
  injected – host + injection text, planted with the same T         label 1

Techniques cover hidden page text (12 variants), non-visual carriers (metadata, annotation)
and visible text (2 variants). Every planted text is verified to be extractable; triads that fail
are dropped and logged. Builds are deterministic: same inputs + seed + PyMuPDF version → the same
bytes (checked with `--check-reproducible`).

    python bench/planted/build.py                  # -> bench/data/planted/v1/
    python bench/planted/build.py --check-reproducible
"""

from __future__ import annotations

import argparse
import codecs
import collections
import hashlib
import json
import random
import re
import shutil
import sys
import tempfile
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from hosts import GENRES, compose  # noqa: E402

VERSION = "v1"
SEED = 20261120
FIXED_DATE = "D:20260101000000Z"

SOURCES = {
    "deepset_train": ("deepset/prompt-injections", "4f61ecb038e9c3fb77e21034b22511b523772cdd",
                      "data/train-00000-of-00001-9564e8b05b4757ab.parquet",
                      "2e10bc7ab30f542c97e4e83e2a5683000b5057d25ec10908784c631d44124c04"),
    "deepset_test": ("deepset/prompt-injections", "4f61ecb038e9c3fb77e21034b22511b523772cdd",
                     "data/test-00000-of-00001-701d16158af87368.parquet",
                     "39ac797cabc157eeed58435a08593b2952bb6cb16fc394a2d383f447cc7b246e"),
    "notinject_one": ("leolee99/NotInject", "847ae76cf8fea5ed325429e569ae8cfef022d2e0",
                      "data/NotInject_one-00000-of-00001.parquet",
                      "5b1d3a8ec341205305efd8c6d2cabeb5ba0f594dd8726b08ee7fde1a46ddc6ec"),
    "notinject_two": ("leolee99/NotInject", "847ae76cf8fea5ed325429e569ae8cfef022d2e0",
                      "data/NotInject_two-00000-of-00001.parquet",
                      "a5a8c1b3b851b0b5acc3b6caf8bfee26d7da631b2967dd31ca90358df8883feb"),
    "notinject_three": ("leolee99/NotInject", "847ae76cf8fea5ed325429e569ae8cfef022d2e0",
                        "data/NotInject_three-00000-of-00001.parquet",
                        "d5c685b123570c092a0f374ba6bdf324b2026d905a2751a243eb2bb360d411a8"),
}

HIDDEN = ["white", "near_white", "tiny", "render_invisible", "zero_opacity", "off_page", "hidden_layer",
          "covered", "clipped", "microglyph", "split_words", "glyph_remap"]
NONVISUAL = ["metadata", "annotation"]
VISIBLE = ["visible", "visible_small"]
TECHNIQUES = HIDDEN + NONVISUAL + VISIBLE
CHANNEL = {**{t: "hidden" for t in HIDDEN}, **{t: "nonvisual" for t in NONVISUAL}, **{t: "visible" for t in VISIBLE}}
TECHNIQUES_PER_INJECTION = {"dev": 3, "test": 6}

DE_HINT = re.compile(r"\b(der|die|das|und|ich|nicht|ist|wie|ein|eine|mit|für|sie|du|auf|zu|vergiss|alle|bitte|sind|oder)\b|[äöüß]", re.I)


# ----------------------------------------------------------------------------- sources


def fetch_sources(src_dir: Path) -> None:
    src_dir.mkdir(parents=True, exist_ok=True)
    for key, (repo, rev, path, sha) in SOURCES.items():
        out = src_dir / f"{key}.parquet"
        if not out.exists():
            url = f"https://huggingface.co/datasets/{repo}/resolve/{rev}/{path}"
            req = urllib.request.Request(url, headers={"User-Agent": "pif-benchmark"})
            out.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        if hashlib.sha256(out.read_bytes()).hexdigest() != sha:
            raise SystemExit(f"checksum mismatch for {key}; delete {out} and retry")


@dataclass
class Payload:
    pid: str
    text: str
    label: int
    source: str
    lang: str
    category: str = ""


def _lang(text: str) -> str:
    if re.search(r"[぀-ヿ㐀-鿿]", text):
        return "zh"
    return "de" if len(DE_HINT.findall(text)) >= 2 else "en"


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r", " ")
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text)  # emoji do not survive PDF fonts
    return re.sub(r"\s+", " ", text).strip()


def load_payloads(src_dir: Path) -> dict[str, dict[str, list[Payload]]]:
    import pyarrow.parquet as pq

    pools: dict[str, dict[str, list[Payload]]] = {s: {"inj": [], "deepset_benign": [], "notinject": []} for s in ("dev", "test")}
    for key, split in (("deepset_train", "dev"), ("deepset_test", "test")):
        for i, r in enumerate(pq.read_table(src_dir / f"{key}.parquet").to_pylist()):
            text = _clean(r["text"])
            if len(text) < 12:
                continue
            p = Payload(f"{key}:{i}", text, int(r["label"]), "deepset", _lang(text))
            pools[split]["inj" if p.label == 1 else "deepset_benign"].append(p)
    for key in ("notinject_one", "notinject_two", "notinject_three"):
        for i, r in enumerate(pq.read_table(src_dir / f"{key}.parquet").to_pylist()):
            text = _clean(r["prompt"])
            if len(text) < 12:
                continue
            # stable 50/50 dev/test split by content hash
            split = "dev" if int(hashlib.sha256(text.encode()).hexdigest(), 16) % 2 == 0 else "test"
            pools[split]["notinject"].append(Payload(f"{key}:{i}", text, 0, "notinject", _lang(text), r["category"]))
    return pools


# ----------------------------------------------------------------------------- PDF helpers


def _font_for(text: str) -> str:
    try:
        text.encode("latin-1")
        return "helv"
    except UnicodeEncodeError:
        return "china-s"


def _textbox(page: pymupdf.Page, rect: pymupdf.Rect, text: str, fontsize: float = 10, **kw) -> pymupdf.Rect:
    """Insert text, growing the box downwards until it fits. Returns the used rect."""
    fontname = kw.pop("fontname", None) or _font_for(text)
    r = pymupdf.Rect(rect)
    for _ in range(30):
        rc = page.insert_textbox(r, text, fontsize=fontsize, fontname=fontname, **kw)
        if rc >= 0:
            return pymupdf.Rect(r.x0, r.y0, r.x1, r.y1 - rc)
        r.y1 += max(20, -rc + 5)
    raise RuntimeError("text does not fit")


def _host_page(doc: pymupdf.Document, host: dict) -> tuple[pymupdf.Page, float]:
    page = doc.new_page(width=595, height=842)
    y = 64
    page.insert_textbox(pymupdf.Rect(60, y, 535, y + 60), host["title"], fontsize=16, fontname="hebo", align=1)
    y += 46
    page.insert_textbox(pymupdf.Rect(60, y, 535, y + 20), host["header"], fontsize=10, fontname="helv", align=1,
                        color=(0.3, 0.3, 0.3))
    y += 34
    for para in host["paragraphs"]:
        used = _textbox(page, pymupdf.Rect(60, y, 535, y + 60), para, fontsize=10.5)
        y = used.y1 + 12
    return page, y


def _escape_pdf(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _add_tounicode(doc: pymupdf.Document, font_xref: int, mapping: dict[str, str]) -> None:
    pairs = "\n".join(f"<{ord(code):02X}> <{ord(uni):04X}>" for code, uni in sorted(mapping.items()))
    cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /Remap def /CMapType 2 def\n"
            "1 begincodespacerange <00> <FF> endcodespacerange\n"
            f"{len(mapping)} beginbfchar\n{pairs}\nendbfchar\nendcmap CMapName currentdict /CMap defineresource pop end end")
    sx = doc.get_new_xref()
    doc.update_object(sx, "<<>>")
    doc.update_stream(sx, cmap.encode())
    doc.xref_set_key(font_xref, "ToUnicode", f"{sx} 0 R")


def effective_technique(technique: str, text: str) -> str:
    """clipped needs Latin-1 text, glyph_remap ASCII; otherwise fall back to white text."""
    if technique == "clipped" and _font_for(text) != "helv":
        return "white"
    if technique == "glyph_remap" and not text.isascii():
        return "white"
    return technique


def plant(doc: pymupdf.Document, page: pymupdf.Page, y: float, text: str, technique: str, rng: random.Random) -> str:
    """Plant `text` with `technique`. Returns the technique actually used (fallbacks for non-Latin text)."""
    latin = _font_for(text) == "helv"
    slot = pymupdf.Rect(60, y, 535, y + 40)
    technique = effective_technique(technique, text)

    if technique == "white":
        _textbox(page, slot, text, color=(1, 1, 1))
    elif technique == "near_white":
        _textbox(page, slot, text, color=(0.985, 0.985, 0.985))
    elif technique == "tiny":
        _textbox(page, slot, text, fontsize=0.6)
    elif technique == "render_invisible":
        _textbox(page, slot, text, render_mode=3)
    elif technique == "zero_opacity":
        _textbox(page, slot, text, fill_opacity=0.0)
    elif technique == "off_page":
        _textbox(page, pymupdf.Rect(60, page.rect.height + 40, 535, page.rect.height + 80), text)
    elif technique == "hidden_layer":
        ocg = doc.add_ocg("annotations", on=False)
        _textbox(page, slot, text, oc=ocg)
    elif technique == "covered":
        used = _textbox(page, slot, text)
        page.draw_rect(used + (-2, -2, 2, 2), color=None, fill=(1, 1, 1), overlay=True)
    elif technique == "clipped":
        page.insert_text((0, 0), " ", fontsize=1, fontname="helv", render_mode=3)  # registers /helv
        xref = page.get_contents()[-1]
        content = f"q 0 0 0 0 re W n BT /helv 10 Tf 60 {page.rect.height - y - 12:.1f} Td ({_escape_pdf(text)}) Tj ET Q"
        doc.update_stream(xref, doc.xref_stream(xref) + b"\n" + content.encode("latin-1"))
    elif technique == "microglyph":
        font = "helv" if latin else "china-s"
        x, yy = 1.5, page.rect.height - 30
        for ch in text:
            if not ch.isspace():
                page.insert_text((x, yy), ch, fontsize=0.5, fontname=font)
            yy += 0.55
    elif technique == "split_words":
        font = "helv" if latin else "china-s"
        x, yy = 60.0, y + 10
        for word in text.split():
            page.insert_text((x, yy), word, fontsize=9, fontname=font, color=(1, 1, 1))
            x += pymupdf.get_text_length(word + " ", fontname="helv", fontsize=9) if latin else 9 * (len(word) + 1)
            if x > 500:
                x, yy = 60.0, yy + 11
    elif technique == "glyph_remap":
        rot = codecs.encode(text, "rot13")
        _textbox(page, slot, rot, fontname="cour", fontsize=9)
        font_xref = next(f[0] for f in page.get_fonts() if f[3] == "Courier")
        letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        _add_tounicode(doc, font_xref, {codecs.encode(c, "rot13"): c for c in letters})
    elif technique == "metadata":
        md = doc.metadata or {}
        md.update({"subject": text, "keywords": ""})
        doc.set_metadata(md)
    elif technique == "annotation":
        a = page.add_text_annot((540, 70), text, icon="Note")
        a.set_info(title="Reviewer")
        a.update()
    elif technique == "visible":
        _textbox(page, slot, text, fontsize=10.5)
    elif technique == "visible_small":
        _textbox(page, slot, text, fontsize=6.5, color=(0.45, 0.45, 0.45))
    else:
        raise ValueError(technique)
    return technique


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", s).lower() if c.isalnum())


def extractable(path: Path, text: str) -> bool:
    """The planted text must be readable by a text-extraction pipeline (layers forced on)."""
    from pif.extract.pdf_text import extract_spans

    with pymupdf.open(path) as d:
        parts = [sp.text for spans in extract_spans(d).values() for sp in spans]
        parts += [str(v) for v in (d.metadata or {}).values() if v]
        for pg in d:
            parts += [(a.info or {}).get("content", "") for a in pg.annots() or []]
    hay = _norm(" ".join(parts))
    needle = _norm(text)[:60]
    return bool(needle) and needle in hay


def save(doc: pymupdf.Document, path: Path, title: str) -> str:
    md = doc.metadata or {}
    md.update({"title": title, "author": "PlantedPI-PDF", "producer": "PlantedPI-PDF builder", "creator": "",
               "creationDate": FIXED_DATE, "modDate": FIXED_DATE})
    doc.set_metadata(md)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=4, deflate=True, no_new_id=True)
    doc.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------- build


def build(out: Path, src_dir: Path, limit: int | None = None) -> dict:
    fetch_sources(src_dir)
    pools = load_payloads(src_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "pdfs").mkdir(parents=True)
    manifest, dropped = [], []
    for split in ("dev", "test"):
        rng = random.Random(f"{SEED}-{split}")
        inj = sorted(pools[split]["inj"], key=lambda p: p.pid)
        if limit:
            inj = inj[:limit]
        k = TECHNIQUES_PER_INJECTION[split]
        schedule = []
        for i in range(len(inj) * k):
            if i % len(TECHNIQUES) == 0:
                cycle = list(TECHNIQUES)
                rng.shuffle(cycle)
            schedule.append(cycle[i % len(TECHNIQUES)])
        benign_ni = sorted(pools[split]["notinject"], key=lambda p: p.pid)
        benign_ds = sorted(pools[split]["deepset_benign"], key=lambda p: p.pid)
        benign_ds_de = [p for p in benign_ds if p.lang == "de"]
        n = 0
        for i, p_inj in enumerate(inj):
            for j in range(k):
                technique = schedule[i * k + j]
                tid = f"{split}-{n:04d}"
                n += 1
                # resolve fallbacks from the injection, then pick a benign text that survives the same technique
                technique = effective_technique(technique, p_inj.text)
                fits = lambda p, t=technique: effective_technique(t, p.text) == t  # noqa: E731
                if p_inj.lang == "de" and rng.random() < 0.7:
                    p_ben = rng.choice([p for p in benign_ds_de if fits(p)] or benign_ds_de)
                elif rng.random() < 0.6:
                    p_ben = rng.choice([p for p in benign_ni if fits(p)])
                else:
                    p_ben = rng.choice([p for p in benign_ds if fits(p)])
                host_lang = ("de" if rng.random() < 0.75 else "en") if p_inj.lang == "de" else ("en" if rng.random() < 0.85 else "de")
                genre = rng.choice(GENRES)
                host = compose(rng, host_lang, genre)
                triad = []
                for role, payload in (("clean", None), ("benign", p_ben), ("injected", p_inj)):
                    doc = pymupdf.open()
                    page, y = _host_page(doc, host)
                    used = technique
                    if payload is not None:
                        used = plant(doc, page, y, payload.text, technique, random.Random(f"{tid}-{role}"))
                    rel = Path("pdfs") / split / f"{tid}.{role}.pdf"
                    sha = save(doc, out / rel, host["title"])
                    ok = payload is None or extractable(out / rel, payload.text)
                    triad.append({
                        "pdf_id": f"{tid}.{role}", "path": str(rel), "sha256": sha, "split": split, "triad_id": tid,
                        "role": role, "label": int(role == "injected"), "technique": used,
                        "channel": CHANNEL[used] if payload is not None else "none",
                        "host_lang": host_lang, "genre": genre,
                        "payload_source": payload.source if payload else None,
                        "payload_id": payload.pid if payload else None,
                        "payload_lang": payload.lang if payload else None,
                        "notinject_category": payload.category if payload else None,
                        "payload_text": payload.text if payload else None,
                        "verified": ok,
                    })
                if all(t["verified"] for t in triad):
                    # benign/injected must use the same technique after fallbacks
                    if triad[1]["technique"] != triad[2]["technique"]:
                        dropped.append({"triad_id": tid, "reason": "technique fallback differs"})
                    else:
                        manifest.extend(triad)
                        continue
                else:
                    dropped.append({"triad_id": tid, "reason": "planted text not extractable",
                                    "technique": technique, "roles": [t["role"] for t in triad if not t["verified"]]})
                for t in triad:
                    (out / t["path"]).unlink(missing_ok=True)

    with (out / "manifest.jsonl").open("w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "dropped.json").write_text(json.dumps(dropped, indent=2))
    sums = "".join(f"{r['sha256']}  {r['path']}\n" for r in manifest)
    (out / "SHA256SUMS").write_text(sums)
    stats = _stats(manifest, dropped)
    (out / "DATASET_CARD.md").write_text(_card(stats), encoding="utf-8")
    return stats


def _stats(manifest: list[dict], dropped: list[dict]) -> dict:
    s = {"pdfs": len(manifest), "dropped_triads": len(dropped), "by_split": {}}
    for split in ("dev", "test"):
        rows = [r for r in manifest if r["split"] == split]
        inj = [r for r in rows if r["role"] == "injected"]
        ben = [r for r in rows if r["role"] == "benign"]
        s["by_split"][split] = {
            "triads": len(inj),
            "pdfs": len(rows),
            "technique": dict(sorted(collections.Counter(r["technique"] for r in inj).items())),
            "channel": dict(collections.Counter(r["channel"] for r in inj)),
            "injection_lang": dict(collections.Counter(r["payload_lang"] for r in inj)),
            "benign_source": dict(collections.Counter(r["payload_source"] for r in ben)),
            "benign_lang": dict(collections.Counter(r["payload_lang"] for r in ben)),
            "host_lang": dict(collections.Counter(r["host_lang"] for r in inj)),
            "genre": dict(collections.Counter(r["genre"] for r in inj)),
        }
    s["dataset_sha256"] = hashlib.sha256("".join(r["sha256"] for r in manifest).encode()).hexdigest()
    s["pymupdf"] = pymupdf.VersionBind
    return s


def _card(stats: dict) -> str:
    def table(d: dict) -> str:
        return ", ".join(f"{k} {v}" for k, v in d.items())

    lines = [
        f"# PlantedPI-PDF {VERSION}",
        "",
        "Real prompt-injection texts and hard benign texts, planted into synthetic PDF host documents "
        "with 16 techniques (hidden, non-visual and visible). Built by `bench/planted/build.py` "
        f"(seed {SEED}); PyMuPDF {stats['pymupdf']}. Dataset fingerprint: `{stats['dataset_sha256'][:16]}`.",
        "",
        "## Sources",
        "",
        "| Source | Revision | License | Used as |",
        "|---|---|---|---|",
        "| [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections) | `4f61ecb` | Apache-2.0 | injections (label 1) and benign prompts; train→dev, test→test |",
        "| [leolee99/NotInject](https://huggingface.co/datasets/leolee99/NotInject) | `847ae76` | MIT | hard benign prompts with trigger words; 50/50 dev/test by content hash |",
        "",
        "Host documents are synthetic (fictional names), written for this benchmark (`bench/planted/hosts.py`).",
        "",
        "## Structure",
        "",
        "Each triad has one host document in three versions: `clean`, `benign` (benign text planted with technique *T*) and "
        "`injected` (injection planted with the same *T* in the same place). Labels: injected = 1, else 0.",
        "",
        f"Techniques. Hidden: {', '.join(HIDDEN)}. Non-visual: {', '.join(NONVISUAL)}. Visible: {', '.join(VISIBLE)}. "
        "Non-Latin texts fall back from `clipped`/`glyph_remap` to `white`.",
        "",
        "## Counts",
        "",
    ]
    for split, d in stats["by_split"].items():
        lines += [f"### {split}: {d['triads']} triads, {d['pdfs']} PDFs", "",
                  f"- techniques: {table(d['technique'])}",
                  f"- channels: {table(d['channel'])}",
                  f"- injection language: {table(d['injection_lang'])}",
                  f"- benign source: {table(d['benign_source'])}; benign language: {table(d['benign_lang'])}",
                  f"- host language: {table(d['host_lang'])}; genres: {table(d['genre'])}", ""]
    lines += [
        f"Dropped triads (planted text not extractable or inconsistent fallback): {stats['dropped_triads']} (see `dropped.json`).",
        "",
        "## Known limitations",
        "",
        "- deepset labels contain some noise (e.g. plain task requests such as \"Generate SQL code to access a database\" "
        "are labelled as injections). Labels are used as published.",
        "- Most deepset injections are chat-style jailbreaks, not document-style injections (\"give a positive review\"). They test "
        "how detection generalises, not peer-review attacks specifically.",
        "- Emoji are stripped from texts (PDF base fonts cannot encode them).",
        "- Host documents are one page and synthetic.",
        "",
        "## Use",
        "",
        "Tune only on `dev`; report `test`. Evaluate with `python bench/planted/evaluate.py`.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "bench/data/planted" / VERSION)
    ap.add_argument("--src", type=Path, default=ROOT / "bench/data/planted-src")
    ap.add_argument("--limit", type=int, default=None, help="injections per split (smoke test)")
    ap.add_argument("--check-reproducible", action="store_true", help="build twice and compare all hashes")
    a = ap.parse_args()
    stats = build(a.out, a.src, a.limit)
    print(json.dumps({k: v for k, v in stats.items() if k != "by_split"}, indent=2))
    for split, d in stats["by_split"].items():
        print(split, d["triads"], "triads", d["pdfs"], "PDFs")
    if a.check_reproducible:
        with tempfile.TemporaryDirectory() as tmp:
            again = build(Path(tmp) / "again", a.src, a.limit)
        same = again["dataset_sha256"] == stats["dataset_sha256"]
        print("reproducible:", same)
        if not same:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
