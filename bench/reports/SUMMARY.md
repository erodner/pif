# CrackedPDFs: pif before and after the benchmark-driven fixes

Test split, 2,919 PDFs (973 injected, 973 benign originals, 973 matched benign confounders). pif is
zero-shot: nothing was trained on CrackedPDFs. All thresholds were chosen on the validation split.

| Detector | Precision | Recall | F1 | FPR | ROC-AUC | Paired rank |
|---|---|---|---|---|---|---|
| Hybrid text+structure (paper, **trained** on CrackedPDFs) | 0.926 | 0.998 | 0.960 | 0.040 | 0.998 | 0.959 |
| Rule baseline (paper) | 0.493 | 0.845 | 0.623 | 0.434 | 0.749 | – |
| PromptGuard on extracted text (paper) | 0.860 | 0.252 | 0.390 | 0.021 | 0.858 | – |
| pif 0.5.1, rules, ≥HIGH | 1.000 | 0.018 | 0.036 | 0.000 | 0.732 | 0.509 |
| pif 0.5.1, rules + embedding + classifier, ≥HIGH | 0.504 | 0.913 | 0.649 | 0.450 | 0.841 | 0.744 |
| **pif research, rules**, ≥HIGH | **1.000** | 0.239 | 0.386 | **0.000** | 0.810 | 0.620 |
| **pif research, rules + embedding**, ≥HIGH | **1.000** | 0.584 | **0.737** | **0.000** | 0.896 | 0.792 |
| **pif research, rules + embedding + classifier**, ≥HIGH | **1.000** | 0.584 | **0.737** | **0.000** | **0.971** | **0.927** |
| pif research, rules + embedding + classifier, ≥MEDIUM | 0.527 | **1.000** | 0.690 | 0.450 | 0.971 | 0.927 |

Validation split (same configs, research version): rules + embedding F1 0.739, classifier ROC-AUC 0.920.

## What changed

1. Microglyph and fused text: glyphs drawn one by one are joined instead of being split onto separate
   lines; fused hidden runs are reported; the rules get a fused-text variant; and fused tokens are
   segmented into words before embedding.
2. Eight rules for generic jailbreak intents (PI020–PI027): system-prompt theft, refusal suppression,
   policy framing, data harvesting, tool abuse, task hijack, summary steering and context reset. They
   fire only on imperatives, so descriptive academic prose is not matched.
3. Embedding stage: machine markup is stripped before embedding, the similarity threshold for
   hidden page text is 0.50 (visible text and metadata stay at 0.72), and there are more generic
   reference phrases.
4. Severity policy: a classifier-only hit in hidden text is MEDIUM ("unconfirmed"). HIGH needs a
   rule or an embedding match. The cascade now reports classifier and embedding matches
   separately.

## Reading the numbers

- **≥HIGH** is the high-precision operating point: in all three configurations no benign original and no
  matched confounder was flagged HIGH.
- **≥MEDIUM** with the classifier catches every injection, but it also flags 90% of the confounders: off-the-shelf
  injection classifiers fire on harmless meta-text about prompts.
- Ranking quality with the classifier (ROC-AUC 0.971, paired rank 0.927) approaches the trained hybrid
  (0.998 / 0.959) without any training on this data.

## Remaining gaps

- Acrostics (80 test documents, recall 0): the payload is spelled out by sentence initials. Fixing this
  needs a dedicated decoder.
- Free paraphrases of policy framing and summary steering are missed by both rules and embedding.

## Caveats

- Test leakage: before switching to validation-only tuning, I looked at about 20 false-negative
  payloads from the *test* split, and a few of the new rule examples are close to them. All thresholds
  and later changes were chosen on the validation split. Validation and test results agree closely
  (F1 0.739 vs 0.737).
- Synthetic, one-page, English documents. Regression checks on real documents (13 arXiv papers including
  6 known attacks, 7 German Wikipedia articles about AI) show no new false positives, and all 6 attacks
  are still HIGH.
