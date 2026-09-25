# gold_newkeys_v1: the six keys added for run F (84 utterances, held out)

The six keys and fields the owner added on 2026-09-24 (`docs/TRAINING_PLAN.md` §8 decision 1) were labeled into the
run F **training** data, but until now they had **no independent test set**: gold v1/v2/v3/ctx predate them, so a run F
model's accuracy on them could only be read off its own dev split. This set measures them on held-out speech.

| File | What it is |
|---|---|
| `gold_newkeys_v1_texts.jsonl` | The 84 inputs: `id`, `dispatch`, `text`, `by`, `speaker` (the shape of `gold_v3_texts.jsonl`) |
| `gold_newkeys_v1.jsonl` | Adjudicated gold: the inputs plus `facts`, `phenomena`, `notes` |
| `gold_newkeys_v1_labeler_a.jsonl` | Pass A, kept as it was labeled (for agreement) |
| `gold_newkeys_v1_labeler_b.jsonl` | Pass B, kept as it was labeled (for agreement) |

`facts` is a **list of `[key, value, role]`**, with a 4th element for the source's relation where §3 needs one —
the format `eval/bench_extract.py` reads, as in `gold_v3.jsonl`. A record key (`meds.given`, `procedures.done`)
contributes one fact per event, its value the record object.

## Roles (§3)

Every fact on the medic's mic is `medic`: no line has the medic attributing a clause to someone else, and a dose
someone else gave is still the medic's report with the giver in the record's own `by` field (§5e.10). The 7 lines on
another mic take the speaker's role, with the relation as the 4th element:

| Speaker | Role | Why |
|---|---|---|
| wife, husband, daughter | `family` | §3 |
| facility nurse | `family` | §3: facility staff are caregivers, adjudicated on v1_039 |
| friend | `bystander` | §4e lists friend/coworker/coach/security as bystanders |
| incident command | `bystander` | §5e.13: a responder on the mic giving a triage category or airway status |

Roles were assigned once, after adjudication, and **none of them was a judgement call** — each follows explicit guide
text, so there was no role disagreement to adjudicate. Distribution: 111 `medic`, 7 `family`, 2 `bystander`;
9 facts carry a relation.

## What scores each of the six keys

A key reaches exactly one scorer: the main headline F1, the free-text presence score, or a group in
`eval/scoring.yaml` measured with `--group-gold`. No new group was added — the six keys already land as follows, and
`tests/test_gold_selfscore.py` pins it so a later change to `FREE_TEXT` or `scoring.yaml` cannot silently drop one:

| Key | Scored by | Why |
|---|---|---|
| `triage.category` | main headline F1 | structured enum |
| `airway.status` | main headline F1 | structured enum |
| `ecg.territory` | main headline F1 | structured list; not in the `broad` key list |
| `impression.primary` | free-text presence | the medic's own words (§5d.4 "short, lowercase, as said"), so "sepsis from a uti" and "urosepsis" are the same answer. **Added to `FREE_TEXT` on 2026-09-25**; no gold set published before this one uses the key, so no earlier number changes |
| `trauma.injury_time` | group `broad` | inside the existing `trauma.` prefix |
| `before_arrival` | group `broad` | a field on `meds.given` / `procedures.done`, both already `broad` keys |

So scoring this set needs `--group-gold broad=eval/gold_newkeys_v1.jsonl`; without it, `trauma.injury_time` and the
dose and procedure records are not measured at all.

## How it was made

- **Independent of the training data.** The texts were written from `docs/LABELING_GUIDE.md` and
  `config/vocabulary.yaml` only. Nothing under `data/` was opened — not the annotated batches, not `data/train_*`.
  Every line is invented; there is no patient data.
- **Two labeling passes, then adjudication.** Pass 0 wrote the 84 texts with no labels, so both labeling passes read
  only `{id, dispatch, text, by, speaker}`. Pass A and pass B labeled independently; the 11 differing items were
  settled from the guide alone, and each ruling is recorded in that item's `notes` with the section that decides it.
- **Caveat, stated plainly:** both passes were made by the same kind of annotator working from the same written
  guide. The agreement below measures how unambiguous the guide is on these lines, not two independent clinical
  opinions. This is the same caveat as `README_gold_es.md`.

## Agreement (before adjudication)

| | |
|---|---|
| Items labeled identically | **73 of 84 (86.9%)** |
| Atom F1 | **0.919** (precision 0.912, recall 0.927) |
| Atoms both passes agreed on | 114 |
| Items adjudicated | 11 (guide supported pass A 5 times, pass B 7 times) |

**Every one of the six new keys agreed on every item.** All 11 disagreements were on incidental keys that happened to
be in the same sentence: `complaint.chief` wording (3), `trauma.mechanism` wording (3), `trauma.injuries` wording (1),
whether a BVM rate is `vitals.rr` (2), whether a transmission time is `ecg.twelve_lead_time` (1), and whether a brand
or product name fills `route` (2). The rulings that matter for the future:

- **A BVM rate the crew delivers is not `vitals.rr`** (§4: `vitals.rr` is the patient's respirations). "bagging her
  at about ten a minute" gives the airway status, not a respiratory rate.
- **A transmission time is not `ecg.twelve_lead_time`** (§4): in "transmitted to Valley at 1408" the time belongs to
  the send, not to when the 12-lead was done.
- **`route` is filled only from a route word** (§5e.17), so an EpiPen with no site gives no IM, and "oral glucose gel
  in his cheek" gives no PO — "oral" there is the product's name, not the route.

## Composition

84 items: **67 with facts, 17 with none** (20%). 7 are on someone else's mic (`by: "other"`: wife, husband, daughter,
friend, facility nurse, incident command). Each new key has positives and hard negatives written against the specific
traps in §5d:

| Key | Positives | Hard negatives | What the negatives test |
|---|---|---|---|
| `triage.category` | 11 | 5 | triage words outside tagging: "red and swollen", "green sputum", "yellow skin", "immediate relief", "the triage nurse" |
| `airway.status` | 11 | 4 | airway words that state no status: "check the airway", "grab the airway kit", "we'll put an i-gel in", "airway?" as a question |
| `impression.primary` | 10 | 6 | a family member's guess, a call label ("STEMI alert"), a chief complaint, the other sense of the word ("the seatbelt left an impression"), a hedge, a differential ("X versus Y") |
| `trauma.injury_time` | 6 | 4 | a discovery time ("found him down at 0600"), a medical onset with no injury, a hedged time ("sometime after the fight") |
| `ecg.territory` | 9 | 5 | leads alone ("elevation in two, three and aVF"), reciprocal changes, a negative ("no inferior involvement") |
| `before_arrival` | 7 records | 6 | a family or facility dose with only a clock time, a routine daily dose, "bystander CPR" with no timing, a plan, a refusal |

Enum coverage is complete: all 5 SALT categories, all 6 `airway.status` values, all 6 `ecg.territory` values.
Also exercised: a retag (the last category wins), a category stated for a different patient (gives none for this
one), counts across patients, `airway.status` from a responder on the mic (§5e.13), an adjunct plus bagging
(§5e.13), two tracings in one utterance (§5e.3), and the patient's own dose for this problem (§5d.6).

## Checks done when the set was built

- **Decontaminated against `data/train_f`** (7,509 texts): no item shares an 8-word run with a training text, and no
  item's words equal one. The first run of this check **failed on 3 items** — phrasings lifted unconsciously from the
  guide's own examples, which are themselves in the training data ("took two of his own nitros before we got there",
  "took her Eliquis this morning", and one line matching a training text exactly). Those three were rewritten to test
  the same rules with different words and both passes relabeled.
- **Every fact validates against `config/vocabulary.yaml`**: known keys, correct types, enum members, known record
  fields, and field ranges. 0 errors.
- **Replayed as its own predictions it scores 1.000 on every part**: headline precision/recall/F1 1.000, role
  accuracy 1.000, free-text presence F1 1.000, and the `broad` group 1.000 over 74 atoms. Command:

  ```bash
  $PY eval/bench_extract.py --rescore <self-prediction dump> --gold eval/gold_newkeys_v1.jsonl \
      --group-gold broad=eval/gold_newkeys_v1.jsonl --terminology off
  ```

  **This check exists because the first version of this file failed it silently.** `facts` was written as a
  `{key: value}` object instead of the list of `[key, value, role]` the scorer reads, so iterating a gold row yielded
  key *strings*: a perfect prediction scored tp=0, fp=1, fn=1 on every item, and the set would have reported ≈0 at
  the gates with nothing obviously wrong in the file. `tests/test_gold_selfscore.py` now runs this against **every**
  `eval/gold_*.jsonl` (format, self-score, role accuracy, and that each key used is reachable by some scorer).

## Scoring a served model

Headline F1 covers the main structured keys; the every-call keys are read from the same file with `--group-gold`, as
for `gold_v3.jsonl`. Run it 3 times and report the spread (AGENTS.md hard rule 3).

```bash
PY=~/miniforge3/envs/zgx/bin/python
$PY eval/bench_extract.py --extractor llm --model herald-f --gold eval/gold_newkeys_v1.jsonl \
    --group-gold broad=eval/gold_newkeys_v1.jsonl \
    --dump eval/dumps/newkeys_herald-f_run1.jsonl --verbose
```

Read the per-key numbers, not only the headline: this set is deliberately dense in six keys and 20% of it is
no-fact lines, so its overall F1 is not comparable with gold v2's.
