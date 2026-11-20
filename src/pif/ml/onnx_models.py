"""Thin ONNX Runtime wrappers: sentence embedder and sequence classifier (no PyTorch)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np



def _session(path: Path):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = int(os.environ.get("PIF_THREADS", "0")) or min(8, os.cpu_count() or 1)
    opts.log_severity_level = 3
    return ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])


def _tokenizer(path: Path, max_len: int):
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(path))
    tok.enable_truncation(max_length=max_len)
    tok.enable_padding(pad_id=tok.token_to_id("[PAD]") or 0, pad_token="[PAD]")
    return tok


class _OnnxTextModel:
    def __init__(self, model_dir: Path, max_len: int, batch_size: int):
        self.model_dir = Path(model_dir)
        self.session = _session(self.model_dir / "model.onnx")
        self.tokenizer = _tokenizer(self.model_dir / "tokenizer.json", max_len)
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.batch_size = batch_size

    def _feeds(self, texts: list[str]) -> dict[str, np.ndarray]:
        enc = self.tokenizer.encode_batch(texts)
        feeds = {
            "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
        }
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
        return {k: v for k, v in feeds.items() if k in self.input_names}

    def _batches(self, texts: list[str]):
        # Sort by length so padding stays small, then restore order.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        for s in range(0, len(order), self.batch_size):
            idx = order[s : s + self.batch_size]
            yield idx, [texts[i] for i in idx]


class Embedder(_OnnxTextModel):
    """Mean-pooled, L2-normalised sentence embeddings (sentence-transformers style)."""

    def __init__(self, model_dir: Path, max_len: int = 256, batch_size: int = 64):
        super().__init__(model_dir, max_len, batch_size)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        out: list[np.ndarray | None] = [None] * len(texts)
        for idx, batch in self._batches(texts):
            feeds = self._feeds(batch)
            hidden = self.session.run(None, feeds)[0]  # (b, t, d)
            mask = feeds["attention_mask"][..., None].astype(np.float32)
            pooled = (hidden * mask).sum(1) / np.clip(mask.sum(1), 1e-9, None)
            pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)
            for i, v in zip(idx, pooled):
                out[i] = v
        return np.stack(out).astype(np.float32)


class Classifier(_OnnxTextModel):
    """Binary/multi-class sequence classifier; returns P(injection) per text."""

    def __init__(self, model_dir: Path, max_len: int = 512, batch_size: int = 16):
        super().__init__(model_dir, max_len, batch_size)
        self.positive_index = self._positive_index()

    def _positive_index(self) -> int:
        cfg_path = self.model_dir / "config.json"
        if cfg_path.exists():
            labels = json.loads(cfg_path.read_text(encoding="utf-8")).get("id2label", {})
            for k, v in labels.items():
                if str(v).upper() in {"INJECTION", "JAILBREAK", "MALICIOUS", "UNSAFE", "LABEL_1"} and str(v).upper() != "LABEL_0":
                    return int(k)
        return 1

    def predict(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros(0, dtype=np.float32)
        out = np.zeros(len(texts), dtype=np.float32)
        for idx, batch in self._batches(texts):
            logits = self.session.run(None, self._feeds(batch))[0]
            logits = logits - logits.max(axis=1, keepdims=True)
            probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
            out[idx] = probs[:, self.positive_index]
        return out
