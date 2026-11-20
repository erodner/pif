# pif on PlantedPI-PDF (test)

Generated 2026-11-20 20:21. Real prompt-injection texts and hard benign texts, planted into synthetic PDF host documents with 16 techniques (hidden, non-visual and visible). Built by `bench/planted/build.py` (seed 20261120); PyMuPDF 2.1. Dataset fingerprint: `de0c0b48c3ba9c23`.

1080 PDFs = 360 triads (clean / benign confounder / injected).

By design, pif reports hidden injections as HIGH and visible or non-visual (metadata, annotation) injections as MEDIUM. So **≥MEDIUM** is the operating point for *any injection present*, and **≥HIGH** for *hidden injection*.

## Overall

| Config | Op | Precision | Recall | F1 | FPR (all neg.) | FPR benign confounder | FPR clean | ROC-AUC | PR-AUC | Paired rank |
|---|---|---|---|---|---|---|---|---|---|---|
| pif rules (default) | ≥HIGH | 1.000 | 0.064 | **0.120** | 0.000 | 0.000 | 0.000 | 0.703 | 0.503 | 0.543 |
| pif rules (default) | ≥MEDIUM | 1.000 | 0.083 | **0.154** | 0.000 | 0.000 | 0.000 | 0.703 | 0.503 | 0.543 |
| pif rules + embedding | ≥HIGH | 0.908 | 0.275 | **0.422** | 0.014 | 0.028 | 0.000 | 0.745 | 0.624 | 0.658 |
| pif rules + embedding | ≥MEDIUM | 0.819 | 0.389 | **0.527** | 0.043 | 0.086 | 0.000 | 0.745 | 0.624 | 0.658 |
| pif rules + embedding + classifier | ≥HIGH | 0.908 | 0.275 | **0.422** | 0.014 | 0.028 | 0.000 | 0.774 | 0.655 | 0.688 |
| pif rules + embedding + classifier | ≥MEDIUM | 0.723 | 0.450 | **0.555** | 0.086 | 0.172 | 0.000 | 0.774 | 0.655 | 0.688 |
| pif all (+ OCR) | ≥HIGH | 0.910 | 0.281 | **0.429** | 0.014 | 0.028 | 0.000 | 0.782 | 0.662 | 0.692 |
| pif all (+ OCR) | ≥MEDIUM | 0.724 | 0.458 | **0.561** | 0.087 | 0.175 | 0.000 | 0.782 | 0.662 | 0.692 |

## Recall per technique (injected, ≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| hidden: clipped | 22 | 0.045 | 0.545 | 0.727 | 0.727 |
| hidden: covered | 22 | 0.136 | 0.545 | 0.591 | 0.591 |
| hidden: glyph_remap | 11 | 0.000 | 0.000 | 0.000 | 0.273 |
| hidden: hidden_layer | 23 | 0.043 | 0.391 | 0.565 | 0.565 |
| hidden: microglyph | 23 | 0.043 | 0.652 | 0.696 | 0.696 |
| hidden: near_white | 22 | 0.091 | 0.455 | 0.500 | 0.500 |
| hidden: off_page | 23 | 0.130 | 0.565 | 0.565 | 0.565 |
| hidden: render_invisible | 22 | 0.091 | 0.455 | 0.545 | 0.545 |
| hidden: split_words | 23 | 0.087 | 0.435 | 0.565 | 0.565 |
| hidden: tiny | 22 | 0.091 | 0.500 | 0.545 | 0.545 |
| hidden: white | 33 | 0.091 | 0.515 | 0.606 | 0.606 |
| hidden: zero_opacity | 23 | 0.130 | 0.609 | 0.696 | 0.696 |
| nonvisual: annotation | 22 | 0.136 | 0.136 | 0.136 | 0.136 |
| nonvisual: metadata | 23 | 0.043 | 0.043 | 0.043 | 0.043 |
| visible: visible | 23 | 0.043 | 0.043 | 0.043 | 0.043 |
| visible: visible_small | 23 | 0.087 | 0.087 | 0.087 | 0.087 |

## Recall per technique (injected, ≥HIGH)

Only hidden techniques are expected to reach HIGH.

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| hidden: clipped | 22 | 0.045 | 0.364 | 0.364 | 0.364 |
| hidden: covered | 22 | 0.136 | 0.455 | 0.455 | 0.455 |
| hidden: glyph_remap | 11 | 0.000 | 0.000 | 0.000 | 0.182 |
| hidden: hidden_layer | 23 | 0.043 | 0.261 | 0.261 | 0.261 |
| hidden: microglyph | 23 | 0.043 | 0.348 | 0.348 | 0.348 |
| hidden: near_white | 22 | 0.091 | 0.455 | 0.455 | 0.455 |
| hidden: off_page | 23 | 0.130 | 0.391 | 0.391 | 0.391 |
| hidden: render_invisible | 22 | 0.091 | 0.318 | 0.318 | 0.318 |
| hidden: split_words | 23 | 0.087 | 0.391 | 0.391 | 0.391 |
| hidden: tiny | 22 | 0.091 | 0.455 | 0.455 | 0.455 |
| hidden: white | 33 | 0.091 | 0.333 | 0.333 | 0.333 |
| hidden: zero_opacity | 23 | 0.130 | 0.478 | 0.478 | 0.478 |
| nonvisual: annotation | 22 | 0.000 | 0.000 | 0.000 | 0.000 |
| nonvisual: metadata | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible_small | 23 | 0.000 | 0.000 | 0.000 | 0.000 |

## Recall per injection language (≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| de | 138 | 0.087 | 0.348 | 0.478 | 0.478 |
| en | 222 | 0.081 | 0.414 | 0.432 | 0.446 |

## False-positive rate per benign source and language (benign confounders, ≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| deepset / de | 109 | 0.000 | 0.037 | 0.037 | 0.037 |
| deepset / en | 75 | 0.000 | 0.053 | 0.053 | 0.053 |
| notinject / en | 138 | 0.000 | 0.167 | 0.391 | 0.399 |
| notinject / zh | 38 | 0.000 | 0.000 | 0.000 | 0.000 |

## False-positive rate per benign source (benign confounders, ≥HIGH)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| deepset / de | 109 | 0.000 | 0.000 | 0.000 | 0.000 |
| deepset / en | 75 | 0.000 | 0.000 | 0.000 | 0.000 |
| notinject / en | 138 | 0.000 | 0.072 | 0.072 | 0.072 |
| notinject / zh | 38 | 0.000 | 0.000 | 0.000 | 0.000 |

## False-positive rate per NotInject category (≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| - | 184 | 0.000 | 0.043 | 0.043 | 0.043 |
| Common Queries | 79 | 0.000 | 0.127 | 0.354 | 0.354 |
| Multilingual | 38 | 0.000 | 0.000 | 0.000 | 0.000 |
| Technique Queries | 45 | 0.000 | 0.289 | 0.511 | 0.533 |
| Virtual Creation | 14 | 0.000 | 0.000 | 0.214 | 0.214 |

## False-positive rate per technique (benign confounders, ≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| hidden: clipped | 22 | 0.000 | 0.227 | 0.364 | 0.364 |
| hidden: covered | 22 | 0.000 | 0.091 | 0.227 | 0.227 |
| hidden: glyph_remap | 11 | 0.000 | 0.000 | 0.000 | 0.091 |
| hidden: hidden_layer | 23 | 0.000 | 0.043 | 0.174 | 0.174 |
| hidden: microglyph | 23 | 0.000 | 0.174 | 0.435 | 0.435 |
| hidden: near_white | 22 | 0.000 | 0.045 | 0.091 | 0.091 |
| hidden: off_page | 23 | 0.000 | 0.130 | 0.348 | 0.348 |
| hidden: render_invisible | 22 | 0.000 | 0.136 | 0.182 | 0.182 |
| hidden: split_words | 23 | 0.000 | 0.174 | 0.261 | 0.261 |
| hidden: tiny | 22 | 0.000 | 0.091 | 0.136 | 0.136 |
| hidden: white | 33 | 0.000 | 0.061 | 0.121 | 0.121 |
| hidden: zero_opacity | 23 | 0.000 | 0.174 | 0.348 | 0.348 |
| nonvisual: annotation | 22 | 0.000 | 0.000 | 0.000 | 0.000 |
| nonvisual: metadata | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible_small | 23 | 0.000 | 0.000 | 0.000 | 0.000 |

## Errors: pif all (+ OCR), ≥MEDIUM

195 false negatives, 63 false positives.

(Error examples are not shown for the test split.)
