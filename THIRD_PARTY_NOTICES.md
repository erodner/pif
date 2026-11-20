# Third-party components

promptinjectorfinder is licensed under the GNU Affero General Public License v3.0 or later
(see `LICENSE`). The packaged desktop app bundles the components below; their licenses apply
to the respective parts.

| Component | License | Source |
|---|---|---|
| PyMuPDF / MuPDF | AGPL-3.0 | https://github.com/pymupdf/PyMuPDF |
| Qt 6 / PySide6 | LGPL-3.0 (dynamically linked; replace the Qt libraries in the app folder to relink) | https://code.qt.io/ |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| Hugging Face tokenizers | Apache-2.0 | https://github.com/huggingface/tokenizers |
| RapidOCR (incl. PaddleOCR PP-OCRv4 models) | Apache-2.0 | https://github.com/RapidAI/RapidOCR |
| OpenCV (via RapidOCR) | Apache-2.0 | https://github.com/opencv/opencv |
| NumPy | BSD-3-Clause | https://numpy.org |
| Typer, Click, Rich | MIT / BSD-3-Clause / MIT | https://github.com/fastapi/typer |
| sentence-transformers/all-MiniLM-L6-v2 (model weights) | Apache-2.0 | https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 |
| Python | PSF License | https://www.python.org |

Downloaded on request (not bundled):

| Component | License | Source |
|---|---|---|
| protectai/deberta-v3-base-prompt-injection-v2 (model weights) | Apache-2.0 | https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2 |
