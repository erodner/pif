"""Download the models that ship inside the desktop app into a build directory.

    python scripts/fetch_models.py build/models            # default: minilm only
    python scripts/fetch_models.py build/models minilm deberta-pi-v2
"""

import sys
from pathlib import Path

from pif.ml import store

if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "build/models")
    names = sys.argv[2:] or [store.DEFAULT_EMBEDDING]
    for name in names:
        print("fetching", name, "->", store.download(name, target_root=target))
