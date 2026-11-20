"""Evaluate pif on the CrackedPDFs benchmark and compare with the published baselines.

CrackedPDFs (arXiv 2607.19396; HF volkthienpreecha/crackedpdfs, MIT): synthetic one-page PDFs
with hidden prompt injections, benign originals and matched benign confounders (hidden
benign text in the same place and style). Document-level binary labels.

    python bench/crackedpdfs.py fetch
    python bench/crackedpdfs.py run --split test --configs R,RE,REC,all -j 4
    python bench/crackedpdfs.py report --split test

Results (local, not committed): bench/results/. pif is evaluated zero-shot; nothing is tuned
on the test split.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import sys
import tarfile
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "src"))

from pif import runner  # noqa: E402
from pif.model import Severity  # noqa: E402
from pif.scanner import ScanOptions  # noqa: E402

REPO = "volkthienpreecha/crackedpdfs"
REVISION = "245bc98ec7e838346ee6fd5bdf5fed1b16d2a3e5"
URL = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{{path}}"
FILES = [
    "checksums.sha256",
    "README.md",
    "LICENSE",
    "data/metadata.jsonl",
    "data/splits.json",
    "metrics/hard_setting_summary.csv",
    *[f"metrics/{m}_per_{g}.csv" for m in ("hybrid", "rule", "promptguard")
      for g in ("attack_family", "benign_confounder_family", "message_type")],
    "pdfs/benign.tar.gz",
    "pdfs/injected.tar.gz",
]

# name -> (ml_mode, ocr_mode, embedding, classifier)
CONFIGS = {
    "R": ("off", "off", False, False),
    "RE": ("on", "off", True, False),
    "REC": ("on", "off", True, True),
    "all": ("on", "on", True, True),
}
CONFIG_LABEL = {
    "R": "pif rules (default)",
    "RE": "pif rules + embedding",
    "REC": "pif rules + embedding + classifier",
    "all": "pif all (+ OCR)",
}
SEV_RANK = {None: 0, "info": 0, "low": 1, "medium": 2, "high": 3}


# --------------------------------------------------------------------------- fetch


def fetch(data_dir: Path) -> None:
    raw = data_dir / "raw"
    for path in FILES:
        dest = raw / path
        if dest.exists() and dest.stat().st_size > 0:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        print("download", path, flush=True)
        req = urllib.request.Request(URL.format(path=path), headers={"User-Agent": "pif-benchmark"})
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as out:
            while chunk := r.read(1 << 20):
                out.write(chunk)
        tmp.replace(dest)

    expected = {}
    for line in (raw / "checksums.sha256").read_text().splitlines():
        digest, name = line.split(None, 1)
        expected[name.strip()] = digest
    for path in FILES:
        if path == "checksums.sha256" or path not in expected:
            continue
        h = hashlib.sha256()
        with (raw / path).open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != expected[path]:
            raise SystemExit(f"checksum mismatch: {path}")
    print("checksums ok")

    pdf_root = data_dir / "pdfs"
    for archive in ("benign", "injected"):
        marker = pdf_root / f".{archive}.extracted"
        if marker.exists():
            continue
        with tarfile.open(raw / "pdfs" / f"{archive}.tar.gz") as tf:
            members = []
            for m in tf.getmembers():
                name = Path(m.name)
                if name.is_absolute() or ".." in name.parts or not (m.isfile() or m.isdir()):
                    raise SystemExit(f"refusing unsafe archive member: {m.name}")
                members.append(m)
            tf.extractall(pdf_root, members=members, filter="data")
        marker.touch()
    print("pdfs extracted to", pdf_root)


# --------------------------------------------------------------------------- data


def load_rows(data_dir: Path, split: str) -> list[dict]:
    raw = data_dir / "raw"
    splits = json.loads((raw / "data/splits.json").read_text())
    ids = splits[{"test": "test_ids", "val": "val_ids", "train": "train_ids"}[split]]
    meta = {}
    with (raw / "data/metadata.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            meta[r["pdf_id"]] = r
    rows = [meta[i] for i in ids]
    for r in rows:
        r["abs_path"] = str(_resolve_pdf(data_dir / "pdfs", r["file_path"]))
    return rows


def _resolve_pdf(pdf_root: Path, file_path: str) -> Path:
    p = pdf_root / file_path
    if p.exists():
        return p
    hits = list(pdf_root.rglob(Path(file_path).name))
    if len(hits) == 1:
        return hits[0]
    raise FileNotFoundError(file_path)


# --------------------------------------------------------------------------- scanning


def _summarise(pdf_id: str, report) -> dict:
    findings = []
    score = 0.0
    for f in report.findings:
        rank = SEV_RANK[f.severity.value]
        score = max(score, (rank + 0.99 * f.semantic_score) / 4.0)
        findings.append({
            "severity": f.severity.value,
            "carrier": f.carrier,
            "techniques": [t.value for t in f.techniques],
            "rules": f.rules,
            "semantic": round(f.semantic_score, 3),
            "text": f.text[:400],
            "page": f.page,
            "bboxes": [list(b) for b in f.bboxes[:5]],
        })
    ms = report.max_severity
    return {
        "pdf_id": pdf_id,
        "max_severity": ms.value if ms else None,
        "score": round(score, 4),
        "seconds": round(report.seconds, 3),
        "errors": report.errors,
        "findings": findings,
    }


def _scan_job(args):
    pdf_id, path = args
    return _summarise(pdf_id, runner.scan_in_worker(path, ScanOptions()))


def run(data_dir: Path, out_dir: Path, split: str, configs: list[str], jobs: int, limit: int | None) -> None:
    rows = load_rows(data_dir, split)
    if limit:
        rng = random.Random(0)
        rows = rng.sample(rows, min(limit, len(rows)))
    out_dir.mkdir(parents=True, exist_ok=True)
    for cfg in configs:
        cache = out_dir / f"{split}-{cfg}.jsonl"
        done = set()
        if cache.exists():
            done = {json.loads(l)["pdf_id"] for l in cache.open()}
        todo = [(r["pdf_id"], r["abs_path"]) for r in rows if r["pdf_id"] not in done]
        print(f"[{cfg}] {len(done)} cached, {len(todo)} to scan", flush=True)
        if not todo:
            continue
        ml, ocr, emb, cls = CONFIGS[cfg]
        init = (ml, ocr, runner.threads_per_worker(jobs), emb, cls)
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=jobs, initializer=runner.worker_init, initargs=init) as ex, \
                cache.open("a") as out:
            futures = [ex.submit(_scan_job, a) for a in todo]
            for n, fut in enumerate(as_completed(futures), 1):
                out.write(json.dumps(fut.result()) + "\n")
                if n % 200 == 0 or n == len(todo):
                    rate = n / (time.time() - t0)
                    print(f"[{cfg}] {n}/{len(todo)}  {rate:.1f} docs/s", flush=True)


# --------------------------------------------------------------------------- metrics


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    """Mann-Whitney U formulation, ties counted as 1/2."""
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    allv = np.concatenate([pos, neg])[order]
    ranks = np.empty(len(allv))
    i = 0
    while i < len(allv):  # average ranks for ties
        j = i
        while j + 1 < len(allv) and allv[j + 1] == allv[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1
        i = j + 1
    r = np.empty(len(allv))
    r[order] = ranks
    rpos = r[: len(pos)].sum()
    return float((rpos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def average_precision(y: np.ndarray, s: np.ndarray) -> float:
    """Step-wise AP (sklearn definition); tied scores are processed as one threshold."""
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-s, kind="mergesort")
    ys, ss = y[order], s[order]
    distinct = np.r_[np.where(np.diff(ss))[0], len(ss) - 1]
    tp = np.cumsum(ys)[distinct]
    fp = (distinct + 1) - tp
    precision = tp / (tp + fp)
    recall = tp / y.sum()
    prev = np.r_[0, recall[:-1]]
    return float(np.sum((recall - prev) * precision))


def binary_metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "accuracy": (tp + tn) / len(y),
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p + r else 0.0,
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def _selftest_metrics() -> None:
    y = np.array([1, 1, 0, 0])
    assert roc_auc(y, np.array([0.9, 0.8, 0.3, 0.1])) == 1.0
    assert roc_auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 0.0
    assert roc_auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5
    assert abs(roc_auc(np.array([1, 0, 1, 0]), np.array([0.8, 0.6, 0.4, 0.2])) - 0.75) < 1e-9
    assert abs(average_precision(np.array([1, 0, 1, 0]), np.array([0.8, 0.6, 0.4, 0.2])) - (1 + 2 / 3) / 2) < 1e-9
    m = binary_metrics(np.array([1, 1, 0, 0]), np.array([1, 0, 1, 0]))
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1) and m["f1"] == 0.5


# --------------------------------------------------------------------------- report


def _load_results(out_dir: Path, split: str, cfg: str) -> dict[str, dict]:
    path = out_dir / f"{split}-{cfg}.jsonl"
    if not path.exists():
        return {}
    return {d["pdf_id"]: d for d in (json.loads(l) for l in path.open())}


def _evaluate(rows: list[dict], res: dict[str, dict], shuffle: bool = False) -> dict:
    rows = [r for r in rows if r["pdf_id"] in res]
    y = np.array([r["label"] for r in rows])
    if shuffle:
        y = np.random.default_rng(0).permutation(y)
    s = np.array([res[r["pdf_id"]]["score"] for r in rows])
    sev = np.array([SEV_RANK[res[r["pdf_id"]]["max_severity"]] for r in rows])
    out = {"n": len(rows), "roc_auc": roc_auc(y, s), "pr_auc": average_precision(y, s)}
    out["high"] = binary_metrics(y, (sev >= 3).astype(int))
    out["medium"] = binary_metrics(y, (sev >= 2).astype(int))

    # paired ranking: injected vs matched benign confounder of the same pair
    by_pair = defaultdict(dict)
    for r in rows:
        by_pair[r["pair_id"]][r["pdf_role"]] = res[r["pdf_id"]]["score"]
    wins = [1.0 if p["injected_attack"] > p["benign_confounder"] else 0.5 if p["injected_attack"] == p["benign_confounder"] else 0.0
            for p in by_pair.values() if "injected_attack" in p and "benign_confounder" in p]
    out["paired_rank_acc"] = float(np.mean(wins)) if wins else float("nan")

    def group_rate(key_fn, role, positive_sev):
        agg = defaultdict(lambda: [0, 0])
        for r in rows:
            if r["pdf_role"] != role:
                continue
            k = key_fn(r)
            agg[k][1] += 1
            agg[k][0] += SEV_RANK[res[r["pdf_id"]]["max_severity"]] >= positive_sev
        return {k: (v[0] / v[1], v[1]) for k, v in sorted(agg.items())}

    for name, sev_t in (("high", 3), ("medium", 2)):
        out[f"recall_by_family_{name}"] = group_rate(lambda r: r["attack_family"], "injected_attack", sev_t)
        out[f"recall_by_message_{name}"] = group_rate(lambda r: r["message_type"], "injected_attack", sev_t)
        out[f"fpr_by_confounder_{name}"] = group_rate(lambda r: r["benign_confounder_family"], "benign_confounder", sev_t)
        out[f"fpr_benign_original_{name}"] = group_rate(lambda r: "all", "benign_original", sev_t).get("all", (0, 0))
    out["seconds_per_doc"] = float(np.mean([res[r["pdf_id"]]["seconds"] for r in rows]))
    out["errors"] = sum(1 for r in rows if res[r["pdf_id"]]["errors"])
    return out


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def _hidden_payload(rows_by_pair: dict, row: dict) -> str:
    """Text present in this PDF but not in the benign original of the same triad."""
    import pymupdf

    from pif.extract.pdf_text import extract_spans

    def words(path):
        with pymupdf.open(path) as d:
            return " ".join(sp.text for spans in extract_spans(d).values() for sp in spans).split()

    orig = rows_by_pair[row["pair_id"]].get("benign_original")
    mine = words(row["abs_path"])
    if not orig:
        return " ".join(mine)[-300:]
    base = Counter(words(orig["abs_path"]))
    extra = []
    for w in mine:
        if base[w] > 0:
            base[w] -= 1
        else:
            extra.append(w)
    return " ".join(extra)


def report(data_dir: Path, out_dir: Path, split: str, configs: list[str], shuffle_check: bool) -> Path:
    _selftest_metrics()
    rows = load_rows(data_dir, split)
    results = {c: _load_results(out_dir, split, c) for c in configs}
    results = {c: r for c, r in results.items() if r}
    if not results:
        raise SystemExit("no results yet; run `run` first")
    evals = {c: _evaluate(rows, r) for c, r in results.items()}
    metrics_dir = data_dir / "raw" / "metrics"
    base = {r["name"]: r for r in _read_csv(metrics_dir / "hard_setting_summary.csv") if r.get("setting") == "heldout_provenance"}

    def f(x, d=3):
        return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"

    L = [f"# pif on CrackedPDFs ({split} split)", ""]
    L.append(f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} · dataset `{REPO}` @ `{REVISION[:12]}` · "
             f"{len(rows)} documents in split ({sum(r['label'] for r in rows)} injected)")
    L.append("")
    L.append("pif is evaluated **zero-shot** (no training or tuning on CrackedPDFs). The trained baselines "
             "were fitted on the CrackedPDFs train split. Document score = max over findings of "
             "(severity rank + 0.99·semantic score)/4. Operating points: a document counts as *injected* "
             "if pif reports a HIGH finding (strict) or at least MEDIUM (sensitive).")
    L.append("")
    L.append("## Overall")
    L.append("")
    L.append("| Detector | Accuracy | Precision | Recall | F1 | FPR | ROC-AUC | PR-AUC | Paired rank |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name, label in (("hybrid", "Hybrid text+structure (trained, paper)"), ("rule", "Rule baseline (paper)"),
                        ("promptguard", "PromptGuard on extracted text (paper)")):
        b = base.get(name)
        if b:
            prec, rec = float(b["precision"]), float(b["recall"])
            neg = len(rows) - sum(r["label"] for r in rows)
            pos = sum(r["label"] for r in rows)
            tp = rec * pos
            fp = tp / prec - tp if prec else 0
            paired = "0.959" if name == "hybrid" else "–"
            L.append(f"| {label} | {f(float(b['accuracy']))} | {f(prec)} | {f(rec)} | {f(float(b['f1']))} | "
                     f"{f(fp / neg)} | {f(float(b['roc_auc']))} | {f(float(b['pr_auc']))} | {paired} |")
    for c, e in evals.items():
        for op in ("high", "medium"):
            m = e[op]
            L.append(f"| **{CONFIG_LABEL[c]}**, ≥{op.upper()} | {f(m['accuracy'])} | {f(m['precision'])} | "
                     f"{f(m['recall'])} | **{f(m['f1'])}** | {f(m['fpr'])} | {f(e['roc_auc'])} | {f(e['pr_auc'])} | "
                     f"{f(e['paired_rank_acc'])} |")
    L.append("")
    L.append("Paper FPR is derived from its precision/recall. ROC-AUC, PR-AUC and paired rank for pif use the continuous score, so they are the same for both operating points.")
    L.append("")
    L.append("| Config | n scanned | s/doc | scan errors | FPR on benign originals (≥HIGH / ≥MEDIUM) |")
    L.append("|---|---|---|---|---|")
    for c, e in evals.items():
        L.append(f"| {CONFIG_LABEL[c]} | {e['n']} | {e['seconds_per_doc']:.2f} | {e['errors']} | "
                 f"{f(e['fpr_benign_original_high'][0])} / {f(e['fpr_benign_original_medium'][0])} |")
    L.append("")

    # per family comparison
    def baseline_family(model: str, group: str) -> dict[str, float]:
        out = {}
        for r in _read_csv(metrics_dir / f"{model}_per_{group}.csv"):
            if r.get("regime_column") and r.get("regime_value"):
                acc = r.get("accuracy")
                out[r["regime_value"]] = float(acc) if acc not in (None, "") else float("nan")
        return out

    best = max(evals, key=lambda c: max(evals[c]["high"]["f1"], evals[c]["medium"]["f1"]))
    L.append(f"## Recall per attack family (injected documents)")
    L.append("")
    L.append("For the paper baselines this is their per-family accuracy on injected-only subsets, which equals recall.")
    L.append("")
    hyb, rule, pg = (baseline_family(m, "attack_family") for m in ("hybrid", "rule", "promptguard"))
    cols = list(evals)
    L.append("| Attack family | n | Hybrid | Rule | PromptGuard | " + " | ".join(f"{CONFIG_LABEL[c]} ≥HIGH" for c in cols) + " |")
    L.append("|---|---|---|---|---|" + "---|" * len(cols))
    fams = sorted(evals[best]["recall_by_family_high"])
    for fam in fams:
        n = evals[best]["recall_by_family_high"][fam][1]
        ours = " | ".join(f(evals[c]["recall_by_family_high"].get(fam, (float('nan'), 0))[0]) for c in cols)
        L.append(f"| {fam} | {n} | {f(hyb.get(fam))} | {f(rule.get(fam))} | {f(pg.get(fam))} | {ours} |")
    L.append("")
    L.append("## Recall per payload type (injected documents)")
    L.append("")
    hyb, rule, pg = (baseline_family(m, "message_type") for m in ("hybrid", "rule", "promptguard"))
    L.append("| Payload type | n | Hybrid | Rule | PromptGuard | " + " | ".join(f"{CONFIG_LABEL[c]} ≥HIGH" for c in cols) + " |")
    L.append("|---|---|---|---|---|" + "---|" * len(cols))
    for mt in sorted(evals[best]["recall_by_message_high"]):
        n = evals[best]["recall_by_message_high"][mt][1]
        ours = " | ".join(f(evals[c]["recall_by_message_high"].get(mt, (float('nan'), 0))[0]) for c in cols)
        L.append(f"| {mt} | {n} | {f(hyb.get(mt))} | {f(rule.get(mt))} | {f(pg.get(mt))} | {ours} |")
    L.append("")
    L.append("## False-positive rate per benign confounder family")
    L.append("")
    L.append("Confounders hide *benign* text with the same technique as the attack. Paper columns are 1 − accuracy on confounder-only subsets.")
    L.append("")
    hyb, rule, pg = (baseline_family(m, "benign_confounder_family") for m in ("hybrid", "rule", "promptguard"))
    L.append("| Confounder family | n | Hybrid | Rule | PromptGuard | " + " | ".join(f"{CONFIG_LABEL[c]} ≥HIGH" for c in cols) + " |")
    L.append("|---|---|---|---|---|" + "---|" * len(cols))
    for cf in sorted(evals[best]["fpr_by_confounder_high"]):
        n = evals[best]["fpr_by_confounder_high"][cf][1]
        ours = " | ".join(f(evals[c]["fpr_by_confounder_high"].get(cf, (float('nan'), 0))[0]) for c in cols)
        def inv(d):
            v = d.get(cf)
            return None if v is None or np.isnan(v) else 1 - v
        L.append(f"| {cf} | {n} | {f(inv(hyb))} | {f(inv(rule))} | {f(inv(pg))} | {ours} |")
    L.append("")

    # error analysis for the best config at its better operating point
    op = "high" if evals[best]["high"]["f1"] >= evals[best]["medium"]["f1"] else "medium"
    thr = 3 if op == "high" else 2
    res = results[best]
    rows_by_pair = defaultdict(dict)
    for r in rows:
        rows_by_pair[r["pair_id"]][r["pdf_role"]] = r
    fns = [r for r in rows if r["label"] == 1 and r["pdf_id"] in res and SEV_RANK[res[r["pdf_id"]]["max_severity"]] < thr]
    fps = [r for r in rows if r["label"] == 0 and r["pdf_id"] in res and SEV_RANK[res[r["pdf_id"]]["max_severity"]] >= thr]
    L.append(f"## Error analysis: {CONFIG_LABEL[best]}, ≥{op.upper()}")
    L.append("")
    L.append(f"{len(fns)} false negatives, {len(fps)} false positives.")
    L.append("")
    L.append("False negatives by attack family: " + ", ".join(f"{k} {v}" for k, v in Counter(r['attack_family'] for r in fns).most_common()))
    L.append("")
    L.append("False negatives by payload type: " + ", ".join(f"{k} {v}" for k, v in Counter(r['message_type'] for r in fns).most_common()))
    L.append("")
    L.append("False positives by role / family: " + ", ".join(
        f"{k} {v}" for k, v in Counter(f"{r['pdf_role']}:{r['benign_confounder_family']}" for r in fps).most_common()))
    L.append("")
    L.append("Our verdict for false negatives (max severity reported): " + ", ".join(
        f"{k or 'none'} {v}" for k, v in Counter(res[r['pdf_id']]['max_severity'] for r in fns).most_common()))
    L.append("")
    rng = random.Random(1)
    for title, sample in (("False negatives (sample)", rng.sample(fns, min(25, len(fns)))),
                          ("False positives (sample)", rng.sample(fps, min(25, len(fps))))):
        L.append(f"### {title}")
        L.append("")
        L.append("| pdf_id | family | payload type | pif verdict | text added vs. benign original |")
        L.append("|---|---|---|---|---|")
        for r in sample:
            d = res[r["pdf_id"]]
            verdict = d["max_severity"] or "clean"
            rules = sorted({x.split(":")[0] for fd in d["findings"] for x in fd["rules"]})
            if rules:
                verdict += " (" + ",".join(rules) + ")"
            try:
                payload = _hidden_payload(rows_by_pair, r)
            except Exception as e:  # noqa: BLE001
                payload = f"(could not extract: {e})"
            payload = re.sub(r"\s+", " ", payload).replace("|", "\\|")[:220]
            fam = r["attack_family"] if r["label"] else r["benign_confounder_family"] if r["pdf_role"] == "benign_confounder" else "original"
            L.append(f"| {r['pdf_id']} | {fam} | {r['message_type']} | {verdict} | {payload} |")
        L.append("")

    if shuffle_check:
        L.append("## Sanity check: shuffled labels")
        L.append("")
        L.append("ROC-AUC must be ≈ 0.5. F1 is compared with its chance level 2pq/(p+q), where p is the share of positive labels and q the share of documents flagged.")
        L.append("")
        for c, r in results.items():
            e = _evaluate(rows, r, shuffle=True)
            m = e["high"]
            p = (m["tp"] + m["fn"]) / e["n"]
            q = (m["tp"] + m["fp"]) / e["n"]
            chance = 2 * p * q / (p + q) if p + q else 0.0
            L.append(f"- {CONFIG_LABEL[c]}: ROC-AUC {f(e['roc_auc'])}; F1 ≥HIGH {f(m['f1'])} vs. chance {f(chance)}")
        L.append("")

    L.append("## Caveats")
    L.append("")
    L.append("- The paper's hybrid detector is trained in-distribution on CrackedPDFs; pif is zero-shot.")
    L.append("- Erratum 2026-09-13: most payloads start at the bottom-left page corner and extend below the page, "
             "so whether text is *hidden* is easy to tell. What matters is telling injected payloads from matched benign hidden text.")
    L.append("- Synthetic, one-page, English-only documents; no glyph-remapping fonts and no real-world attacks.")
    L.append("")

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    md = out_dir / f"crackedpdfs-{split}-{stamp}.md"
    md.write_text("\n".join(L), encoding="utf-8")
    (out_dir / f"crackedpdfs-{split}-{stamp}.json").write_text(json.dumps(evals, indent=2, default=str))
    with (out_dir / f"crackedpdfs-{split}-{stamp}-predictions.csv").open("w", newline="") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(["pdf_id", "label", "pdf_role", "attack_family", "message_type", "benign_confounder_family"]
                   + [f"{c}_{k}" for c in results for k in ("max_severity", "score")])
        for r in rows:
            w.writerow([r["pdf_id"], r["label"], r["pdf_role"], r["attack_family"], r["message_type"], r["benign_confounder_family"]]
                       + [v for c in results for v in (results[c].get(r["pdf_id"], {}).get("max_severity"),
                                                        results[c].get(r["pdf_id"], {}).get("score"))])
    return md


# --------------------------------------------------------------------------- CLI


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["fetch", "run", "report", "all"])
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "results")
    ap.add_argument("--split", choices=["test", "val", "train"], default="test")
    ap.add_argument("--configs", default="R,RE")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="random subset (smoke tests)")
    ap.add_argument("--shuffle-check", action="store_true", help="add label-shuffle sanity check to report")
    a = ap.parse_args()
    configs = [c.strip() for c in a.configs.split(",") if c.strip()]
    for c in configs:
        if c not in CONFIGS:
            raise SystemExit(f"unknown config {c}; choose from {', '.join(CONFIGS)}")
    out_dir = a.out_dir / ("smoke" if a.limit else "")
    if a.command in ("fetch", "all"):
        fetch(a.data_dir)
    if a.command in ("run", "all"):
        run(a.data_dir, out_dir, a.split, configs, a.jobs, a.limit)
    if a.command in ("report", "all"):
        print("report:", report(a.data_dir, out_dir, a.split, configs, a.shuffle_check))


if __name__ == "__main__":
    main()
