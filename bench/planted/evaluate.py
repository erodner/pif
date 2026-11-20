"""Evaluate pif on PlantedPI-PDF (build it first with bench/planted/build.py).

    python bench/planted/evaluate.py --split dev  --configs R,RE,REC,all -j 3
    python bench/planted/evaluate.py --split test --configs R,RE,REC,all -j 3

Error examples are printed for the dev split only; for test the report gives counts, so the
test split is not used to look at individual failures.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

from crackedpdfs import (  # noqa: E402
    CONFIG_LABEL, CONFIGS, SEV_RANK, _summarise, average_precision, binary_metrics, roc_auc,
)
from pif import runner  # noqa: E402
from pif.scanner import ScanOptions  # noqa: E402

OPS = {"high": 3, "medium": 2}


def _job(args):
    pdf_id, path = args
    return _summarise(pdf_id, runner.scan_in_worker(path, ScanOptions()))


def load(data: Path, split: str) -> list[dict]:
    rows = [json.loads(l) for l in (data / "manifest.jsonl").open(encoding="utf-8")]
    rows = [r for r in rows if r["split"] == split]
    for r in rows:
        r["abs_path"] = str(data / r["path"])
    return rows


def run(data: Path, out: Path, split: str, configs: list[str], jobs: int) -> None:
    rows = load(data, split)
    out.mkdir(parents=True, exist_ok=True)
    for cfg in configs:
        cache = out / f"{split}-{cfg}.jsonl"
        done = {json.loads(l)["pdf_id"] for l in cache.open()} if cache.exists() else set()
        todo = [(r["pdf_id"], r["abs_path"]) for r in rows if r["pdf_id"] not in done]
        print(f"[{cfg}] {len(done)} cached, {len(todo)} to scan", flush=True)
        if not todo:
            continue
        ml, ocr, emb, cls = CONFIGS[cfg]
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=jobs, initializer=runner.worker_init,
                                 initargs=(ml, ocr, runner.threads_per_worker(jobs), emb, cls)) as ex, cache.open("a") as fh:
            for n, fut in enumerate(as_completed([ex.submit(_job, a) for a in todo]), 1):
                fh.write(json.dumps(fut.result()) + "\n")
                if n % 300 == 0 or n == len(todo):
                    print(f"[{cfg}] {n}/{len(todo)} {n / (time.time() - t0):.1f} docs/s", flush=True)


def _rate(rows, res, sev_t, key=None, role=None):
    agg = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if role and r["role"] != role:
            continue
        k = key(r) if key else "all"
        agg[k][1] += 1
        agg[k][0] += SEV_RANK[res[r["pdf_id"]]["max_severity"]] >= sev_t
    return {k: (v[0] / v[1], v[1]) for k, v in sorted(agg.items(), key=lambda kv: str(kv[0]))}


def report(data: Path, out: Path, split: str, configs: list[str]) -> Path:
    rows = load(data, split)
    results = {}
    for c in configs:
        p = out / f"{split}-{c}.jsonl"
        if p.exists():
            results[c] = {d["pdf_id"]: d for d in (json.loads(l) for l in p.open())}
    if not results:
        raise SystemExit("no results; run first")

    def f(x):
        return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"

    card = (data / "DATASET_CARD.md").read_text(encoding="utf-8").splitlines()[2]
    L = [f"# pif on PlantedPI-PDF ({split})", "", f"Generated {dt.datetime.now():%Y-%m-%d %H:%M}. {card}", ""]
    n_inj = sum(r["label"] for r in rows)
    L.append(f"{len(rows)} PDFs = {n_inj} triads (clean / benign confounder / injected).")
    L.append("")
    L.append("By design, pif reports hidden injections as HIGH and visible or non-visual (metadata, annotation) injections as MEDIUM. "
             "So **≥MEDIUM** is the operating point for *any injection present*, and **≥HIGH** for *hidden injection*.")
    L.append("")
    L.append("## Overall")
    L.append("")
    L.append("| Config | Op | Precision | Recall | F1 | FPR (all neg.) | FPR benign confounder | FPR clean | ROC-AUC | PR-AUC | Paired rank |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    evals = {}
    for c, res in results.items():
        rs = [r for r in rows if r["pdf_id"] in res]
        y = np.array([r["label"] for r in rs])
        s = np.array([res[r["pdf_id"]]["score"] for r in rs])
        sev = np.array([SEV_RANK[res[r["pdf_id"]]["max_severity"]] for r in rs])
        by_triad = collections.defaultdict(dict)
        for r in rs:
            by_triad[r["triad_id"]][r["role"]] = res[r["pdf_id"]]["score"]
        wins = [1.0 if t["injected"] > t["benign"] else 0.5 if t["injected"] == t["benign"] else 0.0
                for t in by_triad.values() if "injected" in t and "benign" in t]
        e = {"roc": roc_auc(y, s), "ap": average_precision(y, s), "paired": float(np.mean(wins))}
        for op, t in OPS.items():
            m = binary_metrics(y, (sev >= t).astype(int))
            fb = _rate(rs, res, t, role="benign")["all"][0]
            fc = _rate(rs, res, t, role="clean")["all"][0]
            e[op] = m
            L.append(f"| {CONFIG_LABEL[c]} | ≥{op.upper()} | {f(m['precision'])} | {f(m['recall'])} | **{f(m['f1'])}** | "
                     f"{f(m['fpr'])} | {f(fb)} | {f(fc)} | {f(e['roc'])} | {f(e['ap'])} | {f(e['paired'])} |")
        evals[c] = e
    L.append("")

    cols = list(results)

    def block(title, note, key, role, op):
        L.append(f"## {title}")
        L.append("")
        if note:
            L.append(note)
            L.append("")
        L.append("| Group | n | " + " | ".join(CONFIG_LABEL[c] for c in cols) + " |")
        L.append("|---|---|" + "---|" * len(cols))
        per = {c: _rate([r for r in rows if r["pdf_id"] in results[c]], results[c], OPS[op], key, role) for c in cols}
        for g in per[cols[0]]:
            n = per[cols[0]][g][1]
            L.append(f"| {g} | {n} | " + " | ".join(f(per[c].get(g, (float('nan'), 0))[0]) for c in cols) + " |")
        L.append("")

    block("Recall per technique (injected, ≥MEDIUM)", None, lambda r: f"{r['channel']}: {r['technique']}", "injected", "medium")
    block("Recall per technique (injected, ≥HIGH)", "Only hidden techniques are expected to reach HIGH.",
          lambda r: f"{r['channel']}: {r['technique']}", "injected", "high")
    block("Recall per injection language (≥MEDIUM)", None, lambda r: r["payload_lang"], "injected", "medium")
    block("False-positive rate per benign source and language (benign confounders, ≥MEDIUM)", None,
          lambda r: f"{r['payload_source']} / {r['payload_lang']}", "benign", "medium")
    block("False-positive rate per benign source (benign confounders, ≥HIGH)", None,
          lambda r: f"{r['payload_source']} / {r['payload_lang']}", "benign", "high")
    block("False-positive rate per NotInject category (≥MEDIUM)", None,
          lambda r: r["notinject_category"] or "-", "benign", "medium")
    block("False-positive rate per technique (benign confounders, ≥MEDIUM)", None,
          lambda r: f"{r['channel']}: {r['technique']}", "benign", "medium")

    best = max(evals, key=lambda c: evals[c]["medium"]["f1"])
    res = results[best]
    fns = [r for r in rows if r["role"] == "injected" and r["pdf_id"] in res and SEV_RANK[res[r["pdf_id"]]["max_severity"]] < 2]
    fps = [r for r in rows if r["role"] != "injected" and r["pdf_id"] in res and SEV_RANK[res[r["pdf_id"]]["max_severity"]] >= 2]
    L.append(f"## Errors: {CONFIG_LABEL[best]}, ≥MEDIUM")
    L.append("")
    L.append(f"{len(fns)} false negatives, {len(fps)} false positives.")
    L.append("")
    if split == "dev":
        rng = random.Random(0)
        for title, sample in (("False negatives", rng.sample(fns, min(30, len(fns)))),
                              ("False positives", rng.sample(fps, min(30, len(fps))))):
            L.append(f"### {title} (sample)")
            L.append("")
            L.append("| pdf | technique | lang | pif | text |")
            L.append("|---|---|---|---|---|")
            for r in sample:
                d = res[r["pdf_id"]]
                rules = sorted({x.split(":")[0] for fd in d["findings"] for x in fd["rules"]})
                txt = (r["payload_text"] or "").replace("|", "\\|")[:160]
                L.append(f"| {r['pdf_id']} | {r['technique']} | {r['payload_lang']} | {d['max_severity'] or 'clean'} {','.join(rules)} | {txt} |")
            L.append("")
    else:
        L.append("(Error examples are not shown for the test split.)")
        L.append("")
    path = out / f"planted-{split}-{dt.datetime.now():%Y%m%d-%H%M}.md"
    path.write_text("\n".join(L), encoding="utf-8")
    (path.with_suffix(".json")).write_text(json.dumps(evals, indent=2, default=str))
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="all", choices=["run", "report", "all"])
    ap.add_argument("--data", type=Path, default=ROOT / "bench/data/planted/v1")
    ap.add_argument("--out", type=Path, default=ROOT / "bench/results/planted")
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--configs", default="R,RE,REC,all")
    ap.add_argument("-j", "--jobs", type=int, default=3)
    a = ap.parse_args()
    configs = [c for c in a.configs.split(",") if c]
    if a.command in ("run", "all"):
        run(a.data, a.out, a.split, configs, a.jobs)
    if a.command in ("report", "all"):
        print("report:", report(a.data, a.out, a.split, configs))


if __name__ == "__main__":
    main()
