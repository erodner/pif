# promptinjectorfinder (`pif`)

Find **hidden and visible prompt-injection patterns** in PDF documents: research papers, CVs, theses and reports. It runs fully offline.

```bash
uv venv && uv pip install -e ".[dev]"
pif scan paper.pdf                       # human-readable report
pif scan submissions/ -j 8 -f json -o report.json
pif scan cvs/ -f sarif --fail-on medium  # CI gate, exit 1 on findings
```

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
| JavaScript | Reported (`javascript`) |

Injection language is detected with a multilingual rule set (EN/DE/FR/ES/IT/PT/ZH/JA). Add your own rules with `--rules rules.json`, a JSON list of `{id, label, pattern, score}`.

**Severity:** `high` = injection language that is hidden from readers. `medium` = injection language that is visible, or in a non-visual carrier. `low` = hidden text without injection language, quoted examples, or JavaScript.

Invisible OCR text layers over scanned images are recognised and not flagged as hidden.

## Status

v0.2: extraction, structural rules, render-based visibility, structure scan, CLI, and JSON/SARIF/text reports.
Planned: local ML classifier (ONNX), OCR-based glyph-remapping check, HTML report, PySide6 desktop app with Windows/macOS installers.

Tests: `pytest` generates one synthetic PDF per technique (`tests/make_fixtures.py`).
