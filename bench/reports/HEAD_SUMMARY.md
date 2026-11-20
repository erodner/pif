# Injection head v1: test results (frozen configuration, one run per test split)

The head is a logistic regression on the bundled MiniLM embeddings (4 KB). It was trained only on a synthetic
corpus written by sub-agents from an intent spec (`bench/synth/`, audited: no text close to any evaluation
set). Thresholds were chosen on dev splits only. It runs in the default `rules + embedding` configuration,
so no extra model download is needed.

## CrackedPDFs, test split (2,919 PDFs)

| Detector | Precision | Recall | F1 | FPR | ROC-AUC | Paired rank |
|---|---|---|---|---|---|---|
| Hybrid (paper, **trained on CrackedPDFs**) | 0.926 | 0.998 | 0.960 | 0.040 | 0.998 | 0.959 |
| Rule baseline (paper) | 0.493 | 0.845 | 0.623 | 0.434 | 0.749 | – |
| PromptGuard (paper) | 0.860 | 0.252 | 0.390 | 0.021 | 0.858 | – |
| pif 0.5.1, all detectors ≥HIGH | 0.504 | 0.913 | 0.649 | 0.450 | 0.841 | 0.744 |
| pif before head, rules + embedding ≥HIGH | 1.000 | 0.584 | 0.737 | 0.000 | 0.896 | 0.792 |
| **pif with head, rules + embedding ≥HIGH** | 0.956 | 0.914 | **0.934** | 0.021 | **0.990** | 0.938 |

## PlantedPI-PDF, test split (1,080 PDFs)

| Configuration | Op | Precision | Recall | F1 | FPR benign twins | FPR clean | ROC-AUC |
|---|---|---|---|---|---|---|---|
| before head, rules + embedding | ≥MEDIUM | 0.949 | 0.156 | 0.267 | 0.008 | 0.000 | 0.714 |
| **with head, rules + embedding** | ≥HIGH | 0.908 | 0.275 | 0.422 | 0.028 | 0.000 | 0.745 |
| **with head, rules + embedding** | ≥MEDIUM | 0.819 | 0.389 | **0.527** | 0.086 | 0.000 | 0.745 |
| with head, + classifier + OCR | ≥MEDIUM | 0.724 | 0.458 | 0.561 | 0.175 | 0.000 | 0.782 |

German injection recall (rules + embedding): 0.087 → 0.348. Benign-twin false positives come mostly from English
NotInject trigger-word prompts (16.7%); deepset benign texts are flagged at 4–5%, Chinese texts and clean hosts never.

## Real documents

13 arXiv papers (6 with known hidden prompts) and 7 German Wikipedia articles: no new findings. The 6 attacks are
HIGH, and the head confirms each of them. The head is deliberately off for visible text and metadata: there it
over-fired on reference lists, tables of contents and few-shot examples.

## Remaining gaps

- Free-form chat injections (deepset): recall 39–46%; part of this is label noise.
- NotInject trigger-word prompts remain the main source of false positives.
- Acrostics (CrackedPDFs): 0% without the classifier.
