# gold_es_v1: Mexican Spanish scene speech (60 utterances, held out)

Measures whether the speech extractor produces the same canonical facts (English values, RxNorm ingredient names,
the same keys, roles and sources) from Spanish speech as from English: patients, family and bystanders at EMS
scenes in Santa Clara County, mostly Mexican Spanish, and medics who code-switch. Labeled under LABELING_GUIDE §2–§5e
and §5f (Spanish speech).

| File | What it is |
|---|---|
| `gold_es_v1_texts.jsonl` | The 60 inputs: `id`, `dispatch`, `text`, `by`, `speaker` (the same shape as `gold_v3_texts.jsonl`) |
| `gold_es_v1.jsonl` | Adjudicated gold: the inputs plus `facts`, `phenomena`, `notes` (G.F.A.S.T. and every-call keys inline, as in `gold_v3.jsonl`) |
| `gold_es_v1_labeler_b.jsonl` | The blind second labeling, kept as it was labeled (for agreement) |

## How it was made

- **Independent of the training data.** The texts were written from the labeling guide, the vocabulary and the
  extractor's input format only. Nothing under `data/` (annotated batches, `train_*`) was opened, and no model output
  was seen before labeling. Every text is invented; there is no patient data.
- **Two labeling passes.** Labeler A (the writer) labeled in a separate pass after all 60 texts were written.
  Labeler B labeled blind from the texts, the guide and the vocabulary only; B never saw A's labels, notes, or this
  file. Disagreements were then adjudicated by the guide (below). A caveat: both passes are by annotators working
  from the same written guide, so agreement measures how unambiguous the guide is for these lines, not two
  independent clinical opinions.
- **Speech style.** Whisper-like Spanish transcripts: mostly punctuated with accents, a few lowercase run-ons with no
  punctuation (`asr_noise`). Numbers appear as digits and as Spanish number words ("ciento cuarenta sobre ochenta",
  "setenta y dos", "treinta y ocho semanas").

## Composition

- **Speakers:** 39 on someone else's mic (`by: "other"`): patient 14, family 18 (daughter 6, mother 4, wife 3, son 2,
  husband, grandson, caregiver), bystanders 7 (witness 2, neighbor, roommate, friend, coworker, a bystander); one
  bystander line is code-switched. 21 medic lines: 17 code-switched, 4 in Spanish (addressing the patient or a
  bilingual medic reading vitals).
- **Dispatch:** 52 distinct dispatch lines; 2 lines have no dispatch (the model sees `[dispatch: unknown]`).
- **Calls:** chest pain / STEMI, stroke (4, with G.F.A.S.T. and RACE items), diabetic (low and high sugar), falls and
  head strikes in the elderly, MVC (T-bone with extrication, rollover with ejection, motorcycle, pedestrian), fall
  from height with spinal signs, GSW, assault, seizure (adult, child with fever, workplace), overdose (benzodiazepine,
  opioid with bystander naloxone, acetaminophen), allergic reaction, asthma/COPD/CHF, pregnancy and field delivery,
  urinary symptoms, psychiatric, arrest with ROSC, heat illness, hospice with a POLST.
- **Colloquialisms:** el azúcar (bajó / salió en 45), la presión (se me subió), derrame (hedged), infarto (history),
  se desmayó, le falta el aire, pastillas para la presión / el azúcar / adelgazar la sangre, calentura, la panza,
  se le rompió la fuente, la boca chueca, se puso morado.
- **Drug names as said in Mexico and the US:** Tempra, Rivotril, Epamín, Ventolín, Xarelto, Eliquis, Coumadin,
  Diovan, Januvia, Keppra, Aricept, Risperdal, Plavix, Lipitor, Tylenol, Benadryl, Narcan, EpiPen, and Spanish
  generics (metformina, losartán, insulina, nitroglicerinas, ciprofloxacina, amoxicilina, furosemida, carvedilol,
  morfina, litio). Epamín (phenytoin) is not in the RxNorm index (`unresolved`), so only the model can get it right.
- **Hard cases:** family reporting the patient's own doses before arrival (es_007 inhaler, es_034 two SL nitros with
  their own times), the patient's own aspirin (es_046), a planned vs given dose (es_019: "we're going to give D10" …
  "D10 going in now, 250 mils"), corrections ("a las cinco, no, perdón, a las seis", es_020; "ciento treinta sobre
  ochenta, perdón, ciento cuarenta", es_041), counting to lift the patient that looks like times (es_024), a stopped
  drug (lithium, es_051), a forgotten dose that is not a stopped drug (es_005, es_031), hedges ("creo que le dio un
  derrame", "creo que era fentanilo", "a lo mejor la simvastatina"), a range ("190 y algo"), "yo no vi nada, nomás
  oí el golpe", an overdose that is not a dose given (es_008, es_035).
- **No facts:** 6 of 60 (10%): es_024, es_030, es_033, es_045, es_048, es_059.

COUNTS_PLACEHOLDER

AGREEMENT_PLACEHOLDER

RULINGS_PLACEHOLDER

## Scoring a served model

Headline F1 covers the main structured keys; G.F.A.S.T. and every-call keys (`eval/scoring.yaml` groups) are read
from the same file with `--group-gold`, as for `gold_v3.jsonl`. Live model runs apply RxNorm drug coding by default
(needs `data/terminology/`). Run it 3 times and report the spread (AGENTS.md hard rule 3).

```bash
PY=~/miniforge3/envs/zgx/bin/python
$PY eval/bench_extract.py --extractor llm --model ems-e-v2-fp8 --gold eval/gold_es_v1.jsonl \
    --group-gold gfast=eval/gold_es_v1.jsonl --group-gold broad=eval/gold_es_v1.jsonl \
    --dump eval/dumps/es_v1_ems-e-v2-fp8_run1.jsonl --verbose
# re-score saved predictions without calling the model:
$PY eval/bench_extract.py --rescore eval/dumps/es_v1_ems-e-v2-fp8_run1.jsonl --gold eval/gold_es_v1.jsonl \
    --group-gold gfast=eval/gold_es_v1.jsonl --group-gold broad=eval/gold_es_v1.jsonl --terminology on
```

`bench_extract.py` has no `--limit`; `--ids es_001-es_002` scores a slice. Checks done when the set was built (none
wrote to `eval/results.jsonl`): the gold replayed as its own predictions scores 1.000 on every part (main, free text,
gfast 7/7, broad 121/121); the rules baseline parses all 60 lines; a live 2-line run against `ems-e-v2-fp8`
(`--ids es_001-es_002`) returned valid JSON and scored.
