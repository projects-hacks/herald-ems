# Gold labels for the every-call keys (run E)

`gold_v1_broad.jsonl` and `gold_v2_broad.jsonl` label only the keys added for every call type (LABELING_GUIDE §4e;
the `broad` group in `eval/scoring.yaml`) on the existing dev (v1) and held-out (v2) texts. Two annotators labeled
them blind, from the texts only (`*_broad_a.jsonl`, `*_broad_b.jsonl`); neither saw the other's labels, the main
gold files, training data or model output.

- Agreement as scored (free-text trauma phrases by presence): F1 0.986 (v1), 0.993 (v2), including the later keys
  trauma.criteria, ecg.stemi_reading and ecg.transmitted. No role disagreements.
- Adjudication: annotator B's labels, which match every settled rule. The one disagreement ("one nitro" given a dose
  of 1) was settled as no dose: a count of tablets is not a dose in a unit. v2_034 gets "can't feel his feet" as an
  injury found, under the §4e rule both annotators flagged (new sensory loss after trauma).
- These sets hold few of the new keys (v1: 23 facts; v2: 45); `gold_v3.jsonl` (every call type, 100 utterances,
  written for them) is the main held-out measure for the new keys.

# gold_v3: every call type (100 utterances, held out)

Written and labeled by one annotator (`gold_v3.jsonl`, texts in `gold_v3_texts.jsonl`) and labeled blind by a second
(`gold_v3_labeler_b.jsonl`), each from the labeling guide only. Categories: medical 20, arrest/ROSC 12, trauma 20,
sepsis 12, stroke 12, general 14, other speakers 10; dispatches vary (31 kinds).

- Agreement as scored: main keys F1 0.993, free-text presence 0.966, every-call keys 0.955, G.F.A.S.T. 1.000.
- Most every-call disagreements were one convention (the giver on a bare listing: "crew" vs left out), settled as
  "crew" and written into LABELING_GUIDE §4e. The second labeler's chief complaints for a stated arrest or found-down
  patient were adopted (§4c: a stated presenting problem). The rest follow the writer.
- Coverage limits: ecg.transmitted never occurs and ecg.stemi_reading twice; those two keys are measured on the
  training dev split only.

# gold_ctx: the call's dispatch as context (60 utterances, held out)

Measures LABELING_GUIDE §4c's dispatch rule: under a stroke dispatch, last known well and onset witnessed are facts
even in a sentence with no symptoms; under other dispatches, the same words give no stroke facts unless stroke-like
signs are described. 36 stroke-dispatch lines (21 with no symptom words), 24 other-dispatch lines (15 tempting
contrasts, 4 with stroke signs described, 5 ordinary). Category in each line's `notes` (`cat=...`).

- Written and labeled by one annotator (`gold_ctx.jsonl`), labeled blind by a second (`gold_ctx_labeler_b.jsonl`).
- Agreement: F1 1.000 on the main keys (199 atoms), G.F.A.S.T. 1.000, stroke.lkw 20/20, onset witnessed 23/23. The
  lines were written to be unambiguous, so this is an upper bound on label quality, not proof.
- The every-call keys (§4e) didn't exist when the set was written; the second labeler's 14 such facts were added.
