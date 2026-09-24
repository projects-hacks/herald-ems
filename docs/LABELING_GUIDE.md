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
- **`stroke.*` keys only for stroke-like presentations.** From run E on, an utterance may carry the call's dispatch (`"dispatch"`, e.g. "possible stroke"; the model sees it as the first line). **When the dispatch is a possible stroke, `stroke.lkw` and `stroke.onset_witnessed` are labeled whenever they are stated, even in a sentence with no symptoms** ("Onset was witnessed.", "husband says she was fine at 2:28"): the paramedic already knows it's a stroke call. Otherwise (no dispatch, or another dispatch), `stroke.onset_witnessed`, `stroke.lkw` and `stroke.deficits` are labeled when the words describe stroke-like symptoms: focal weakness, facial droop, speech or language trouble, gaze deviation, sudden collapse with neuro signs, vertigo with ataxia. They are **not** labeled for a trauma mechanism (a witnessed bike crash), a found-down fall, hypoglycemia, hypothermia, or numbness from a suspected spinal injury (v2_013, 019, 034, 048, 072, 078, 079).
- **Attribution is clause-scoped, also in run-ons.** "per mom she's been vomiting since yesterday she's fourteen and on an insulin pump": only the vomiting clause is the mother's. A new clause (a new subject, or a subjectless shorthand clause like "takes lipiter and metoprolol") is the medic's (v2_022, v2_057).
- **A stated presenting problem that no structured key captures is `complaint.chief`:** "lethargic", "collapsed", "vomiting", "room spinning". This joins the rules for "fall" and "MVC". Still, don't repeat what a structured key holds: fever goes in `vitals.temp`, and new confusion in `vitals.consciousness` (v2_016, v2_068).
- **Response words give an ACVPU letter; a GCS number doesn't.** "Eyes open to pain" or "only responds to pain" → P. "GCS nine" alone gives no letter (v2_062).
- **A drug class without a drug name is not `meds.list`:** "birth control", "something for her thyroid", "a water pill". A named drug is, including an ingredient named by its device ("insulin pump" → insulin) (v2_084, v1_050).
- **Time values:** kept as spoken, lowercase, with number words as digits. "Last night" adds pm ("went to bed at ten thirty last night" → "10:30 pm"). A discovery time ("found at 0400", "woke up at 6") is neither LKW nor onset. Approximators ("about", "around", "like") are dropped; hedges ("maybe", "I think", "not sure") mean no fact (v2_074, v2_064).
- **Two readings in one breath are two facts:** lying and standing, room air then on oxygen (with both `vitals.on_oxygen` false and true), or before and after a drug. "The cuff slipped, it's 140 over 86" is a correction: one fact.
- **`stroke.onset_witnessed` needs someone who saw it.** A wife who "heard a thump" didn't see it. A security guard or store manager is a `bystander`, not facility staff.

## 4d. G.F.A.S.T. items (Santa Clara County stroke screen; rules set 2026-09-23)
Four keys, each 0 or 1: `exam.gfast.gaze`, `exam.gfast.facial`, `exam.gfast.arm_leg`, `exam.gfast.speech`
(Protocol 700-A13 §2.3: G gaze abnormalities, F facial asymmetry, A arm or leg weakness/drift, S speech
difficulties; T is the last-known-well time and is labeled as `stroke.lkw`, not here).

- **G.F.A.S.T. is the EMS provider's own screen: label its items only from the medic's words about what the medic observes now** (role `medic`). A family member's or bystander's report ("his face drooped at dinner") is a deficit (`stroke.deficits`), not a G.F.A.S.T. item.
- **Unlike RACE, the items are presence or absence, so plain descriptions count.** "Right-sided weakness", "slurred speech", "left face droop", "eyes deviated left" each give a 1. This differs from the RACE rule in §4b ("weakness on the right" gives RACE nothing, because RACE needs a severity).
- **1 when the finding is present now:**
  - gaze: deviation, gaze preference, forced gaze, can't look to one side;
  - facial: droop, asymmetry, facial palsy, uneven smile;
  - arm_leg: weakness or drift in **any** arm or leg, or can't lift one;
  - speech: slurred or dysarthric speech, aphasia, word-finding trouble, garbled or nonsensical speech, can't speak.
- **0 only when stated normal:**
  - gaze: "eyes midline", "no gaze deviation", "tracks normally";
  - facial: "face symmetric", "no droop";
  - arm_leg: normal strength in **all** limbs, e.g. "no weakness", "no drift", "moves all extremities equally", "arms and legs strong". "Arms fine" alone says nothing about the legs, so no label;
  - speech: "speech clear", "speaking normally".
- **Not mentioned means no label,** never a guess.
- **A stated screen result:**
  - item by item ("GFAST: gaze positive, face positive, arm negative, speech positive"): label each;
  - "GFAST 4 of 4" / "GFAST positive, all four": all four items 1;
  - "GFAST 0" / "GFAST negative": all four items 0 (a zero total does say which);
  - any other total ("GFAST of 2"): no item labels, because the total doesn't say which. If the medic names the positive items ("two of four, face and speech"), those are 1 and the unnamed ones get no label unless stated negative.
- **RACE item scores spoken by the medic are the medic's findings.** All three G.F.A.S.T. annotators independently used this convention, and it is now the rule:
  - facial/gaze score > 0 gives 1 for that item; a score of 0 gives 0;
  - arm or leg score > 0 gives arm_leg 1; arm_leg 0 only when both the arm and the leg are scored 0;
  - an aphasia score > 0 gives speech 1;
  - an agnosia score, or aphasia 0, gives no speech label (no aphasia doesn't rule out slurred speech).
  A RACE **total** gives nothing.
- **Findings that resolved:** the current state wins. "Slurred earlier, speech clear now" gives speech 0.
- **Only for stroke-like presentations** (§4c). A trauma patient's "can't move his legs" is not a G.F.A.S.T. item.
- **The same words can also give RACE items and deficits:** "left arm drift" → `exam.gfast.arm_leg` 1, `exam.race.arm` 1, and `stroke.deficits` ["left arm drift"]. Label each key by its own rule.

G.F.A.S.T. labels for the gold sets live in separate files (`eval/gold_v1_gfast.jsonl`, `eval/gold_v2_gfast.jsonl`), scored separately, so extraction F1 stays comparable with every number already published.

## 4e. Every call type: keys added for run E (2026-09-23)
Herald is a copilot for every EMS call, not only strokes. These keys cover what the crew does and what trauma and sepsis calls need. Values follow NEMSIS where it has an element.

**Records (one fact per event).** A record value is a JSON object; only the fields said are filled.
- **`meds.given`** `{"drug", "dose", "unit", "route", "time", "by"}`: a drug given by the crew or, before arrival, by someone else (fire, first responder, bystander, police). NEMSIS eMedications.03–.06.
  - `drug`: generic, lowercase ("naloxone" for Narcan, "ondansetron" for Zofran, "dextrose" for D10/D50, "nitroglycerin", "aspirin", "epinephrine", "albuterol", "fentanyl"). `dose`: the number as said (324, 0.4, 2). `unit`: mg, mcg, g, mL, units. `route`: IV, IO, IM, IN, PO, SL, SQ, neb, PR. `time`: as said. `by`: "crew" when our crew gave it ("gave", "we gave", "pushed"), otherwise who ("fire", "bystander", "police", "first responder").
  - **Not** `meds.given`: the patient's own doses before the call ("took two nitro at home" → `meds.list`); plans ("going to give zofran"); denials ("no aspirin given yet"); oxygen (`vitals.on_oxygen`).
  - A repeat dose is a second fact ("second round of narcan at 14:12"). Doses said as a count with no separate times ("nitro 0.4 SL times three") are **one** fact with `"count": 3`; identical facts would be read as the same dose said twice.
  - `by` is a category: crew, fire, police, first responder, family, facility (nursing-home or school staff) or bystander (friend, coworker, coach, security). The relation itself ("husband") goes in the fact's source. The vocabulary normalizes synonyms (`field_synonyms` in `config/vocabulary.yaml`), so "husband" and "family" are the same label. The patient's own dose before the call stays `meds.list`, even when a family member reports it; a dose a family member **gave** the patient is `meds.given` with `by` the relation.
  - Before arrival, a dose **given to** the patient by someone else (a parent's EpiPen, nursing-home nitro paste) is `meds.given` with `by` as said, not `meds.list`; a caregiver handing over the usual daily pills is neither. Unnamed fluids ("a liter wide open") give `{"drug": "iv fluids"}`. A drug being given right now ("pushing the D50 now") counts; a plan ("gonna push D10") doesn't. When a time or route could belong to two drugs, it goes on the nearest one only.
  - Names: IV fluid → "normal saline"; oral glucose gel → "glucose"; IV dextrose (D10/D50) → "dextrose"; DuoNeb → "ipratropium-albuterol"; Keflex → "cephalexin".
- **`procedures.done`** `{"procedure", "time", "detail", "by"}`: something done to the patient. NEMSIS eProcedures. `procedure`, short and lowercase: "iv access", "io access", "bvm ventilation", "supraglottic airway", "intubation", "cpr", "defibrillation", "cardioversion", "pacing", "cpap", "splint", "spinal motion restriction", "tourniquet", "wound packing", "needle decompression". `detail`: size, site, count or result as said ("18 gauge left AC", "2 shocks", "200 joules"). Not procedures: a 12-lead (`ecg.*`) or a glucose check (`vitals.glucose`); plans; attempts said to have failed go in `detail` ("iv access", detail "missed x2").

**Numbers.**
- **`vitals.pain`** 0–10, only when a number is said ("eight out of ten", "pain 3/10"); "a lot of pain" gives none.
- **`vitals.gcs_eye`** (1–4), **`vitals.gcs_verbal`** (1–5), **`vitals.gcs_total`** (3–15): each only when its number is said. (`vitals.gcs_motor` keeps its older rule: a stated response such as "withdraws to pain" gives the motor number.) Examples: "GCS 14" → total 14; "E4 V4 M6" → eye 4, verbal 4, motor 6. Never compute a total from components, or components from a total.
- **`vitals.etco2`** in mmHg as said ("end tidal 32", "capno reading 18").
- **`patient.pregnancy_weeks`**: "she's 30 weeks" → 30; "pregnant" with no weeks gives none.

**Trauma and sepsis.**
- **`trauma.mechanism`**: how the injury happened, short, as said, on any call where it's stated (a fall on a stroke call too; "found down" is not a mechanism) ("rollover mvc, ejected", "fall from 12 feet", "gsw to the abdomen", "pedestrian struck at 35 mph"). `complaint.chief` keeps its own rule; the same words may give both.
- **`trauma.injuries`**: a list of injuries found, as said ("open deformity right femur", "penetrating wound left chest", "unstable pelvis", "flail segment"). Complaints without a finding ("my leg hurts") are not injuries.
- **`trauma.criteria`**: a list from the fixed values in `config/vocabulary.yaml` (the national field-triage injury patterns and mechanisms, in Policy 605's words), labeled when the words describe one: "ejected from the vehicle" → "ejection"; "fell from the second floor balcony, about 15 feet" → "fall over 10 feet"; "GSW to the chest" → "penetrating injury head neck torso or proximal extremity"; "tourniquet on the left thigh, still oozing" → "bleeding requiring tourniquet or wound packing"; "unstable pelvis" → "pelvic fracture"; "rolled the car, no seatbelt" → "rollover unrestrained". Label only what the words support (a fall "from a ladder" with no height gives none); hedged heights ("maybe 8, maybe 12 feet") give none. **Never** label the vital-sign criteria (GCS motor, RR, SpO2, blood pressure by age), anticoagulants or pregnancy here: those are computed from their own facts.
- **`ecg.stemi_reading`**: true when the 12-lead's interpretation reads STEMI or "acute MI suspected" ("monitor's reading STEMI", "tombstones in 2, 3, aVF, it's calling a STEMI"); false when stated otherwise ("no STEMI on the 12-lead"). ST changes described without the reading give none.
- **`ecg.transmitted`**: true when the 12-lead was sent to the hospital ("transmitted to Regional", "12-lead is sent"); a plan ("I'll send it") gives none.
- **What counts as an injury found:** wounds, deformity, swelling, bruising, crepitus, instability, tenderness on palpation, and new motor or sensory loss after trauma. Pupils, breath sounds and distal pulses are signs, not injuries. A penetrating wound can give the mechanism, the complaint and the injury from the same words.
- **A negative stroke screen said on a trauma call** ("no facial droop, speech clear" after a fall) gives no G.F.A.S.T. or RACE values (§4d: stroke-like presentations only).
- **Approximators** ("about", "like") are dropped from pain, pregnancy weeks and speeds as from times; hedges ("maybe") and ranges ("six to eight") give no fact.
- **`infection.suspected`**: the suspected source when the crew or a caregiver states one ("probably urosepsis" → "urinary"; "looks like pneumonia" → "respiratory"; "that wound looks infected" → "skin"; "septic, no clear source" → "unknown"). A fever alone gives none.

## 5. Corrections, negations, numbers
- **Corrections:** "pulse 88, correction, 98" → only `vitals.hr` = 98. "BP 120 over 80, I mean 130 over 80" → SBP 130, DBP 80. The corrected value replaces the first; never label both.
- **Negations:** "denies chest pain" gives no complaint fact (a symptom denial isn't a chief complaint in our schema). "Denies blood thinners" → `meds.anticoagulant` = "none". "No facial droop" → `exam.race.facial` = 0.
- **Spoken numbers:** convert to digits: "one forty over eighty" → 140/80; "ninety one" → 91; "one twenty six" → 126.
- **Units:** labels carry no units; units are implied by the key.

- **Times said as numbers:** "normal at one forty" → `stroke.lkw` "1:40" (never "1:14"); "fourteen thirty" → "14:30".
- **Hyphenated and run-together numbers:** "one-eighteen" → 118; "one-oh-two" → 102; "a hundred and ten" → 110.

## 5a. Additions for run D (2026-09-23; from the dev-set error analysis, MODEL_PLAN §0g)
- **Order of facts:** list the facts **in the order they were said** (by the first word that supports each fact). When one phrase gives several facts ("left facial droop" → a G.F.A.S.T. item and a RACE item), the G.F.A.S.T. item comes before the RACE item. `scripts/build_train_set.py --order spoken` re-sorts every training target by the same rule (`config/training.yaml`), so the builder's order is the one the model learns.
- **Antiplatelets are not anticoagulants:** clopidogrel (Plavix), aspirin, ticagrelor (Brilinta), prasugrel (Effient) go in `meds.list` only, never `meds.anticoagulant`. Other drug classes (SGLT2 inhibitors, statins, beta blockers) likewise.
- **Slurred speech is dysarthria, not aphasia:** it gives G.F.A.S.T. speech 1 but **no** RACE `aphasia_agnosia` value on its own. RACE aphasia needs language trouble (can't find words, doesn't follow commands, nonsense speech); agnosia needs not recognizing the arm or the deficit.
- **Someone else's mic (`by: "other"`):** the model input will start with a speaker line (see `config/prompts/extract_finetuned.md`), e.g. `[speaker: daughter]`. The speaker is the source of what they say about themselves or what they saw; "Mom is allergic to aspirin" said by the daughter → role `family`, not the patient.

## 5b. Conventions settled while writing the run D batches (2026-09-23)
Annotators flagged these as unclear; these are the labels used from batch 10 on.
- **Facility staff** (nurse, aide, group-home staff, caregiver) are `family` with their job word as the source ("aide").
- **Subjectless shorthand** ("NKDA", "denies allergies", "takes eliquis and metformin") is the medic's; "Pt denies…" is the patient's.
- **Family or bystander descriptions of stroke findings** ("her face drooped at dinner") give `stroke.deficits` only, never RACE or G.F.A.S.T. items (those are the medic's own exam, §4d).
- **A POLST marked "attempt resuscitation"** → `code_status` "full code".
- **A drug the patient has stopped** gets no `meds.list`; `meds.anticoagulant` "none" still needs an explicit denial.
- **Clock-time arrivals and ranges** ("around fourteen fifteen", "in the one-forties", "HI, north of six hundred") give no numeric fact.
- **Nested relays** ("my brother says…" said by the daughter): the source is the relation to the patient ("son").
- **One drug word, two facts** ("she takes eloquis"): `meds.anticoagulant` before `meds.list`.
- **A 12-lead "done at T"** gives `ecg.twelve_lead_time`; "attached" gives `ecg.attached` true; "I'll attach it" gives nothing.
- **Unqualified "no drift"** → `exam.gfast.arm_leg` 0 and `exam.race.arm` 0; arm-only wording ("arms fine") → `exam.race.arm` 0 only.
- **"Speech clear"** is articulation: G.F.A.S.T. speech 0, no RACE value. "Talking normally" gives both 0s. Word-finding trouble with no severity: G.F.A.S.T. speech 1 and a deficit, no RACE value.
- **Resolved findings** (RACE as well as G.F.A.S.T.): the current state wins, and a resolved finding is not a deficit.
- **"Can't look to the left"** → G.F.A.S.T. gaze 1 and a deficit; RACE gaze only when a deviation is stated.
- **Times of day:** "this morning" adds am, "this afternoon/last night" adds pm; 24-hour times stay as said ("2200"); "quarter past eight" → "8:15". `symptom.onset` keeps "since" ("since 2 pm"); `stroke.lkw` drops "at".
- **Discovery times** ("found at 0400", "noticed at 1045") are not last known well and not onset: no time fact.
- **"Unknown down time" / "LKW unknown"** give no fact; `onset_witnessed` false needs "found", "woke up with it", "unwitnessed", or "nobody saw it". Seeing it happen on a video call counts as witnessed.
- **"Found by her landlord" / "last seen normal by her daughter":** the source is the person named; a bare "found down" is the medic's.
- **Bare RACE scores** ("face two, arm one") give no `stroke.deficits` (no phrase was said). "GFAST positive" without the count gives no item labels.

## 6. Phenomena tags (use all that apply)
`clean`, `shorthand` (yom, sats, A&O, D-stick…), `spoken_numbers`, `correction`, `negation`, `attribution` (someone else's statement), `other_speaker` (`by: "other"`), `multi_event` (many facts in one utterance), `no_facts`, `uncertain` (hedged statements that must yield no fact), `brand_names`, `fahrenheit`, `disfluency` (uh, um, restarts), `asr_noise` (the kind of errors speech-to-text makes: missing punctuation, homophones, lowercase).

## 7. Scoring (how `eval/bench_extract.py` uses labels)
- Headline F1 is over **structured keys** as exact `(key, normalized value)` pairs.
- **Free-text keys** (`complaint.chief`, `stroke.deficits`, `transport.destination`, `scene.notes`) are scored by **key presence** only, because paraphrases are not errors.
- Role accuracy is measured on matched facts.
- Report precision and recall, not only F1. Run model extractors 3 times and report the spread (AGENTS.md hard rule 3).
