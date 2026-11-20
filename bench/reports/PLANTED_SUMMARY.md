# PlantedPI-PDF v1: first results (research branch, before any tuning on this dataset)

Dataset fingerprint `de0c0b48c3ba9c23`. Test split: 360 triads = 1,080 PDFs (360 injected, 360 matched benign, 360 clean).

| pif configuration | Op | Precision | Recall | F1 | FPR benign twins | ROC-AUC | Paired rank |
|---|---|---|---|---|---|---|---|
| rules | ≥HIGH | 1.000 | 0.064 | 0.120 | 0.000 | 0.703 | 0.543 |
| rules | ≥MEDIUM | 1.000 | 0.083 | 0.154 | 0.000 | 0.703 | 0.543 |
| + embedding | ≥MEDIUM | 0.949 | 0.156 | 0.267 | 0.008 | 0.714 | 0.569 |
| + classifier | ≥HIGH | 0.942 | 0.136 | 0.238 | 0.008 | 0.756 | 0.629 |
| + classifier | ≥MEDIUM | 0.731 | 0.339 | 0.463 | 0.125 | 0.756 | 0.629 |
| + OCR | ≥MEDIUM | 0.732 | 0.342 | 0.466 | 0.125 | 0.762 | 0.632 |

Dev split (599 triads) agrees: rules ≥MEDIUM F1 0.104; + classifier ≥MEDIUM F1 0.532.

## Findings

- Hiding is not the bottleneck: recall is similar across all 12 hidden techniques. The bottleneck is recognising
  free-form chat-style injections (deepset) by their wording.
- Visible and non-visual injections are almost never detected (4–14%): the classifier does not run on visible text,
  and classifier-only hits in metadata or annotations are reported as LOW by design.
- False positives come only from English NotInject trigger-word prompts flagged by the classifier: 33% at ≥MEDIUM,
  2% at ≥HIGH. German and Chinese benign texts and clean hosts are never flagged.
- German recall with the classifier (0.377) is similar to English (0.315); rules alone reach 9%.
- deepset label noise (plain questions labelled as injections) caps achievable recall.

## Next (tune on dev only)

1. Rules for generic chat hijacks ("forget about everything …", "say/state that …", "act as …").
2. A multilingual embedding model with German reference phrases.
3. Let the classifier confirm visible and non-visual hits when the embedding agrees.
