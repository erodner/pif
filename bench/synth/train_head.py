"""Train pif's injection head: logistic regression on MiniLM sentence embeddings.

    python bench/synth/train_head.py     # corpus_v1.jsonl -> src/pif/ml/data/injection_head_v1.json

Trained only on the synthetic corpus (no evaluation data). Inputs are prepared exactly as in
the cascade (markup stripped, fused words segmented). Class-balanced, L2-regularised,
fitted with Newton's method (numpy only). Reports 5-fold cross-validated ROC-AUC on the corpus.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

L2 = 0.3  # best 5-fold CV AUC on the synthetic corpus (sweep 0.01–10)
OUT = ROOT / "src/pif/ml/data/injection_head_v1.json"


def fit(X: np.ndarray, y: np.ndarray, l2: float = L2, iters: int = 30) -> tuple[np.ndarray, float]:
    n, d = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])
    w = np.zeros(d + 1)
    pos = y.mean()
    sw = np.where(y == 1, 0.5 / pos, 0.5 / (1 - pos))  # class balance
    reg = np.full(d + 1, l2)
    reg[-1] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Xb @ w)))
        g = Xb.T @ (sw * (p - y)) + reg * w
        H = (Xb * (sw * p * (1 - p))[:, None]).T @ Xb + np.diag(reg)
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w[:-1], float(w[-1])


def main() -> None:
    from crackedpdfs import roc_auc

    from pif.ml import store
    from pif.ml.cascade import MLCascade, _strip_markup

    corpus_path = HERE / "corpus_v1.jsonl"
    rows = [json.loads(l) for l in corpus_path.open(encoding="utf-8")]
    c = MLCascade.load(classifier=None)
    X = c.embedder.encode([c._unfuse(_strip_markup(r["text"])) for r in rows]).astype(np.float64)
    y = np.array([r["label"] for r in rows], dtype=np.float64)

    rng = np.random.default_rng(0)
    folds = rng.permutation(len(rows)) % 5
    scores = np.zeros(len(rows))
    for k in range(5):
        tr, te = folds != k, folds == k
        w, b = fit(X[tr], y[tr])
        scores[te] = 1 / (1 + np.exp(-(X[te] @ w + b)))
    cv_auc = roc_auc(y, scores)
    by_lang = {}
    for lang in sorted({r["lang"] for r in rows}):
        m = np.array([r["lang"] == lang for r in rows])
        if len(set(y[m])) == 2:
            by_lang[lang] = round(roc_auc(y[m], scores[m]), 4)

    w, b = fit(X, y)
    spec = store.MODELS[store.DEFAULT_EMBEDDING]
    head = {
        "name": "injection_head_v1",
        "embedding_model": f"{spec.repo}@{spec.revision}",
        "corpus": corpus_path.name,
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "n_train": len(rows),
        "n_injection": int(y.sum()),
        "l2": L2,
        "cv_roc_auc": round(cv_auc, 4),
        "cv_roc_auc_by_lang": by_lang,
        "trained": dt.date.today().isoformat(),
        "dim": int(X.shape[1]),
        "bias": round(b, 6),
        "weights": [round(float(v), 6) for v in w],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(head) + "\n")
    print(json.dumps({k: v for k, v in head.items() if k != "weights"}, indent=2))


if __name__ == "__main__":
    main()
