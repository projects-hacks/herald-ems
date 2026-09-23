# Labeling guide: paramedic speech → Herald facts

This guide defines the correct answer for extraction. It's used for the gold evaluation sets (`eval/gold_*.jsonl`), for the synthetic training data of the fine-tune (P10), and by anyone checking extractor output. When the extractor and this guide disagree, the guide wins. If a case isn't covered, add it here in the same PR as the label.

## 1. What a label is

One utterance (what the paramedic, or someone else, said into the push-to-talk mic) gets a list of **facts**. Each fact is a triple:

```json
[key, value, role]
```

- `key`: one of the canonical keys in §4. Never invent a key.
- `value`: normalized as described for that key.
- `role`: who the information came from. One of `medic`, `patient`, `family`, `bystander` (§3).

A gold file is JSON Lines, one utterance per line:

```json
{"id": "v1_001", "text": "…utterance…", "by": "medic", "speaker": null, "facts": [["vitals.hr", 98, "medic"], …], "phenomena": ["correction"], "notes": "optional"}
```

- `by`: `"medic"` if the paramedic spoke into the mic (default), or `"other"` if someone else did (a family member handed the mic, as in the demo's judge beat). With `"other"`, also set `speaker` (e.g., `"daughter"`).
- `phenomena`: tags from §6 describing what makes this utterance hard. Used to report accuracy per phenomenon.

## 2. The golden rule: only what was said

Label a fact **only if the words in the utterance state it**. Do not infer, diagnose, or complete.

- "Sudden left-sided weakness" → `stroke.deficits` = `["left-sided weakness"]`. It does **not** give `complaint.chief` = "suspected stroke" (inference), and it does **not** give any RACE exam item (no exam was described).
- "She's on Coumadin" → `meds.anticoagulant` = `"warfarin"` (Coumadin is a brand name of warfarin; mapping a brand to its generic is normalization, not inference) and `meds.list` = `["warfarin"]`.
- "Son thinks she's on a blood thinner but isn't sure which one" → **no facts**. Uncertain statements are not facts.
- An utterance with no extractable facts has `"facts": []`. Such utterances are important; include them.

## 3. Role: who the information came from

- `medic`: the paramedic observed, measured, or said it without attributing it to anyone. Vitals read off a monitor are `medic`.
- `patient`: "patient says/states/denies…", "she tells me…", or the patient speaking into the mic.
- `family`: "husband/wife/daughter/son/mom/dad/brother/sister/caregiver says…", or a family member speaking into the mic (`by: "other"`).
- `bystander`: "neighbor/witness/bystander/passer-by says…".
- **Facility staff** (nursing-home nurse or aide, home-health aide, group-home staff) are caregivers → `family`. They know the patient's baseline, like family does. (Adjudicated on gold v1, item v1_039.)

Attribution applies only to the clause it governs. In "68-year-old female, sudden left-sided weakness, husband says she was fine at 1:40", only the last-known-well time is `family`; age, sex, and deficits are `medic`.

When `by` is `"other"` and nothing else is said about the source, the role is the speaker's (e.g., `family` for a daughter).

## 4. Keys and value rules

| Key | Meaning | Type |
|---|---|---|
| `patient.age` | Age | int |
| `patient.sex` | Sex | str |
| `complaint.chief` | Chief complaint | str |
| `symptom.onset` | Symptom onset | time |
| `stroke.lkw` | Last known well | time |
| `stroke.onset_witnessed` | Onset witnessed | bool |
| `stroke.deficits` | Deficits | list |
| `exam.race.facial` | RACE facial palsy (0-2) | int |
| `exam.race.arm` | RACE arm motor (0-2) | int |
| `exam.race.leg` | RACE leg motor (0-2) | int |
| `exam.race.gaze` | RACE head/gaze deviation (0-1) | int |
| `exam.race.aphasia_agnosia` | RACE aphasia/agnosia (0-2) | int |
| `vitals.sbp` | Systolic BP | int |
| `vitals.dbp` | Diastolic BP | int |
| `vitals.hr` | Heart rate | int |
| `vitals.rr` | Respiratory rate | int |
| `vitals.spo2` | SpO2 | int |
| `vitals.temp` | Temperature | float |
| `vitals.glucose` | Glucose | int |
| `vitals.on_oxygen` | Supplemental oxygen | bool |
| `vitals.consciousness` | Consciousness (ACVPU) | str |
| `vitals.gcs_motor` | GCS motor | int |
| `meds.list` | Medications | list |
| `meds.anticoagulant` | Anticoagulant | str |
| `allergies` | Allergies | list |
| `code_status` | Code status (POLST/DNR) | str |
| `ecg.twelve_lead_time` | 12-lead time | time |
| `ecg.attached` | 12-lead attached | bool |
| `transport.destination` | Destination | str |
| `transport.eta_min` | ETA (min) | int |
| `scene.notes` | Scene notes | list |

### Per-key normalization
- **`patient.age`**: integer years. "Seventy-two" → 72. "72-year-old", "72 yo", "72 yom" → 72.
- **`patient.sex`**: `"F"` or `"M"`. Female, woman, lady, "yof", "she" *alone does not count* (pronouns are not a statement of sex; only label sex when stated as a descriptor, e.g., "68-year-old female").
- **`complaint.chief`**: short free text, only when a complaint is stated ("chest pain", "shortness of breath", "fall"). **Mechanisms of injury count** ("fall", "MVC", "assault"; adjudicated on v1_065). **Don't repeat a finding already captured by a structured key** (e.g., "more confused than baseline" is `vitals.consciousness` = C, not also a complaint; v1_039). Not for "stroke alert", exam signs, or deficits. Scored by presence only.
- **`symptom.onset`**: time or duration as spoken ("20 minutes ago", "since 3").
- **`stroke.lkw`**: last-known-well time **as spoken**, lowercase: "1:40", "10 pm", "9 am", "0630". "Fine at", "normal at", "last seen normal", "LKW" all count. The scorer treats "0630", "06:30" and "6:30" as equal. A clock time of a witnessed onset ("dropped his cup at 7:15") is `symptom.onset`, not `stroke.lkw`.
- **`stroke.onset_witnessed`**: `true` if the onset was seen happening ("collapsed in front of him", "witnessed"); `false` if the patient was found or woke up with symptoms ("found on the floor", "unwitnessed", "woke up like this").
- **`stroke.deficits`**: list of short phrases as said ("left-sided weakness", "facial droop", "slurred speech"). Scored by presence only.
- **RACE exam items** (label only when the exam finding is explicitly described):
  - `exam.race.facial`: 0 none / symmetric; 1 mild ("mild/slight droop"); 2 moderate–severe ("severe/complete droop"). Unqualified "facial droop" → 2.
  - `exam.race.arm` and `exam.race.leg`: 0 normal/strong/no drift; 1 drift or holds < 10 s ("drifts", "drift"); 2 cannot lift against gravity ("can't lift", "no movement", "flaccid").
  - `exam.race.gaze`: 0 no deviation; 1 deviation ("eyes deviated to the right", "looking to the right").
  - `exam.race.aphasia_agnosia`: 0 normal speech / recognizes arm and deficit / "no agnosia"; 1 doesn't recognize either the arm or the deficit; 2 recognizes neither, or severe aphasia ("can't speak", "aphasic").
- **Vitals** (all numbers as integers except temperature):
  - `vitals.sbp`, `vitals.dbp`: from "BP/pressure X over Y" or "X/Y".
  - `vitals.hr`: "pulse/heart rate/HR".
  - `vitals.rr`: "resps/respirations/breathing/RR".
  - `vitals.spo2`: "sat/sats/satting/SpO2/O2 sat/pulse ox". Always 0–100.
  - `vitals.temp`: degrees **Celsius**, one decimal. Convert Fahrenheit: 101.8 °F → 38.8.
  - `vitals.glucose`: mg/dL integer ("sugar", "BGL", "glucose", "D-stick").
  - `vitals.on_oxygen`: `false` for "room air"; `true` for "on oxygen / nasal cannula / non-rebreather / N liters".
  - `vitals.consciousness`: one letter: `A` alert (incl. "alert and oriented", "A&O"); `C` new confusion ("confused", "disoriented"); `V` responds to voice; `P` responds to pain; `U` unresponsive.
  - `vitals.gcs_motor`: 1–6, only when the motor score is stated.
- **`meds.list`**: list of lowercase **generic** names mentioned as taken ("Eliquis" → "apixaban"). Include non-anticoagulants ("metformin").
- **`meds.anticoagulant`**: the generic name (warfarin, apixaban, rivaroxaban, dabigatran, edoxaban, enoxaparin, heparin), or `"none"` **only when explicitly denied** ("no blood thinners", "denies anticoagulants").
- **`allergies`**: list of lowercase allergens; `[]` for "no known allergies / NKDA / no allergies / denies allergies".
- **`code_status`**: `"DNR"` for do-not-resuscitate / POLST DNR statements, `"full code"` when stated.
- **`ecg.twelve_lead_time`**, **`ecg.attached`**: only when a 12-lead is mentioned as done or attached.
- **`transport.destination`**: hospital name as said, title case ("Valley Medical"). Scored by presence only.
- **`transport.eta_min`**: integer minutes ("ETA 12", "12 minutes out", "8 minutes").
- **`scene.notes`**: only for explicit scene observations ("walker by the bed", "pill organizer still full"). Scored by presence only.

## 4b. Rules settled while building gold v1 (from both labelers' notes)
- **RACE without a formal exam:** stroke findings stated in words ("left facial droop, left arm drift, eyes deviated") get RACE items per §4, whether or not the word "exam" is used. Vague wording ("weakness", "slurred", "garbled") gets deficits only. A RACE **total** ("RACE of 7") gets no item scores.
- **A positive RACE finding is also a deficit:** "facial droop" → `exam.race.facial` and `stroke.deficits` ["facial droop"]. Negative findings get only the RACE 0.
- **Rechecked vitals are two facts, not a correction:** "BGL 42 … recheck 156" labels both values.
- **Drugs given by EMS are interventions, not home meds:** no `meds.list`. Home medications taken before EMS arrived ("took a nitro before we got here") are labeled.
- **Future actions are not facts:** "I'll attach the 12-lead" → no `ecg.attached`.
- **CPAP counts as oxygen delivery:** `vitals.on_oxygen` = true; a CPAP number is pressure, not litres.
- **"c/o" (complains of) is the medic's report shorthand:** role `medic`, not `patient`.
- **Nested attribution:** the daughter on the mic relaying the neighbor → the neighbor's statement is `bystander` (clause-level attribution wins over the speaker's default role).

## 4c. Rules settled while building gold v2 (adjudication of 15 disagreements, 2026-09-23)
- **`stroke.*` keys only for stroke-like presentations.** `stroke.onset_witnessed`, `stroke.lkw` and `stroke.deficits` are labeled when the words describe stroke-like symptoms: focal weakness, facial droop, speech or language trouble, gaze deviation, sudden collapse with neuro signs, vertigo with ataxia. They are **not** labeled for a trauma mechanism (a witnessed bike crash), a found-down fall, hypoglycemia, hypothermia, or numbness from a suspected spinal injury (v2_013, 019, 034, 048, 072, 078, 079).
- **Attribution is clause-scoped, also in run-ons.** "per mom she's been vomiting since yesterday she's fourteen and on an insulin pump": only the vomiting clause is the mother's. A new clause (a new subject, or a subjectless shorthand clause like "takes lipiter and metoprolol") is the medic's (v2_022, v2_057).
- **A stated presenting problem that no structured key captures is `complaint.chief`:** "lethargic", "collapsed", "vomiting", "room spinning". This joins the rules for "fall" and "MVC". Still, don't repeat what a structured key holds: fever goes in `vitals.temp`, and new confusion in `vitals.consciousness` (v2_016, v2_068).
- **Response words give an ACVPU letter; a GCS number doesn't.** "Eyes open to pain" or "only responds to pain" → P. "GCS nine" alone gives no letter (v2_062).
- **A drug class without a drug name is not `meds.list`:** "birth control", "something for her thyroid", "a water pill". A named drug is, including an ingredient named by its device ("insulin pump" → insulin) (v2_084, v1_050).
- **Time values:** kept as spoken, lowercase, with number words as digits. "Last night" adds pm ("went to bed at ten thirty last night" → "10:30 pm"). A discovery time ("found at 0400", "woke up at 6") is neither LKW nor onset. Approximators ("about", "around", "like") are dropped; hedges ("maybe", "I think", "not sure") mean no fact (v2_074, v2_064).
- **Two readings in one breath are two facts:** lying and standing, room air then on oxygen (with both `vitals.on_oxygen` false and true), or before and after a drug. "The cuff slipped, it's 140 over 86" is a correction: one fact.
- **`stroke.onset_witnessed` needs someone who saw it.** A wife who "heard a thump" didn't see it. A security guard or store manager is a `bystander`, not facility staff.

## 5. Corrections, negations, numbers
- **Corrections:** "pulse 88, correction, 98" → only `vitals.hr` = 98. "BP 120 over 80, I mean 130 over 80" → SBP 130, DBP 80. The corrected value replaces the first; never label both.
- **Negations:** "denies chest pain" gives no complaint fact (a symptom denial isn't a chief complaint in our schema). "Denies blood thinners" → `meds.anticoagulant` = "none". "No facial droop" → `exam.race.facial` = 0.
- **Spoken numbers:** convert to digits: "one forty over eighty" → 140/80; "ninety one" → 91; "one twenty six" → 126.
- **Units:** labels carry no units; units are implied by the key.

## 6. Phenomena tags (use all that apply)
`clean`, `shorthand` (yom, sats, A&O, D-stick…), `spoken_numbers`, `correction`, `negation`, `attribution` (someone else's statement), `other_speaker` (`by: "other"`), `multi_event` (many facts in one utterance), `no_facts`, `uncertain` (hedged statements that must yield no fact), `brand_names`, `fahrenheit`, `disfluency` (uh, um, restarts), `asr_noise` (the kind of errors speech-to-text makes: missing punctuation, homophones, lowercase).

## 7. Scoring (how `eval/bench_extract.py` uses labels)
- Headline F1 is over **structured keys** as exact `(key, normalized value)` pairs.
- **Free-text keys** (`complaint.chief`, `stroke.deficits`, `transport.destination`, `scene.notes`) are scored by **key presence** only, because paraphrases are not errors.
- Role accuracy is measured on matched facts.
- Report precision and recall, not only F1. Run model extractors 3 times and report the spread (AGENTS.md hard rule 3).
