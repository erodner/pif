# How the synthetic corpus was generated

The corpus (`corpus_v1.jsonl`) is **frozen and checked in**. Rebuilding the head needs only
`audit.py` and `train_head.py`, no LLM. This file records how the raw files in `raw/` were produced.

- Generator: Claude Code sub-agents (model claude-opus-5-5), 2026-11-20. One agent per slice, run in
  parallel, no tool access to the repository except writing their own output files. Web access was not used.
- Every agent prompt contains the definition and rules from `SPEC.md`, the forbidden-sources rule (no
  reproducing or paraphrasing known injection datasets or benchmarks), and a non-harm rule (fictional
  names, example.com, fake keys).

| Slice | Files | Content |
|---|---|---|
| A | `A_part*.jsonl` | 400 EN injections: override, sysprompt, refusal, persona, opinion, output |
| B | `B_part*.jsonl` | 400 EN injections: taskswap, exfil, tool, evaluation, steering, conceal |
| C | `C_part*.jsonl` | 400 injections: 340 DE (all 12 intents), 30 FR, 30 ES |
| D | `D_part*.jsonl` | 400 EN hard negatives: trigger, human_instr, meta, prose, request, creative |
| E | `E_part*.jsonl` | 400 hard negatives: 300 DE, 30 FR, 30 ES, 40 EN trigger questions |
| F | `F_part*.jsonl` | 400 EN topic-matched negatives (review/eval, summaries, security, systems, rules, AI assistants, roles, opinions) |
| G | `G_part*.jsonl` | 400 DE topic-matched negatives (same topics plus plain CV/document fragments) |
| H | `H_part*.jsonl` | 200 contrastive minimal pairs (120 EN, 70 DE, 10 FR/ES): injection and benign twin on the same topic |

Round 2 (F, G, H) was added after a diagnosis: the head trained on A–E flagged ordinary document prose about
reviews, references and grades, and plain German prose (topic and language shortcuts). The diagnosis used the
PlantedPI-PDF host-document sentences, which occur in both its dev and test splits. They were never shown to the
generators and never used for training: `audit.py` drops anything close to them. No evaluation payloads were
shown to any generator.

`audit.py` then removes exact and near duplicates and drops anything close to an evaluation text:
deepset, NotInject, PlantedPI-PDF host documents, and CrackedPDFs payloads/confounders. See `AUDIT.md`.
