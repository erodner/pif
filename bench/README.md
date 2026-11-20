# Benchmarks

| Benchmark | What it tests | Source |
|---|---|---|
| [CrackedPDFs](#crackedpdfs) | 15 hiding techniques, synthetic payloads, matched benign confounders; published baselines | external (arXiv 2607.19396) |
| [PlantedPI-PDF](planted/README.md) | real injection texts (EN/DE) + hard benign trigger-word texts (NotInject) planted with 16 techniques | built reproducibly by `planted/build.py` |

## CrackedPDFs

[CrackedPDFs](https://arxiv.org/abs/2607.19396) ([dataset](https://huggingface.co/datasets/volkthienpreecha/crackedpdfs),
MIT) is a controlled benchmark for hidden prompt injection in PDFs:

- 29,322 synthetic one-page PDFs, built as triads from the same base document: a benign original, a benign *confounder*
  (benign text hidden with the same technique, in the same place) and an injected attack.
- 15 attack families (white, tiny, invisible and low-contrast text, split text objects, layout mimicry, semantic
  fragmentation, margin microtext, acrostics, microglyph steganography, …) and 8 payload types (system-prompt
  extraction, refusal suppression, exfiltration, tool manipulation, task hijack, …).
- A frozen test split of 2,919 documents (973 per role), with published baselines.

```bash
python bench/crackedpdfs.py fetch                                  # ~650 MB download (pinned + checksummed), ~870 MB extracted
python bench/crackedpdfs.py run --split test --configs R,RE,REC -j 3
python bench/crackedpdfs.py report --split test --configs R,RE,REC --shuffle-check
python bench/crackedpdfs.py all --limit 60 --configs R             # quick smoke test on a random subset
```

Configurations: `R` = rules + visibility checks (the default without models), `RE` = + MiniLM embedding,
`REC` = + DeBERTa classifier, `all` = + OCR glyph check. The ML configurations need `pif models download`.

Each document's report becomes:

- a **score**: max over findings of (severity rank + 0.99·semantic score)/4, used for ROC-AUC, PR-AUC and paired ranking;
- two **decisions**: *injected* if pif reports ≥ HIGH (strict) or ≥ MEDIUM (sensitive).

Per-document results are cached in `bench/results/<split>-<config>.jsonl`, so reruns resume. Reports are written to
`bench/results/crackedpdfs-<split>-<timestamp>.md` with `.json` metrics and a per-document `.csv`.

Comparison: the report puts pif next to the paper's hybrid detector, rule baseline and PromptGuard. Their numbers
come from the dataset's `metrics/` folder: overall, per attack family, per payload type and per benign confounder family.

### Caveats

- **Zero-shot vs. trained.** The paper's hybrid detector is trained on the CrackedPDFs train split. pif is not
  trained or tuned on this data. If you tune anything, use `--split val`, never the test split.
- **Erratum (2026-09-13).** Most payloads start at the bottom-left page corner and extend below the page, so whether
  text is *hidden* is easy to tell. What the benchmark really tests is telling injected payloads apart from matched
  benign hidden text.
- **Shortcut tokens.** Payloads carry wrapper tokens (`[DATASET_SAMPLE_ID=…]`, `<SYSTEM_POLICY_DO_NOT_REMOVE>`). That is
  why the paper's TF-IDF comparator scores perfectly. pif's rules do not use them.
- **Scope.** The documents are synthetic, one page long and English only. There are no glyph-remapping fonts and no real-world documents.
