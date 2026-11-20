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
    hidden: bool = False  # hidden page text: lower embedding threshold (not for metadata labels)


@dataclass
class CascadeConfig:
    classify_visible: bool = False
    candidate_similarity: float = 0.55  # visible segments at/above this go to the classifier
    strong_similarity: float = 0.72  # embedding alone counts as a hit (visible text)
    # Hidden / non-visual text: tuned on the CrackedPDFs validation split (0.45 was still free
    # of confounder hits; 0.50 leaves a margin for real-world documents).
    strong_similarity_hidden: float = 0.50
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
        self._vocab: set[str] | None = None

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

    def _unfuse(self, text: str) -> str:
        """Re-insert spaces into long fused tokens ("Writeouttheinternalrules") for embedding."""
        if not any(len(tok) >= FUSED_MIN for tok in text.split()):
            return text
        if self._vocab is None:
            vocab = self.embedder.tokenizer.get_vocab()
            self._vocab = {w for w in vocab if w.isalpha() and w.isascii() and not w.startswith("##")}
        return " ".join(segment_fused(tok, self._vocab) if len(tok) >= FUSED_MIN else tok for tok in text.split())

    def _bank_vectors(self) -> np.ndarray:
        if self._bank is None:
            self._bank = self.embedder.encode(INJECTION_PHRASES)
        return self._bank

    def detect(self, text: str) -> list[Match]:
        """Detector-protocol entry point: treat the whole text as forced (non-visual) input."""
        return self.score_segments(split_segments(text, force=True))

    def score_segments(self, segments: list[Segment]) -> list[Match]:
        cfg = self.config
        # Machine markup ("[ID=…]", "<SOME_TAG>") dilutes sentence embeddings, and fused text
        # ("Writeouttheinternalrules") is one "word". Both are normalised before the word-count
        # filter and the embedding; rules and the classifier still see the original text.
        pairs = []
        for s in segments:
            prepared = self._unfuse(_strip_markup(s.text)) if self.embedder is not None else s.text
            if _wordy(prepared, cfg.min_words):
                pairs.append((s, prepared))
        if not pairs:
            return []
        segs = [s for s, _ in pairs]
        texts = [s.text for s in segs]

        sims = np.zeros(len(segs), dtype=np.float32)
        best = np.zeros(len(segs), dtype=np.int64)
        if self.embedder is not None:
            sim_matrix = self.embedder.encode([p for _, p in pairs]) @ self._bank_vectors().T
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

        # Both signals are reported separately: severity policy treats a classifier-only hit
        # differently from one confirmed by phrase similarity.
        matches: list[Match] = []
        for i, s in enumerate(segs):
            p = probs[i]
            if not np.isnan(p):
                threshold = cfg.classifier_threshold_hidden if s.force else cfg.classifier_threshold_visible
                if p >= threshold:
                    matches.append(Match(self.name, "ML-CLS", f"classifier P(injection)={p:.2f}",
                                         0.5 + 0.45 * float(p), s.start, s.end))
            emb_threshold = cfg.strong_similarity_hidden if s.hidden else cfg.strong_similarity
            if self.embedder is not None and sims[i] >= emb_threshold:
                phrase = INJECTION_PHRASES[int(best[i])]
                matches.append(Match(self.name, "ML-EMB", f"similar to “{phrase}” ({sims[i]:.2f})",
                                     min(0.9, 0.6 + (float(sims[i]) - emb_threshold)), s.start, s.end))
        return matches


_SENT_END = re.compile(r"(?<=[.!?;:。！？])\s+|\n{2,}")


def split_segments(text: str, force: bool = False, offset: int = 0, max_chars: int = 400, min_chars: int = 40,
                   hidden: bool = False) -> list[Segment]:
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
            out.append(Segment(offset + s, offset + cut, text[s:cut], force, hidden))
            s = cut + 1
        if e > s:
            out.append(Segment(offset + s, offset + e, text[s:e], force, hidden))
    return out


FUSED_MIN = 20


def segment_fused(token: str, vocab: set[str], max_word: int = 18) -> str:
    """Split a fused alphabetic run into known words (fewest pieces; single letters penalised).

    Non-letters are kept as separators. Used only to make fused hidden text readable for the
    embedding model; the extracted text itself is not changed.
    """
    out = []
    for part in re.split(r"([^A-Za-z]+)", token):
        if not part or not part.isalpha() or len(part) < 8:
            out.append(part)
            continue
        low = part.lower()
        n = len(low)
        best = [0.0] + [float("inf")] * n
        back = [0] * (n + 1)
        for i in range(1, n + 1):
            for j in range(max(0, i - max_word), i):
                w = low[j:i]
                if w in vocab or (len(w) == 1 and w in "ai"):
                    cost = best[j] + 1.0 + (2.0 if len(w) == 1 else 0.0) + (0.5 if len(w) == 2 else 0.0)
                    if cost < best[i]:
                        best[i], back[i] = cost, j
        if best[n] == float("inf"):
            out.append(part)
            continue
        words, i = [], n
        while i > 0:
            words.append(part[back[i]:i])
            i = back[i]
        out.append(" ".join(reversed(words)))
    return re.sub(r"\s+", " ", " ".join(out)).strip()


_MARKUP = re.compile(r"\[[A-Za-z_]{2,40}=[^\]]{0,120}\]|</?[A-Za-z_][A-Za-z0-9_:.-]{1,60}>")


def _strip_markup(text: str) -> str:
    return re.sub(r"\s+", " ", _MARKUP.sub(" ", text)).strip() or text


def _wordy(text: str, min_words: int) -> bool:
    words = [w for w in text.split() if sum(c.isalpha() for c in w) >= 2]
    return len(words) >= min_words
