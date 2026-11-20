# promptinjectorfinder (`pif`)

Find **hidden and visible prompt-injection patterns** in PDF documents: research papers, CVs, theses and reports. It runs fully offline.

```bash
uv venv && uv pip install -e ".[ml,ocr,dev]"
pif models download                      # optional: MiniLM (23 MB) + DeBERTa classifier (740 MB)
pif scan paper.pdf                       # human-readable report
pif scan submissions/ -j 8 -f json -o report.json   # whole directory tree, with progress bar
pif scan cvs/ -f sarif --fail-on medium  # CI gate, exit 1 on findings
pif scan inbox/ -f html -o report.html   # shareable report with page crops
```

Directories are scanned recursively (`--no-recursive` to stay at the top level). All `*.pdf`/`*.PDF`
files are picked up, hidden files and folders are skipped (`--include-hidden`), and duplicates are
scanned once. A progress bar appears on stderr when it is a terminal (`--progress/--no-progress`,
`-q` for silence), so `-f json > out.json` stays clean.

```python
from pif import scan
report = scan("paper.pdf")
for f in report.findings:
    print(f.severity, f.page, f.techniques, f.text)
```

## What it detects

| Hiding technique | How |
|---|---|
| White or background-coloured text, text covered by images or shapes, zero-area clipping | Render-diff: the page is rendered with and without text, and spans that change ~no pixels are hidden (`not_rendered`) |
| Tiny fonts (e.g. 0.1pt), horizontally squashed text | Effective glyph size after all transforms (`tiny_font`) |
| Invisible render mode (Tr 3/7), zero opacity | Text trace (`invisible_render_mode`, `zero_opacity`) |
| Text outside the CropBox | Geometry (`off_page`) |
| Optional-content layers switched OFF | Extraction with all layers forced on (`hidden_layer`) |
| Unicode tag smuggling, zero-width characters | Normalisation; tag payloads are decoded and scanned (`invisible_unicode`) |
| Metadata/XMP, annotations, form fields, bookmarks, embedded files | Scanned as non-visual carriers (`non_visual_carrier`) |
| Malicious fonts / lying `/ToUnicode` maps (shows one text, extracts another) | OCR (RapidOCR, recognition only) of a few clean sample lines per font, compared with the extracted text (`glyph_remap`) |
| JavaScript | Reported (`javascript`) |

Injection language is detected in layers. The first is a multilingual rule set (EN/DE/FR/ES/IT/PT/ZH/JA). Add your own rules with `--rules rules.json`, a JSON list of `{id, label, pattern, score}`.
The optional local ML layers (`--ml auto|on|off`; auto uses whatever is installed) are:

- **Embedding similarity** (all-MiniLM-L6-v2 int8) to about 40 reference injection phrasings. It runs on every sentence and catches paraphrases the rules miss.
- **Classifier** (ProtectAI deberta-v3-base-prompt-injection-v2, fp32). It runs only on hidden and non-visual text, because on ordinary visible prose these classifiers fire on harmless instructions ("follow the instructions in Section 3"). A carrier hit found only by the classifier is reported as LOW (unconfirmed).

Models are pinned to exact Hugging Face revisions, checked by SHA-256, and cached per user. `PIF_MODEL_DIR` overrides the location.

**Severity:** `high` = injection language that is hidden from readers. `medium` = injection language that is visible, or in a non-visual carrier. `low` = hidden text without injection language, quoted examples, or JavaScript.

Invisible OCR text layers over scanned images are recognised and not flagged as hidden.

The OCR glyph check (`--ocr auto|on|off`) costs about 0.2–0.6 s per document. It samples only lines that nothing else is drawn over. A remapped font is reported once (LOW) and all of its text counts as hidden, so injection language set in that font is HIGH.

The HTML report (`-f html`) is a single self-contained file. Each finding shows a crop of the page as a reader sees it, with the extracted text outlined. All PDF-derived text is HTML-escaped.

## Status

v0.4: extraction, structural rules, render-based visibility, OCR glyph-remap check, structure scan, ML cascade (ONNX), recursive CLI with progress bar, and text/JSON/SARIF/HTML reports.
Planned: PySide6 desktop app with Windows/macOS installers.

Tests: `pytest` generates one synthetic PDF per technique (`tests/make_fixtures.py`).
