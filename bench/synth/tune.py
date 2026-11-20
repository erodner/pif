"""Choose the injection-head thresholds on dev data only.

    python bench/synth/tune.py

Dev texts: PlantedPI-PDF dev payloads (injected vs. benign twins) and CrackedPDFs validation
hidden texts (injected vs. confounders, from cached scans), plus our own host-document prose as
visible negatives. Prints precision/recall/FPR per threshold; the chosen thresholds go into
CascadeConfig (head_threshold_hidden / head_threshold_visible).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "planted"))


def main() -> None:
    from crackedpdfs import load_rows, roc_auc
    from hosts import TEXT

    from pif.ml.cascade import MLCascade, _strip_markup

    c = MLCascade.load(classifier=None)
    assert c.head is not None, "train the head first"
    w, b, _ = c.head

    def prob(texts):
        v = c.embedder.encode([c._unfuse(_strip_markup(t)) for t in texts]).astype(np.float64)
        return 1 / (1 + np.exp(-(v @ w + b)))

    sets = {}
    planted = [json.loads(l) for l in open(ROOT / "bench/data/planted/v1/manifest.jsonl", encoding="utf-8")]
    dev = [r for r in planted if r["split"] == "dev" and r["role"] != "clean"]
    sets["planted-dev"] = ([r["payload_text"] for r in dev], np.array([r["label"] for r in dev]))

    rows = {r["pdf_id"]: r for r in load_rows(ROOT / "bench/data", "val")}
    texts, labels = [], []
    for line in open(ROOT / "bench/results/val-v2/val-R.jsonl"):
        d = json.loads(line)
        r = rows[d["pdf_id"]]
        if r["pdf_role"] == "benign_original":
            continue
        t = " ".join(f["text"] for f in d["findings"] if f["carrier"] == "page_text")
        if t:
            texts.append(t)
            labels.append(r["label"])
    sets["crackedpdfs-val"] = (texts, np.array(labels))

    prose = [s for lang in TEXT.values() for g in lang.values() for s in g["sentences"]]
    p_prose = prob(prose)

    print(f"host prose (visible negatives, n={len(prose)}): max P = {p_prose.max():.3f}, "
          f"FP@0.5 = {(p_prose >= 0.5).mean():.3f}, FP@0.9 = {(p_prose >= 0.9).mean():.3f}")
    for name, (t, y) in sets.items():
        p = prob(t)
        print(f"\n== {name}: n={len(y)} ({int(y.sum())} injected)  ROC-AUC {roc_auc(y, p):.3f}")
        print("thr   recall  FPR    precision")
        for thr in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98):
            pred = p >= thr
            tp, fp = (pred & (y == 1)).sum(), (pred & (y == 0)).sum()
            print(f"{thr:<5} {tp / max(1, y.sum()):.3f}   {fp / max(1, (y == 0).sum()):.3f}  {tp / max(1, tp + fp):.3f}")


if __name__ == "__main__":
    main()
