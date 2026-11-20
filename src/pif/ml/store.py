"""Model registry, cache location and verified downloads from the Hugging Face Hub.

Models are pinned to an exact repository revision, and large files are checked against
their SHA-256. Nothing is downloaded implicitly: call `download()` (or `pif models download`).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HF_URL = "https://huggingface.co/{repo}/resolve/{revision}/{path}"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    kind: str  # "embedding" | "classifier"
    repo: str
    revision: str
    license: str
    files: dict[str, str]  # local name -> path in repo
    sha256: dict[str, str] = field(default_factory=dict)  # local name -> expected digest
    description: str = ""


MODELS: dict[str, ModelSpec] = {
    "minilm": ModelSpec(
        name="minilm",
        kind="embedding",
        repo="sentence-transformers/all-MiniLM-L6-v2",
        revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        license="apache-2.0",
        files={
            "model.onnx": "onnx/model_qint8_arm64.onnx",  # dynamic int8, runs on x86 and arm64
            "tokenizer.json": "tokenizer.json",
        },
        sha256={"model.onnx": "4278337fd0ff3c68bfb6291042cad8ab363e1d9fbc43dcb499fe91c871902474"},
        description="Sentence embeddings (23 MB) for similarity to known injection phrasing",
    ),
    "deberta-pi-v2": ModelSpec(
        name="deberta-pi-v2",
        kind="classifier",
        repo="protectai/deberta-v3-base-prompt-injection-v2",
        revision="90c9989b1a342275dd0d1a95aad283c04e075671",
        license="apache-2.0",
        files={
            "model.onnx": "onnx/model.onnx",
            "tokenizer.json": "onnx/tokenizer.json",
            "config.json": "onnx/config.json",
        },
        sha256={"model.onnx": "f0ea7f239f765aedbde7c9e163a7cb38a79c5b8853d3f76db5152172047b228c"},
        # fp32 on purpose: dynamic int8 quantisation collapses this DeBERTa-v3 model's outputs,
        # and MatMul-only int8 loses non-English recall while staying >500 MB.
        description="Prompt-injection classifier (740 MB download); used on hidden/non-visual text",
    ),
}

DEFAULT_EMBEDDING = "minilm"
DEFAULT_CLASSIFIER = "deberta-pi-v2"


def model_roots() -> list[Path]:
    """Search order: $PIF_MODEL_DIR, bundled (frozen app), user cache."""
    roots: list[Path] = []
    if os.environ.get("PIF_MODEL_DIR"):
        roots.append(Path(os.environ["PIF_MODEL_DIR"]))
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "models")
    roots.append(cache_dir())
    return roots


def cache_dir() -> Path:
    if os.environ.get("PIF_MODEL_DIR"):
        return Path(os.environ["PIF_MODEL_DIR"])
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "promptinjectorfinder" / "models"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "promptinjectorfinder" / "models"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "promptinjectorfinder" / "models"


def find_model(name: str) -> Path | None:
    """Directory containing a complete copy of model `name`, or None."""
    spec = MODELS.get(name)
    for root in model_roots():
        d = root / name
        if spec is None:
            if (d / "model.onnx").exists():
                return d
            continue
        if all((d / f).exists() for f in spec.files):
            return d
    # A user-supplied directory path (custom model) is also accepted.
    p = Path(name)
    if p.is_dir() and (p / "model.onnx").exists() and (p / "tokenizer.json").exists():
        return p
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(
    name: str,
    target_root: Path | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> Path:
    spec = MODELS[name]
    target = (target_root or cache_dir()) / name
    target.mkdir(parents=True, exist_ok=True)
    for local, remote in spec.files.items():
        dest = target / local
        if dest.exists() and (local not in spec.sha256 or _sha256(dest) == spec.sha256[local]):
            continue
        url = HF_URL.format(repo=spec.repo, revision=spec.revision, path=remote)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "promptinjectorfinder"})
        with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(1 << 20):
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(local, done, total)
        if local in spec.sha256 and _sha256(tmp) != spec.sha256[local]:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"checksum mismatch for {name}/{local}")
        tmp.replace(dest)

    return target


def remove(name: str) -> None:
    d = cache_dir() / name
    if d.exists():
        shutil.rmtree(d)
