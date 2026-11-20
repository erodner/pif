# PlantedPI-PDF

A reproducible, challenging PDF benchmark for prompt-injection detection. Real injection texts
and *hard benign* texts are planted into synthetic host documents with 16 techniques.

```bash
python bench/planted/build.py --check-reproducible   # ~1 min; downloads ~0.3 MB of source data
python bench/planted/evaluate.py --split dev  --configs R,RE,REC,all -j 3
python bench/planted/evaluate.py --split test --configs R,RE,REC,all -j 3
```

## Why it is hard

- **Real attack texts.** [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections)
  contains free-form jailbreaks and task hijacks written by people, not templates. About 38% are **German**.
- **Hard negatives.** Benign confounders come partly from [NotInject](https://huggingface.co/datasets/leolee99/NotInject):
  harmless prompts full of trigger words ("ignore", "bypass", "uncensored", "override"), including Chinese.
  Off-the-shelf injection classifiers over-flag these.
- **Matched confounders.** Each injection has a benign twin planted with the *same* technique in the *same*
  place of the *same* host document, so hiding alone is not a signal. Paired ranking measures exactly this.
- **16 techniques.**
  - Hidden page text: white, near-white, 0.6 pt, invisible render mode, zero opacity, off-page, hidden layer,
    covered by a shape, zero-area clipping, microglyphs (one 0.5 pt glyph per text object), split words, and a
    lying `/ToUnicode` map (glyph remap: the page shows rot13 while extraction yields the payload).
  - Non-visual: document metadata, annotation.
  - Visible: normal paragraph, small grey footnote.
- **Host documents** in English and German, in four genres (paper, CV, memo, datasheet).

## Reproducibility

- Source files are pinned to Hugging Face revisions and verified by SHA-256 (`SOURCES` in `build.py`).
- Generation is seeded. PDFs are saved without timestamps or random IDs: the same seed and PyMuPDF version give
  byte-identical files. `--check-reproducible` builds twice and compares every hash.
- The output contains `manifest.jsonl` (all labels and metadata for each PDF), `SHA256SUMS`, `dropped.json`
  and a generated `DATASET_CARD.md` with counts and a dataset fingerprint.

## Splits and protocol

`dev` uses deepset's train split and `test` uses deepset's test split, so no injection text appears in both.
NotInject is split 50/50 by content hash. Tune on `dev` only. The evaluator prints error examples only for `dev`.

## Labels and operating points

Injected = 1; clean and benign = 0. pif reports hidden injections as HIGH and visible or non-visual ones as
MEDIUM. So **≥MEDIUM** answers "is any injection present?" and **≥HIGH** answers "is an injection hidden?".

## Licenses

deepset/prompt-injections: Apache-2.0 · NotInject: MIT · generator and host texts: AGPL-3.0 (this repository).
