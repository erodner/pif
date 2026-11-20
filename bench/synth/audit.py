"""Merge, deduplicate and contamination-audit the synthetic corpus.

    python bench/synth/audit.py          # raw/*.jsonl -> corpus_v1.jsonl + AUDIT.md

Contamination check against every evaluation text we know of: deepset/prompt-injections (train+test),
NotInject (all), the PlantedPI-PDF host-document sentences, and the hidden payload/confounder texts of
the CrackedPDFs validation/test splits (taken from cached scan results). A synthetic text is dropped if it is too close to any of them:
cosine similarity ≥ 0.90 (MiniLM) or a shared run of ≥ 8 words.
"""

from __future__ import annotations

import collections
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

COS_MAX = 0.90
NGRAM = 8
NEAR_DUP = 0.95
WRAP = re.compile(r"\[[A-Za-z_]{2,40}=[^\]]{0,120}\]|</?[A-Za-z_][A-Za-z0-9_:.-]{1,60}>")


def words(t: str) -> list[str]:
    return re.findall(r"\w+", t.lower())


def ngrams(t: str, n: int = NGRAM) -> set[tuple[str, ...]]:
    w = words(t)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def reference_texts() -> dict[str, list[str]]:
    import pyarrow.parquet as pq

    refs: dict[str, list[str]] = collections.defaultdict(list)
    src = ROOT / "bench/data/planted-src"
    for f in sorted(src.glob("deepset_*.parquet")):
        refs["deepset"] += [r["text"] for r in pq.read_table(f).to_pylist()]
    for f in sorted(src.glob("notinject_*.parquet")):
        refs["notinject"] += [r["prompt"] for r in pq.read_table(f).to_pylist()]
    sys.path.insert(0, str(ROOT / "bench/planted"))
    from hosts import TEXT  # PlantedPI-PDF host documents are evaluation data too

    for lang in TEXT.values():
        for genre in lang.values():
            refs["planted_hosts"] += genre["sentences"] + genre["titles"] + genre["header"]
    for cache in glob.glob(str(ROOT / "bench/results/**/*-R.jsonl"), recursive=True):
        if "planted" in cache:
            continue
        for line in open(cache):
            for fd in json.loads(line)["findings"]:
                t = WRAP.sub(" ", fd["text"])
                if len(t.split()) >= 4:
                    refs["crackedpdfs"].append(t)
    return {k: sorted(set(v)) for k, v in refs.items()}


def main() -> None:
    from pif.ml.cascade import MLCascade, _strip_markup

    rows = []
    for f in sorted(glob.glob(str(HERE / "raw" / "*.jsonl"))):
        for i, line in enumerate(open(f, encoding="utf-8")):
            if line.strip():
                r = json.loads(line)
                r["origin"] = f"{Path(f).stem}:{i}"
                rows.append(r)
    n_raw = len(rows)

    # exact duplicates (case/punctuation-insensitive)
    seen, uniq = set(), []
    for r in rows:
        key = " ".join(words(r["text"]))
        if key and key not in seen:
            seen.add(key)
            uniq.append(r)
    n_exact = n_raw - len(uniq)

    c = MLCascade.load(classifier=None)
    emb = c.embedder
    vec = emb.encode([_strip_markup(r["text"]) for r in uniq])

    # near duplicates inside the corpus (keep first)
    keep = np.ones(len(uniq), dtype=bool)
    sims = vec @ vec.T
    for i in range(len(uniq)):
        if keep[i]:
            dup = np.where(sims[i, i + 1:] >= NEAR_DUP)[0] + i + 1
            keep[dup] = False
    n_near = int((~keep).sum())
    uniq = [r for r, k in zip(uniq, keep) if k]
    vec = vec[keep]

    refs = reference_texts()
    dropped = collections.Counter()
    examples = []
    ok = np.ones(len(uniq), dtype=bool)
    nearest = np.zeros(len(uniq))
    for name, texts in refs.items():
        rv = emb.encode([WRAP.sub(" ", _strip_markup(t)) for t in texts])
        cos = vec @ rv.T
        best = cos.max(axis=1)
        arg = cos.argmax(axis=1)
        nearest = np.maximum(nearest, best)
        ref_ngrams = set().union(*(ngrams(t) for t in texts)) if texts else set()
        for i, r in enumerate(uniq):
            hit_cos = best[i] >= COS_MAX
            hit_ng = bool(ngrams(r["text"]) & ref_ngrams)
            if (hit_cos or hit_ng) and ok[i]:
                ok[i] = False
                dropped[name] += 1
                if len(examples) < 15:
                    examples.append((name, round(float(best[i]), 3), r["text"][:120], texts[arg[i]][:120]))
    corpus = [r for r, k in zip(uniq, ok) if k]

    out = HERE / "corpus_v1.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in corpus:
            fh.write(json.dumps({k: r[k] for k in ("text", "label", "intent", "category", "lang", "style", "origin") if k in r},
                                ensure_ascii=False) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()

    lab = collections.Counter(r["label"] for r in corpus)
    langs = collections.Counter((r["label"], r["lang"]) for r in corpus)
    kinds = collections.Counter(r.get("intent") or r.get("category") for r in corpus)
    near_hist = np.histogram(nearest[ok], bins=[0, .5, .6, .7, .8, .85, .9])[0]
    L = ["# Synthetic corpus v1: audit", "",
         f"Raw lines: {n_raw} · exact duplicates removed: {n_exact} · near duplicates (cos ≥ {NEAR_DUP}) removed: {n_near}",
         f"Contamination drops (cos ≥ {COS_MAX} or shared {NGRAM}-gram): " + (", ".join(f"{k} {v}" for k, v in dropped.items()) or "none"),
         f"Reference texts: " + ", ".join(f"{k} {len(v)}" for k, v in refs.items()),
         "", f"**Final corpus: {len(corpus)} texts** ({lab[1]} injections, {lab[0]} benign) · sha256 `{digest[:16]}`", "",
         "By label/language: " + ", ".join(f"{'inj' if k[0] else 'ben'}/{k[1]} {v}" for k, v in sorted(langs.items())),
         "", "By intent/category: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())), "",
         "Similarity of kept texts to their nearest evaluation text (MiniLM cosine):", "",
         "| < 0.5 | 0.5–0.6 | 0.6–0.7 | 0.7–0.8 | 0.8–0.85 | 0.85–0.9 |", "|---|---|---|---|---|---|",
         "| " + " | ".join(str(int(x)) for x in near_hist) + " |", "", "Dropped examples (synthetic → nearest reference):", ""]
    for name, s, a, b in examples:
        L.append(f"- [{name}, {s}] “{a}” → “{b}”")
    (HERE / "AUDIT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:8]))


if __name__ == "__main__":
    main()
