# Synthetic corpus v1: audit

Raw lines: 3200 · exact duplicates removed: 0 · near duplicates (cos ≥ 0.95) removed: 0
Contamination drops (cos ≥ 0.9 or shared 8-gram): none
Reference texts: deepset 662, notinject 339, planted_hosts 129, crackedpdfs 406

**Final corpus: 3200 texts** (1400 injections, 1800 benign) · sha256 `16f672c6cb2c3d9c`

By label/language: ben/de 770, ben/en 960, ben/es 35, ben/fr 35, inj/de 410, inj/en 920, inj/es 35, inj/fr 35

By intent/category: conceal 117, contrast 200, creative 124, evaluation 120, exfil 120, human_instr 127, meta 127, opinion 115, output 114, override 119, persona 117, prose 127, refusal 117, request 126, steering 112, sysprompt 117, taskswap 115, tool 117, topic_match 800, trigger 169

Similarity of kept texts to their nearest evaluation text (MiniLM cosine):

| < 0.5 | 0.5–0.6 | 0.6–0.7 | 0.7–0.8 | 0.8–0.85 | 0.85–0.9 |
|---|---|---|---|---|---|
| 2260 | 806 | 111 | 22 | 0 | 1 |

Dropped examples (synthetic → nearest reference):

