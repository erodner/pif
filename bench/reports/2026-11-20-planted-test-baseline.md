# pif on PlantedPI-PDF (test)

Generated 2026-11-20 13:13. Real prompt-injection texts and hard benign texts, planted into synthetic PDF host documents with 16 techniques (hidden, non-visual and visible). Built by `bench/planted/build.py` (seed 20261120); PyMuPDF 2.1. Dataset fingerprint: `de0c0b48c3ba9c23`.

1080 PDFs = 360 triads (clean / benign confounder / injected).

By design, pif reports hidden injections as HIGH and visible or non-visual (metadata, annotation) injections as MEDIUM. So **≥MEDIUM** is the operating point for *any injection present*, and **≥HIGH** for *hidden injection*.

## Overall

| Config | Op | Precision | Recall | F1 | FPR (all neg.) | FPR benign confounder | FPR clean | ROC-AUC | PR-AUC | Paired rank |
|---|---|---|---|---|---|---|---|---|---|---|
| pif rules (default) | ≥HIGH | 1.000 | 0.064 | **0.120** | 0.000 | 0.000 | 0.000 | 0.703 | 0.503 | 0.543 |
| pif rules (default) | ≥MEDIUM | 1.000 | 0.083 | **0.154** | 0.000 | 0.000 | 0.000 | 0.703 | 0.503 | 0.543 |
| pif rules + embedding | ≥HIGH | 0.942 | 0.136 | **0.238** | 0.004 | 0.008 | 0.000 | 0.714 | 0.533 | 0.569 |
| pif rules + embedding | ≥MEDIUM | 0.949 | 0.156 | **0.267** | 0.004 | 0.008 | 0.000 | 0.714 | 0.533 | 0.569 |
| pif rules + embedding + classifier | ≥HIGH | 0.942 | 0.136 | **0.238** | 0.004 | 0.008 | 0.000 | 0.756 | 0.611 | 0.629 |
| pif rules + embedding + classifier | ≥MEDIUM | 0.731 | 0.339 | **0.463** | 0.062 | 0.125 | 0.000 | 0.756 | 0.611 | 0.629 |
| pif all (+ OCR) | ≥HIGH | 0.942 | 0.136 | **0.238** | 0.004 | 0.008 | 0.000 | 0.762 | 0.616 | 0.632 |
| pif all (+ OCR) | ≥MEDIUM | 0.732 | 0.342 | **0.466** | 0.062 | 0.125 | 0.000 | 0.762 | 0.616 | 0.632 |

## Recall per technique (injected, ≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| hidden: clipped | 22 | 0.045 | 0.091 | 0.591 | 0.591 |
| hidden: covered | 22 | 0.136 | 0.227 | 0.409 | 0.409 |
| hidden: glyph_remap | 11 | 0.000 | 0.000 | 0.000 | 0.091 |
| hidden: hidden_layer | 23 | 0.043 | 0.130 | 0.391 | 0.391 |
| hidden: microglyph | 23 | 0.043 | 0.087 | 0.391 | 0.391 |
| hidden: near_white | 22 | 0.091 | 0.182 | 0.318 | 0.318 |
| hidden: off_page | 23 | 0.130 | 0.217 | 0.435 | 0.435 |
| hidden: render_invisible | 22 | 0.091 | 0.182 | 0.455 | 0.455 |
| hidden: split_words | 23 | 0.087 | 0.261 | 0.435 | 0.435 |
| hidden: tiny | 22 | 0.091 | 0.227 | 0.364 | 0.364 |
| hidden: white | 33 | 0.091 | 0.182 | 0.545 | 0.545 |
| hidden: zero_opacity | 23 | 0.130 | 0.304 | 0.522 | 0.522 |
| nonvisual: annotation | 22 | 0.136 | 0.136 | 0.136 | 0.136 |
| nonvisual: metadata | 23 | 0.043 | 0.043 | 0.043 | 0.043 |
| visible: visible | 23 | 0.043 | 0.043 | 0.043 | 0.043 |
| visible: visible_small | 23 | 0.087 | 0.087 | 0.087 | 0.087 |

## Recall per technique (injected, ≥HIGH)

Only hidden techniques are expected to reach HIGH.

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| hidden: clipped | 22 | 0.045 | 0.091 | 0.091 | 0.091 |
| hidden: covered | 22 | 0.136 | 0.227 | 0.227 | 0.227 |
| hidden: glyph_remap | 11 | 0.000 | 0.000 | 0.000 | 0.000 |
| hidden: hidden_layer | 23 | 0.043 | 0.130 | 0.130 | 0.130 |
| hidden: microglyph | 23 | 0.043 | 0.087 | 0.087 | 0.087 |
| hidden: near_white | 22 | 0.091 | 0.182 | 0.182 | 0.182 |
| hidden: off_page | 23 | 0.130 | 0.217 | 0.217 | 0.217 |
| hidden: render_invisible | 22 | 0.091 | 0.182 | 0.182 | 0.182 |
| hidden: split_words | 23 | 0.087 | 0.261 | 0.261 | 0.261 |
| hidden: tiny | 22 | 0.091 | 0.227 | 0.227 | 0.227 |
| hidden: white | 33 | 0.091 | 0.182 | 0.182 | 0.182 |
| hidden: zero_opacity | 23 | 0.130 | 0.304 | 0.304 | 0.304 |
| nonvisual: annotation | 22 | 0.000 | 0.000 | 0.000 | 0.000 |
| nonvisual: metadata | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible_small | 23 | 0.000 | 0.000 | 0.000 | 0.000 |

## Recall per injection language (≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| de | 138 | 0.087 | 0.087 | 0.377 | 0.377 |
| en | 222 | 0.081 | 0.198 | 0.315 | 0.320 |

## False-positive rate per benign source and language (benign confounders, ≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| deepset / de | 109 | 0.000 | 0.000 | 0.000 | 0.000 |
| deepset / en | 75 | 0.000 | 0.000 | 0.000 | 0.000 |
| notinject / en | 138 | 0.000 | 0.022 | 0.326 | 0.326 |
| notinject / zh | 38 | 0.000 | 0.000 | 0.000 | 0.000 |

## False-positive rate per benign source (benign confounders, ≥HIGH)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| deepset / de | 109 | 0.000 | 0.000 | 0.000 | 0.000 |
| deepset / en | 75 | 0.000 | 0.000 | 0.000 | 0.000 |
| notinject / en | 138 | 0.000 | 0.022 | 0.022 | 0.022 |
| notinject / zh | 38 | 0.000 | 0.000 | 0.000 | 0.000 |

## False-positive rate per NotInject category (≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| - | 184 | 0.000 | 0.000 | 0.000 | 0.000 |
| Common Queries | 79 | 0.000 | 0.013 | 0.291 | 0.291 |
| Multilingual | 38 | 0.000 | 0.000 | 0.000 | 0.000 |
| Technique Queries | 45 | 0.000 | 0.044 | 0.422 | 0.422 |
| Virtual Creation | 14 | 0.000 | 0.000 | 0.214 | 0.214 |

## False-positive rate per technique (benign confounders, ≥MEDIUM)

| Group | n | pif rules (default) | pif rules + embedding | pif rules + embedding + classifier | pif all (+ OCR) |
|---|---|---|---|---|---|
| hidden: clipped | 22 | 0.000 | 0.045 | 0.273 | 0.273 |
| hidden: covered | 22 | 0.000 | 0.000 | 0.227 | 0.227 |
| hidden: glyph_remap | 11 | 0.000 | 0.000 | 0.000 | 0.000 |
| hidden: hidden_layer | 23 | 0.000 | 0.000 | 0.130 | 0.130 |
| hidden: microglyph | 23 | 0.000 | 0.000 | 0.261 | 0.261 |
| hidden: near_white | 22 | 0.000 | 0.000 | 0.091 | 0.091 |
| hidden: off_page | 23 | 0.000 | 0.043 | 0.261 | 0.261 |
| hidden: render_invisible | 22 | 0.000 | 0.000 | 0.136 | 0.136 |
| hidden: split_words | 23 | 0.000 | 0.000 | 0.130 | 0.130 |
| hidden: tiny | 22 | 0.000 | 0.000 | 0.136 | 0.136 |
| hidden: white | 33 | 0.000 | 0.000 | 0.091 | 0.091 |
| hidden: zero_opacity | 23 | 0.000 | 0.043 | 0.217 | 0.217 |
| nonvisual: annotation | 22 | 0.000 | 0.000 | 0.000 | 0.000 |
| nonvisual: metadata | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible | 23 | 0.000 | 0.000 | 0.000 | 0.000 |
| visible: visible_small | 23 | 0.000 | 0.000 | 0.000 | 0.000 |

## Errors: pif all (+ OCR), ≥MEDIUM

237 false negatives, 45 false positives.

(Error examples are not shown for the test split.)
