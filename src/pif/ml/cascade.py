"""Embedding-similarity + classifier cascade over text segments.

Every segment gets a cheap embedding similarity to known injection phrasing. The
classifier runs on segments a reader cannot see (hidden text, metadata and other
non-visual carriers). Off-the-shelf injection classifiers are trained on chat prompts and
flag ordinary instructional prose ("follow the instructions in Section 3"), so on visible
text they run only when `classify_visible` is set, on embedding candidates, with a strict
threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from ..model import Match
from . import store
from .phrases import INJECTION_PHRASES


@dataclass
class Segment:
    start: int
    end: int
    text: str
    force: bool = False  # always run the classifier (hidden or non-visual text)


@dataclass
class CascadeConfig:
    classify_visible: bool = False
    candidate_similarity: float = 0.55  # visible segments at/above this go to the classifier
    strong_similarity: float = 0.72  # embedding alone counts as a hit
    classifier_threshold_hidden: float = 0.90
    classifier_threshold_visible: float = 0.97
    min_words: int = 4


class MLCascade:
    name = "ml"

    def __init__(self, embedder=None, classifier=None, config: CascadeConfig | None = None):
        if embedder is None and classifier is None:
            raise ValueError("need at least an embedder or a classifier")
        self.embedder = embedder
        self.classifier = classifier
        self.config = config or CascadeConfig()
        self._bank = None

    @classmethod
    def load(
        cls,
        embedding: str | None = store.DEFAULT_EMBEDDING,
        classifier: str | None = store.DEFAULT_CLASSIFIER,
        require: bool = False,
        config: CascadeConfig | None = None,
    ) -> "MLCascade | None":
        """Load whatever requested models are installed. Returns None if none are."""
        try:
            from .onnx_models import Classifier, Embedder
        except ImportError:
            if require:
                raise RuntimeError("ML detectors need `pip install promptinjectorfinder[ml]`")
            return None
        emb = cls_model = None
        missing = []
        if embedding:
            d = store.find_model(embedding)
            emb = Embedder(d) if d else None
            if not d:
                missing.append(embedding)
        if classifier:
            d = store.find_model(classifier)
            cls_model = Classifier(d) if d else None
            if not d:
                missing.append(classifier)
        if require and missing:
            raise RuntimeError(f"models not installed: {', '.join(missing)} (run `pif models download`)")
        if emb is None and cls_model is None:
            return None
        return cls(emb, cls_model, config)

    @property
    def description(self) -> str:
        parts = []
        if self.embedder:
            parts.append(f"embedding:{self.embedder.model_dir.name}")
        if self.classifier:
            parts.append(f"classifier:{self.classifier.model_dir.name}")
        return ", ".join(parts)

    def _bank_vectors(self) -> np.ndarray:
        if self._bank is None:
            self._bank = self.embedder.encode(INJECTION_PHRASES)
        return self._bank

    def detect(self, text: str) -> list[Match]:
        """Detector-protocol entry point: treat the whole text as forced (non-visual) input."""
        return self.score_segments(split_segments(text, force=True))

    def score_segments(self, segments: list[Segment]) -> list[Match]:
        cfg = self.config
        segs = [s for s in segments if _wordy(s.text, cfg.min_words)]
        if not segs:
            return []
        texts = [s.text for s in segs]

        sims = np.zeros(len(segs), dtype=np.float32)
        best = np.zeros(len(segs), dtype=np.int64)
        if self.embedder is not None:
            sim_matrix = self.embedder.encode(texts) @ self._bank_vectors().T
            sims = sim_matrix.max(axis=1)
            best = sim_matrix.argmax(axis=1)

        probs = np.full(len(segs), np.nan, dtype=np.float32)
        if self.classifier is not None:
            todo = [
                i for i, s in enumerate(segs)
                if s.force
                or (cfg.classify_visible and (self.embedder is None or sims[i] >= cfg.candidate_similarity))
            ]
            if todo:
                probs[todo] = self.classifier.predict([texts[i] for i in todo])

        matches: list[Match] = []
        for i, s in enumerate(segs):
            score, rule, label = 0.0, "", ""
            p = probs[i]
            if not np.isnan(p):
                threshold = cfg.classifier_threshold_hidden if s.force else cfg.classifier_threshold_visible
                if p >= threshold:
                    score, rule, label = 0.5 + 0.45 * float(p), "ML-CLS", f"classifier P(injection)={p:.2f}"
            if self.embedder is not None and sims[i] >= cfg.strong_similarity:
                emb_score = min(0.9, 0.6 + (float(sims[i]) - cfg.strong_similarity))
                if emb_score > score:
                    phrase = INJECTION_PHRASES[int(best[i])]
                    score, rule, label = emb_score, "ML-EMB", f"similar to “{phrase}” ({sims[i]:.2f})"
            if score > 0:
                matches.append(Match(self.name, rule, label, score, s.start, s.end))
        return matches


_SENT_END = re.compile(r"(?<=[.!?;:。！？])\s+|\n{2,}")


def split_segments(text: str, force: bool = False, offset: int = 0, max_chars: int = 400, min_chars: int = 40) -> list[Segment]:
    """Split into sentence-like segments, merging short ones and hard-wrapping long ones."""
    pieces: list[tuple[int, int]] = []
    pos = 0
    for m in _SENT_END.finditer(text):
        pieces.append((pos, m.start()))
        pos = m.end()
    pieces.append((pos, len(text)))

    merged: list[tuple[int, int]] = []
    for s, e in pieces:
        if e <= s:
            continue
        if merged and (merged[-1][1] - merged[-1][0] < min_chars) and e - merged[-1][0] <= max_chars:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    out: list[Segment] = []
    for s, e in merged:
        while e - s > max_chars:
            cut = text.rfind(" ", s, s + max_chars)
            cut = cut if cut > s else s + max_chars
            out.append(Segment(offset + s, offset + cut, text[s:cut], force))
            s = cut + 1
        if e > s:
            out.append(Segment(offset + s, offset + e, text[s:e], force))
    return out


def _wordy(text: str, min_words: int) -> bool:
    words = [w for w in text.split() if sum(c.isalpha() for c in w) >= 2]
    return len(words) >= min_words
