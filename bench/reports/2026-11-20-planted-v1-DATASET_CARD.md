# PlantedPI-PDF v1

Real prompt-injection texts and hard benign texts, planted into synthetic PDF host documents with 16 techniques (hidden, non-visual and visible). Built by `bench/planted/build.py` (seed 20261120); PyMuPDF 2.1. Dataset fingerprint: `de0c0b48c3ba9c23`.

## Sources

| Source | Revision | License | Used as |
|---|---|---|---|
| [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections) | `4f61ecb` | Apache-2.0 | injections (label 1) and benign prompts; train→dev, test→test |
| [leolee99/NotInject](https://huggingface.co/datasets/leolee99/NotInject) | `847ae76` | MIT | hard benign prompts with trigger words; 50/50 dev/test by content hash |

Host documents are synthetic (fictional names), written for this benchmark (`bench/planted/hosts.py`).

## Structure

Each triad has one host document in three versions: `clean`, `benign` (benign text planted with technique *T*) and `injected` (injection planted with the same *T* in the same place). Labels: injected = 1, else 0.

Techniques. Hidden: white, near_white, tiny, render_invisible, zero_opacity, off_page, hidden_layer, covered, clipped, microglyph, split_words, glyph_remap. Non-visual: metadata, annotation. Visible: visible, visible_small. Non-Latin texts fall back from `clipped`/`glyph_remap` to `white`.

## Counts

### dev: 599 triads, 1797 PDFs

- techniques: annotation 38, clipped 36, covered 38, glyph_remap 27, hidden_layer 36, metadata 38, microglyph 38, near_white 38, off_page 37, render_invisible 38, split_words 37, tiny 39, visible 38, visible_small 38, white 48, zero_opacity 35
- channels: nonvisual 76, hidden 447, visible 76
- injection language: en 370, de 229
- benign source: notinject 245, deepset 354; benign language: en 331, zh 48, de 220
- host language: en 364, de 235; genres: memo 164, cv 131, datasheet 163, paper 141

### test: 360 triads, 1080 PDFs

- techniques: annotation 22, clipped 22, covered 22, glyph_remap 11, hidden_layer 23, metadata 23, microglyph 23, near_white 22, off_page 23, render_invisible 22, split_words 23, tiny 22, visible 23, visible_small 23, white 33, zero_opacity 23
- channels: hidden 269, nonvisual 45, visible 46
- injection language: en 222, de 138
- benign source: notinject 176, deepset 184; benign language: zh 38, en 213, de 109
- host language: en 237, de 123; genres: memo 85, paper 85, datasheet 92, cv 98

Dropped triads (planted text not extractable or inconsistent fallback): 10 (see `dropped.json`).

## Known limitations

- deepset labels contain some noise (e.g. plain task requests such as "Generate SQL code to access a database" are labelled as injections). Labels are used as published.
- Most deepset injections are chat-style jailbreaks, not document-style injections ("give a positive review"). They test how detection generalises, not peer-review attacks specifically.
- Emoji are stripped from texts (PDF base fonts cannot encode them).
- Host documents are one page and synthetic.

## Use

Tune only on `dev`; report `test`. Evaluate with `python bench/planted/evaluate.py`.
