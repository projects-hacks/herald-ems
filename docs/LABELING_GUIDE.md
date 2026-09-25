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
- **Drug names (all drug keys) are RxNorm ingredient names, lowercase** (team lead, 2026-09-24; the app codes every drug name to RxNorm, `herald/terminology/`, MODEL_PLAN §0j). Brands and misspellings become the ingredient ("Eliquis" → "apixaban"; Depakote → "valproate", RxNorm's ingredient for divalproex). A combination is RxNorm's multi-ingredient name: the ingredients in alphabetical order joined by " / " (DuoNeb or "ipratropium-albuterol" → "albuterol / ipratropium"; Percocet → "acetaminophen / oxycodone"). A name RxNorm doesn't have, or one it can't pin to one ingredient ("insulin", "dextrose"), is labeled as said. A product said with its number keeps every ingredient, never the plain brand's: "Tylenol 3" → "acetaminophen / codeine", Humalog Mix 75/25 → "insulin lispro / insulin lispro protamine, human" (the number is part of the product, not a dose; RxNorm's name carries ", human", §5c.2). To check a name, look it up in RxNav (https://mor.nlm.nih.gov/RxNav/) or ask the index: `RxNormNormalizer.load(...).normalize(key, name)`.
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
  - A medic reporting an intervention without naming anyone else ("TXA one gram IV", "IO in the right humerus") is reporting the crew's: `by` "crew" (settled when adjudicating gold v3).
  - `by` is a category: crew, fire, police, first responder, family, facility (nursing-home or school staff) or bystander (friend, coworker, coach, security). The relation itself ("husband") goes in the fact's source. The vocabulary normalizes synonyms (`field_synonyms` in `config/vocabulary.yaml`), so "husband" and "family" are the same label. The patient's own dose before the call stays `meds.list`, even when a family member reports it; a dose a family member **gave** the patient is `meds.given` with `by` the relation.
  - Before arrival, a dose **given to** the patient by someone else (a parent's EpiPen, nursing-home nitro paste) is `meds.given` with `by` as said, not `meds.list`; a caregiver handing over the usual daily pills is neither. Unnamed fluids ("a liter wide open") give `{"drug": "iv fluids"}`. A drug being given right now ("pushing the D50 now") counts; a plan ("gonna push D10") doesn't. When a time or route could belong to two drugs, it goes on the nearest one only.
  - Names: normal saline → "sodium chloride" (RxNorm's ingredient; no gold item had it before 2026-09-24); oral glucose gel → "glucose"; IV dextrose (D10/D50) → "dextrose" (RxNorm files both under "glucose" but "dextrose" alone is ambiguous there, so it stays as said); DuoNeb → "albuterol / ipratropium" (RxNorm's combination name; was "ipratropium-albuterol" until 2026-09-24, renamed in every gold set); Keflex → "cephalexin".
- **`procedures.done`** `{"procedure", "time", "detail", "by"}`: something done to the patient. NEMSIS eProcedures. `procedure`, short and lowercase: "iv access", "io access", "bvm ventilation", "supraglottic airway", "intubation", "cpr", "defibrillation", "cardioversion", "pacing", "cpap", "splint", "spinal motion restriction", "tourniquet", "wound packing", "needle decompression". `detail`: size, site, count or result as said ("18 gauge left AC", "2 shocks", "200 joules"). Not procedures: a 12-lead (`ecg.*`) or a glucose check (`vitals.glucose`); plans; attempts said to have failed go in `detail` ("iv access", detail "missed x2").

**Numbers.**
- **`vitals.pain`** 0–10, only when a number is said ("eight out of ten", "pain 3/10"); "a lot of pain" gives none.
- **`vitals.gcs_eye`** (1–4), **`vitals.gcs_verbal`** (1–5), **`vitals.gcs_total`** (3–15): each only when its number is said. (`vitals.gcs_motor` keeps its older rule: a stated response such as "withdraws to pain" gives the motor number.) Examples: "GCS 14" → total 14; "E4 V4 M6" → eye 4, verbal 4, motor 6. Never compute a total from components, or components from a total.
- **`vitals.etco2`** in mmHg as said ("end tidal 32", "capno reading 18").
- **`patient.pregnancy_weeks`**: "she's 30 weeks" → 30; "pregnant" with no weeks gives none.

**Trauma and sepsis.**
- **`trauma.mechanism`**: how the injury happened, short, as said, on any call where it's stated (a fall on a stroke call too; "found down" is not a mechanism) ("rollover mvc, ejected", "fall from 12 feet", "gsw to the abdomen", "pedestrian struck at 35 mph"). `complaint.chief` keeps its own rule; the same words may give both.
- **`trauma.injuries`**: a list of injuries found, as said ("open deformity right femur", "penetrating wound left chest", "unstable pelvis", "flail segment"). Complaints without a finding ("my leg hurts") are not injuries.
- **`trauma.criteria`**: a list from the fixed values in `config/vocabulary.yaml` (the national field-triage injury patterns and mechanisms, in Policy 605's words), labeled when the words describe one: "ejected from the vehicle" → "ejection"; "fell from the second floor balcony, about 15 feet" → "fall over 10 feet"; "GSW to the chest" → "penetrating injury head neck torso or proximal extremity"; "tourniquet on the left thigh, still oozing" → "bleeding requiring tourniquet or wound packing"; "unstable pelvis" → "pelvic fracture"; "rolled the car, no seatbelt" → "rollover unrestrained". Label only what the words support (a fall "from a ladder" with no height gives none); hedged heights ("maybe 8, maybe 12 feet") give none. The county words the injury patterns as suspicions ("suspected pelvic fracture", "suspected skull fracture"), so for these values a stated suspicion counts ("possible pelvic fracture" → "pelvic fracture"), unlike the general hedge rule. "Major burn" is a burn-center criterion (Policy 605 §III), not a Trauma Alert criterion. **Never** label the vital-sign criteria (GCS motor, RR, SpO2, blood pressure by age), anticoagulants or pregnancy here: those are computed from their own facts.
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

## 5c. Rules settled for run F (2026-09-24; gaps found while writing batches 21 on, MODEL_PLAN §0k)
Numbered so labelers and adjudicators can cite them ("§5c.3").

1. **Said is not done: orders, requests, plans, advice, offers, refusals and holds give no `meds.given` or
   `procedures.done`.** "Give her 325 aspirin" (anyone saying it, a bystander included), "base says push 4 of Zofran",
   "we'll start fentanyl", "I told him to take his aspirin", "offered her Tylenol", "she refused the aspirin",
   "declined the IV", "held the nitro, pressure's too soft" → no record. The dose is a fact only once someone says it
   was given or is going in now ("aspirin's been chewed", "pushing it now", "fentanyl 50 in"). A refused drug is not a
   home medication either (no `meds.list`). The patient's own doses before the call stay `meds.list` (§4e).
2. **Drug labels are the names the RxNorm coder writes back for an exact match** (§4 drug names; the coder is
   `RxNormNormalizer.normalize(key, name)`): a label must code to itself with method `exact`, or be a name RxNorm
   doesn't have (kept as said, e.g. "insulin", "dextrose", "peanuts"). RxNorm writes some ingredients with a
   qualifier, and the qualifier is part of the name: Humalog Mix 75/25 (and "Humalog 75/25") → "insulin lispro /
   insulin lispro protamine, human" (written without ", human" it codes to one insulin); NovoLog → "insulin aspart,
   human"; NovoLog Mix 70/30 → "insulin aspart protamine, human / insulin aspart, human"; Humulin or Novolin 70/30 →
   "insulin isophane / insulin, regular, human"; isosorbide mononitrate (Imdur) → "isosorbide". Racemic epinephrine
   → "racepinephrine". Numbered products keep every ingredient whatever the number: "Tylenol 3", "Tylenol number 4",
   "Tylenol with codeine" → "acetaminophen / codeine"; "Percocet 5/325" → "acetaminophen / oxycodone"; "Norco 10/325",
   Vicodin, "hydrocodone APAP" → "acetaminophen / hydrocodone". Ingredients go in alphabetical order ("hydrochlorothiazide /
   losartan" for Hyzaar or "losartan HCTZ"). Two separate drugs said together ("Plavix and aspirin") are two items,
   never a combination.
3. **12-lead keys.**
   - `ecg.stemi_reading` true when the 12-lead's reading, or the medic's read of it, says STEMI or acute MI ("monitor's
     calling a STEMI", "it's an inferior STEMI", "meets STEMI criteria", "acute MI suspected"). False for a negative
     read of the whole tracing: "no STEMI", "not a STEMI", "doesn't meet criteria", "no acute changes", "no ST changes",
     "no ST elevation", "unremarkable", "nondiagnostic", "normal 12-lead". None for ST elevation or depression
     described without the reading ("ST elevation in 2, 3 and aVF"), a rhythm alone ("sinus tach", "a-fib"), or
     "STEMI alert" / "cath lab activated" as the call's label without a reading.
   - `ecg.transmitted` true when the 12-lead is said sent ("transmitted to the cath lab", "sent it to Regional", "you
     should have it on your screen"); false when said not sent ("couldn't transmit", "didn't go through"). A plan
     ("I'll send it") gives none.
   - `ecg.attached` true when the 12-lead is said attached, on the chart/ePCR/pre-alert, "on" the patient, done with
     no time given, or sent (a sent 12-lead was acquired and attached). "Done at T", "at T shows…" gives only
     `ecg.twelve_lead_time` (§5b). A rhythm read off the monitor, not the 12-lead, gives no ECG key.
4. **`infection.suspected` values** (the suspected source, lowercase): "urinary" (UTI, urosepsis, cloudy or foul
   catheter urine), "respiratory" (pneumonia, productive cough with fever called a chest infection), "skin" (cellulitis,
   infected wound, abscess, pressure ulcer, infected surgical site), "abdominal" (appendicitis, belly source,
   cholecystitis, peritonitis), "neurologic" (meningitis), "device" (infected port, PICC, dialysis catheter; a urinary
   catheter is "urinary"), "unknown" ("looks septic, no clear source", "sepsis alert, source unknown"). Only when the
   crew or a caregiver states the suspicion (a hedge from the crew such as "probably" or "looks like" is the suspicion
   itself, as in §4e). A fever, a SIRS count, or a dispatch of "possible sepsis" alone gives none. A patient with a
   known diagnosis under treatment ("on antibiotics for pneumonia") → the source ("respiratory").
5. **`trauma.criteria`: which words give which value** (injured patients only: a mechanism or injury is stated in the
   utterance or the dispatch is an injury; "respiratory distress" on an asthma call is not a trauma criterion):
   - "fall over 10 feet": a height over 10 feet, or two or more stories of drop ("third-floor window", "off the roof of a
     two-story house"). Exactly 10 feet, a "second-floor balcony" with no height, "a ladder", or a hedged height give
     none.
   - "low level fall with significant head impact": a fall from standing or a low height with a stated head strike
     ("tripped and hit her head on the counter"). "Denies hitting her head" or a head strike not stated gives none.
   - "pedestrian or cyclist thrown or run over": a pedestrian or bicyclist thrown, run over, dragged, or struck with
     significant impact: said as significant/high speed, or at a stated speed of 20 mph or more (the 2011 national
     guideline's "significant (> 20 mph) impact", which the 2021 wording replaced with "significant impact").
   - "rider separated with significant impact": thrown or separated from a motorcycle, ATV, scooter, dirt bike or horse
     ("thrown over the handlebars", "bucked off"). Laying the bike down and staying with it gives none.
   - "ejection" (partial or complete, from a car); "rollover unrestrained" (rollover and no restraint, both said);
     "child unrestrained" (a child passenger not restrained or in an unsecured car seat); "death in same passenger
     compartment" (someone dead in the same vehicle, not another vehicle).
   - "intrusion or extrication": intrusion said as major/significant, or over 12 inches at the patient's seat (18
     anywhere), or extrication needed ("had to cut her out", "prolonged extrication", "entrapped"). "Minor intrusion"
     gives none.
   - "penetrating injury head neck torso or proximal extremity": a GSW, stab or impalement to the head, neck, chest,
     abdomen, back, pelvis, or an arm or leg above the elbow or knee. A stab to the forearm or a nail through the foot
     gives none.
   - "skull deformity" (deformity, step-off, depressed or suspected skull fracture); "chest wall instability"
     (flail, paradoxical movement, chest wall deformity); "pelvic fracture" (unstable or suspected); "two or more
     proximal long bone fractures" (two or more of femur and humerus, e.g. "bilateral femur deformities");
     "crushed degloved mangled or pulseless extremity"; "amputation proximal to wrist or ankle" (fingers or toes give
     none); "spinal injury with new motor or sensory loss" (a suspected spinal injury and new weakness, numbness or
     tingling); "bleeding requiring tourniquet or wound packing" (a tourniquet or packing applied or needed to stop
     the bleeding).
   - "time sensitive extremity injury": an open fracture, or a fracture or dislocation with lost or weak pulses or
     sensation below it. A pulseless extremity is "crushed degloved mangled or pulseless extremity" instead.
   - "respiratory distress or need for respiratory support": an injured patient in respiratory distress or being
     ventilated (BVM, airway, CPAP).
   - "major burn" (Policy 605 §III.A.1-6): partial-thickness burns over 10% of the body, burns to the face, hands,
     feet, genitalia, perineum or a major joint, any full-thickness burn, an electrical (incl. lightning) or chemical
     burn, or an inhalation injury (singed nasal hair, soot in the airway, hoarse voice after a fire).
   - One description may give several values ("rolled, unbelted, thrown from the car" → "rollover unrestrained" and
     "ejection").

## 5d. Keys and fields added for run F (owner-approved 2026-09-24; `config/vocabulary.yaml`)
Numbered like §5c. Each key follows §2 (only what was said) and §3 (who said it).

1. **`trauma.injury_time`** (time, as `stroke.lkw`): when the injury happened, as spoken ("crashed around 1430" →
   "1430"; "fell about two hours ago" → "2 hours ago"; "went down at eleven last night" → "11 pm"). The same words
   also give `symptom.onset`, as they always have (the complaint began with the injury; older labels do this). A
   discovery time ("found at 0600") is neither; a hedge gives none; a medical onset with no injury gives only
   `symptom.onset`.
2. **`ecg.territory`** (list from the enum): the territory of the injury pattern when a territory word is said by
   the medic or read off the monitor: "inferior STEMI" → ["inferior"] (and `ecg.stemi_reading` true, §5c.3);
   "anteroseptal" → ["anterior", "septal"]; "inferolateral" → ["inferior", "lateral"]; "anterolateral" →
   ["anterior", "lateral"]; "RV infarct", "right-sided elevation in V4R" → ["right ventricular"]; "posterior MI" →
   ["posterior"]. "Inferior ST elevation" with no STEMI reading gives the territory only. Leads alone ("elevation in
   2, 3 and aVF") give no territory (reading leads is interpretation), and reciprocal changes give none ("reciprocal
   depression laterally"). A negative ("no inferior changes") gives none.
3. **`airway.status`** (one enum value; the current status the medic states):
   - "patent": "airway's patent / clear / intact", "maintaining her own airway", "no airway issues";
   - "patent with adjunct": an OPA or NPA in place ("NPA in the right nare, airway's good");
   - "supraglottic airway": i-gel, King, LMA in place; "endotracheal tube": intubated, tubed, "ETT at 23 at the teeth";
   - "bag-valve-mask ventilation": being bagged with a BVM and nothing more advanced in place;
   - "compromised": "airway's compromised", snoring or gurgling respirations, blood or vomit in the airway, "can't
     protect his airway", stridor said as an airway problem.
   A device placed is also a `procedures.done` event (§4e). Words about the airway that state no status give none
   ("check the airway", "airway bag", "grab the airway kit", "we'll put an i-gel in", "airway?" as a question). A
   later status replaces an earlier one only within one utterance ("bagging, now i-gel's in" → "supraglottic
   airway"; §5 corrections: the current state wins).
4. **`impression.primary`** (str, short, lowercase, as said): the crew's working impression, stated as the medic's
   own assessment: "my impression is hypoglycemia" → "hypoglycemia"; "looks like a CVA to me" → "cva"; "treating it as
   anaphylaxis"; "primary impression opioid overdose"; "field impression, sepsis from a UTI" → "sepsis from a uti";
   "I think she's septic" → "sepsis". Role `medic` only: a family member's or bystander's guess ("my wife thinks it's
   a stroke") is not the crew's impression. It does not replace other keys: "probably urosepsis" → impression
   "urosepsis" and `infection.suspected` "urinary"; "looks like a stroke" gives no stroke keys (§4c) and no
   `complaint.chief`. Not an impression: the dispatch, a chief complaint ("c/o chest pain"), "stroke alert" or "STEMI
   alert" as a call label, the other sense of the word ("the seatbelt left an impression"), and hedges ("could be
   anything, maybe a bleed, maybe not").
5. **`triage.category`** (one enum value; SALT, mass-casualty): the category given to the patient being described:
   "immediate" (red), "delayed" (yellow), "minimal" (green, walking wounded), "expectant" (gray/grey), "dead"
   (black, deceased). Colors map to the SALT category ("tagged him red" → "immediate"; "she's a green" → "minimal";
   "black tag" → "dead"). A retag is a correction: the last category said wins. Counts across patients ("two reds and
   five greens on scene") and a category for someone else ("the driver's a black tag" said about another patient
   while describing this one) give none for this patient; a line about one patient gives that patient's category.
   Triage words outside mass-casualty tagging give none ("red and swollen", "green sputum", "yellow skin",
   "immediate relief", "the triage nurse", "code red").
6. **`before_arrival`** (bool field on `meds.given` and `procedures.done`; NEMSIS eMedications.02 "prior to EMS
   care"): true when the words say the dose or procedure happened before this crew arrived ("fire gave 2 of Narcan
   before we got there", "PTA", "prior to our arrival", "bystander CPR in progress on arrival", "I gave him my
   Narcan before you got here", "had already given"). Set only when true; the crew's own interventions leave it out.
   A dose given by fire, police or a bystander with no timing said leaves it out.
   - **A dose the patient took for this problem before the crew arrived is a record given before arrival**, with
     `by` "patient": "took two of his own nitros before we got there" → `meds.given` {"drug": "nitroglycerin",
     "count": 2, "by": "patient", "before_arrival": true}. It is also still a home medication (`meds.list`
     ["nitroglycerin"]), as before (§4b, §4e). Routine daily doses ("took her Eliquis this morning", "had her
     morning pills") are `meds.list` only.
   - Plans, advice and refusals (§5c.1) give no record, so no `before_arrival`.
7. **Units and shared times on dose records** (settled conventions restated; nothing changed):
   - A unit is filled only when said or spoken as a unit word ("mg", "migs", "milligrams" → mg; "mics", "micrograms"
     → mcg; "grams" → g; "units"; "mils", "cc" → mL). "324 of aspirin", "aspirin 324 PO" → dose 324, no unit: a
     standard unit is not filled in when it wasn't said (§4e: only the fields said are filled).
   - A time said once after a list of doses goes on the nearest dose only (§4e): "we gave 324 of aspirin chewed and
     fentanyl 50 mics IV at 1422" → the time on fentanyl only. A time said before the list applies to the first
     only. A time said for each dose ("aspirin at 1410, fentanyl at 1422") goes on each.
8. **Procedure names** (`procedures.done` `procedure`) are always lowercase and use the names in §4e: "iv access",
   "io access", "bvm ventilation", "supraglottic airway", "intubation", "cpr", "defibrillation", "cardioversion",
   "pacing", "cpap", "splint", "spinal motion restriction", "tourniquet", "wound packing", "needle decompression",
   plus "airway adjunct" (OPA/NPA; the device in `detail`), "suction", "pelvic binder", "chest seal", "bleeding
   control" (direct pressure, pressure dressing), "cooling", "childbirth" (field delivery). Synonyms become the name:
   "got a line", "an 18 in the AC" → "iv access"; "i-gel", "King", "LMA" → "supraglottic airway" (device in
   `detail`); "tubed him" → "intubation"; "bagging" → "bvm ventilation"; "shocked" → "defibrillation"; "C-collar",
   "backboard", "SMR" → "spinal motion restriction"; "traction splint" → "splint" (detail "traction").

## 5e. Rulings from the run F adjudication (2026-09-24)
Cases the writers and blind labelers of batches 21–31 flagged as unclear, settled so every batch uses one reading.

1. **Overdoses are not doses given.** Pills the patient took as the overdose ("took thirty of her Percocet") give no
   `meds.given` record: the ingestion is the problem, not a treatment. The drug is `meds.list` only when said to be
   the patient's own ("her own Percocet"); someone else's pills give no `meds.list`. The overdose itself is
   `complaint.chief`. Illicit drugs (heroin, meth, cocaine) are never `meds.list`.
2. **`before_arrival` needs arrival words** (§5d.6), with one exception: the patient's own dose taken for this problem
   is always before arrival. A dose by family, facility staff, fire or a bystander with only a clock or past time
   ("mom gave him Tylenol at noon", "the nurse gave a Percocet at 2200") leaves it out; so does "bystander CPR" with
   no timing. Arrival words cover every dose or procedure in the same sentence from the same speaker ("I gave him a
   nitro before you got here and made him chew an aspirin" → both); "CPR in progress on arrival" and "we took over
   compressions" count as arrival words.
3. **12-lead details.** A reading alone ("monitor's calling an inferior STEMI") gives `ecg.stemi_reading` (and
   territory) but not `ecg.attached`. A failed send gives `ecg.transmitted` false only. Two tracings in one
   utterance ("first one nondiagnostic, repeat shows a STEMI") give one fact each, like rechecked vitals (§4b).
   "V4R elevation" and "RV infarct" give "right ventricular" (§5d.2 names them); other leads alone give no territory.
4. **Drug names the coder writes back in another form.** Pradaxa is labeled "dabigatran" (the name every earlier
   label and gold set uses; RxNorm has both "dabigatran" and "dabigatran etexilate", MODEL_PLAN §0j). Adderall is
   labeled "amphetamine / dextroamphetamine" (the coder's name). "LR" / lactated Ringer's is "lactated ringer's"
   (not in RxNorm, kept as said).
5. **Volumes and rates.** A volume is labeled as said, because a dose must be a number that was said (§5,
   `config/grounding.yaml`): "one liter of LR" → dose 1, unit "L"; "500 cc" → 500 mL. With no number said
   ("a liter of saline", "second liter hanging"), the record has the drug and who gave it, no dose or unit.
   (Changed Thu 2026-09-24 before run F: litres used to be converted to 1000 mL, which the production grounding
   drops as a number never said, so the model would have learned output the app always discards; 8 lines relabeled.) A running infusion's rate ("nitro drip at twenty mics a minute") is
   not a dose: the record has the drug and who runs it, no dose.
6. **Procedure names** (§5d.8) are a starting list, not a closed one: other interventions are short lowercase names
   as NEMSIS would call them ("back blows", "active rewarming", "physical restraint", "irrigation"). A device said to
   be in place is also a procedure (§5d.3).
7. **Crew concern is an impression.** "I'm worried about an ectopic", "concern for meningitis", "suspect X" →
   `impression.primary` (and the infection source where it applies, §5c.4), like "probably" or "looks like". A
   differential ("could be X, could be Y", "X versus Y") gives none.
8. **Age under one year** is `patient.age` 0 ("nine months old", "six weeks old"); "eighteen months" → 1.
9. **"Alert but confused"** → `vitals.consciousness` "C" (new confusion is reported over alert).
10. **A dose reported by the medic without attribution words** ("his mom gave the EpiPen at 1340") is role `medic`
    with `by` "family"; with them ("mom says she gave…") it is role `family` (§3).
11. **"Tombstones" or ST elevation in named leads** without a reading give no `ecg.stemi_reading`; "the inferior
    leads" names a territory (§5d.2).
12. **Riders.** A solo crash on a pedal bicycle ("went over the handlebars on the trail") gives no criterion; an
    e-bike or stand-up scooter rider thrown gives "rider separated with significant impact"; "run over" gives the
    pedestrian/cyclist criterion at any speed; exactly 12 inches of intrusion gives none (over 12).
13. **Airway with an adjunct and bagging** ("OPA in, bagging at ten") is "bag-valve-mask ventilation": the support
    being given wins over the adjunct. A responder on the mic (fire, incident command) giving a triage category or
    an airway status is role `bystander` (§3) and the fact is still labeled.
14. **A rate said with a rhythm** ("sinus tach at 124", "a-fib at 110", "paced at 70") is `vitals.hr`, as every
    earlier batch labels it. "A 12-lead shows X" is a reading (point 3), not "done": no `ecg.attached`.
15. **Inhaler puffs and tablets.** "Four puffs of albuterol" → `count` 4 (a puff is not a unit); "chewed four baby
    aspirin" → one dose with no count and no dose (the number is tablets, not an amount in a unit); "two Benadryl,
    twenty-five each" → dose 25, `count` 2.
16. **Restraint or seat position alone is not a mechanism** ("front passenger, restrained", "in his booster"):
    no `trauma.mechanism` unless the event is said (a crash, a rollover). It still counts toward "rollover
    unrestrained" or "child unrestrained" when the event is said too.
17. **Route is filled only from a route word**: "IV", "IM", "IN", "PO", "SL", "neb", "PR", "IO", "SQ", or a verb
    that names one ("chewed", "swallowed" → PO; "under the tongue" → SL; "in the thigh" with an auto-injector → IM;
    "up the nose" → IN). A brand or dosage form ("DuoNeb", "Zofran ODT", "Narcan spray") does not fill it.
18. **Routine home care is not a procedure event**, like usual daily pills (§4e): a parent's regular trach suctioning
    or a scheduled dressing change gives no `procedures.done`; care given for this problem ("I suctioned him when he
    started gurgling") does.
19. **The sign phrases listed under §5c.4 are themselves the suspicion** when the crew or a caregiver says them of the
    patient ("foley's cloudy and foul" → "urinary"; "pus at the port site" → "device"). A symptom alone ("burning
    when she pees", "coughing") is not.
20. **A symptom said only as improving or resolved** ("the nausea's better now") gives no `complaint.chief`.

21. **Suspected spinal injury from the words.** New numbness, tingling or weakness after an injury, together with neck
    or back pain or a mechanism that loads the spine (diving into shallow water, landing on the head, a head-first
    tackle, a crash), gives "spinal injury with new motor or sensory loss" even when "suspected" isn't said; the
    role is whoever reported the deficit. Numbness alone after a hand or limb injury does not.
22. **Fever with no number** is `complaint.chief` "fever" (there is no `vitals.temp` to hold it, §4c).
23. **Units the list doesn't name** are kept as said when spoken as a unit ("one inch" of nitro paste → dose 1, unit
    "inch"). An approximate age ("fifty-ish", "in her forties") gives no `patient.age`.
24. **An ingestion time on an overdose** ("took them at 1900") is `symptom.onset`, like an injury time.
25. **A rescue drug the patient carries but didn't use** (an EpiPen in her purse) gives no `meds.list`; one said to
    be theirs and used or prescribed ("her EpiPen, she used it") does.
26. **A sending physician or nurse on a transfer** ("sending doc says the CT showed a subdural") is relayed by the
    medic: role `medic`.
27. **Active bleeding with no wound named** ("bleeding from somewhere on the scalp", "blood in the mouth") is not a
    `trauma.injuries` item; a named wound is. Petechiae or discoloration without a wound are signs, not injuries.
28. **An event named only as the reference of a hedged time** ("sometime after the fight") is not a stated
    mechanism or complaint.

29. **`count` is only for more than one dose** ("narcan x2", "three nitros"): a single dose ("one Narcan", "narcan
    x1") has no `count`, as in every earlier batch.

## 5f. Spanish speech (Mexican Spanish at the scene; 2026-09-24, MODEL_PLAN §0k "Spanish (Mexican) speech")
Patients, family and bystanders in Santa Clara County often speak Spanish (mostly Mexican Spanish), and medics
code-switch ("le dimos 324 de aspirina", "está diaphoretic"). The utterance text is the Whisper transcript in the
language that was spoken; it stays the fact's evidence. The labels do not change language. Numbered like §5c.

1. **Same facts, English values.** A Spanish utterance gets exactly the facts its English equivalent would get under
   §2–§5e: the same keys, roles, sources, enums, numbers, booleans and record fields. Every string value is English:
   ACVPU letters, "F"/"M", enum values, units ("mg", "mL"), routes ("IV", "PO"), `by` categories, procedure names,
   time words ("5 pm", "1 hour ago", "since 5"). Nothing is labeled in Spanish.
2. **Drug names are the RxNorm ingredient in English** (§4, §5c.2), whatever language or country the name comes from:
   a Spanish generic ("metformina", "insulina", "aspirina", "paracetamol") becomes the English ingredient ("metformin",
   "insulin", "aspirin", "acetaminophen"); a Mexican brand ("Tempra" → "acetaminophen") is a brand like any other. A
   name the labeler cannot pin to one ingredient is kept as said, like an English one; a drug class without a name
   ("pastillas para la presión", "algo para el corazón", "pastillas para la sangre") is not `meds.list` (§4c).
   An international name that differs from the US one is the US RxNorm name ("salbutamol" → "albuterol",
   "glibenclamida" → "glyburide", "paracetamol" → "acetaminophen"): "unresolved" in the coder is not a licence to keep
   a Spanish spelling. Allergens and foods are English and lowercase ("penicilina" → "penicillin", "camarón" →
   "shrimp").
3. **Free-text keys are a faithful short English rendering** of what was said, not a translation of every word and
   not an interpretation: `complaint.chief`, `trauma.mechanism`, `impression.primary`, `scene.notes`,
   `stroke.deficits`, `trauma.injuries`, `procedures.done` `detail`. "Se cayó de la escalera" → "fell from a ladder";
   "le falta el aire" → "shortness of breath". `transport.destination` keeps the hospital's name ("el Valley" →
   "Valley Medical" only if said so; otherwise as said, e.g. "Valley").
4. **Colloquial terms mean what they mean in everyday Mexican Spanish.** Knowing that meaning is the model's job, the
   same way it knows "sugar" is glucose; the guide gives no word list. The label is still only what was said (§2):
   - a named condition in the patient's history ("tiene el azúcar", "tiene la presión alta", "es diabético") gives
     no fact, exactly as "he's diabetic" gives none; a number said for it does ("el azúcar le salió en cuatrocientos"
     → `vitals.glucose` 400);
   - a problem happening now, named by the caller ("le dio un derrame", "se desmayó", "le falta el aire",
     "está convulsionando") is `complaint.chief`, in English, as the caller's words say it ("stroke", "passed out",
     "short of breath", "seizing"). It is the caller's complaint, never the crew's `impression.primary` (§5d.4),
     and it gives no `stroke.*` keys unless stroke-like symptoms are described (§4c);
   - an ambiguous word is labeled only when the words around it fix the meaning ("le dio un ataque, se puso a
     temblar" → seizure); a bare "le dio un ataque" with nothing to fix it gives no complaint.
5. **Numbers said as Spanish words become digits** (§5): "ciento ochenta sobre cien" → 180/100; "noventa y dos" →
   92; "dos disparos de Narcan" → `count` 2; "treinta y siete y medio" → 37.5. "Siete meses de embarazo" gives no
   `patient.pregnancy_weeks` (months are not weeks, as in English; the grounding check would drop a converted number).
6. **Times** follow §4c/§5b with English words: "desde las cinco" → "since 5"; "hace como una hora" → "1 hour ago"
   (the approximator "como" is dropped); "a las tres de la tarde" → "3 pm"; "anoche a las diez" → "10 pm"; "esta
   mañana a las siete" → "7 am"; "a las catorce treinta" → "14:30". Hedges ("creo que", "no sé", "a lo mejor",
   "como que") give no fact, as "I think" or "maybe" do.
7. **Negations and denials** follow §5: "no toma nada" gives no fact (no drug was named; no anticoagulant "none"
   either); "no toma nada para adelgazar la sangre" / "no toma anticoagulantes" → `meds.anticoagulant` "none"; "no
   es alérgico a nada" → `allergies` []; "no le duele el pecho" gives no complaint.
8. **Sex descriptors:** "señora", "mujer", "muchacha", "niña" → "F"; "señor", "hombre", "muchacho", "niño" → "M",
   when said as a descriptor of the patient (as "lady", §4). A pronoun or grammatical gender alone ("ella", "está
   cansada") is not a statement of sex.
9. **Roles and speakers** (§3): "mi mamá", "mi esposo", "mi hija" on the mic → `family`; "el vecino", "un señor que
   pasaba" → `bystander`; the patient speaking ("me duele aquí") → `patient`. The `speaker` field and the fact's
   source are English relation words ("daughter", "husband", "neighbor"), because the speaker line the model sees
   is built by the app, not transcribed.
10. **Code-switching medics** are labeled like any medic line: "le dimos 324 de aspirina" → `meds.given` {"drug":
    "aspirin", "dose": 324, "by": "crew"} (no unit said, §5d.7); "está diaphoretic" gives no key (a sign with no
    key); "le pusimos una IV en el brazo izquierdo" → `procedures.done` "iv access", detail "left arm".
11. **Code status** follows §4 and §5b: "tiene una orden de no resucitar" / "no quiere que la revivan, tiene el
    papel" → "DNR"; "que hagan todo lo posible" is a wish, not a code status (no fact). A remembered wish ("no
    quería que la conectaran a máquinas") and a hedged denial ("no tiene papel de no resucitar, no que yo sepa") give
    none either; a POLST said to ask for resuscitation ("dice que sí la revivan") is "full code" (§5b).

Rulings from the adjudication of batches 32–39 (2026-09-24; the writers' GAP notes and the blind second pass,
MODEL_PLAN §0k "Spanish (Mexican) speech"). They apply to English speech too; each matches an earlier English label.

12. **A drug the patient ran out of is still their medication** ("toma Keppra pero se le acabó hace una semana",
    "no se ha puesto la insulina porque se le acabó" → `meds.list`): missed doses are the story. A drug a doctor
    stopped or replaced ("ya no toma el Coumadin", "se lo cambiaron por el Keppra") is not (§5b).
13. **A low or high reading named with its number is only the reading**: "se le bajó el azúcar … salió en cuarenta y
    dos" → `vitals.glucose` 42 and no `complaint.chief` (§4c: a structured key holds it; English b06_042). Without a
    number, a problem happening now is the complaint ("se le bajó el azúcar" → "low blood sugar", §5f.4).
14. **"La señora" / "el señor" said of the patient is a descriptor**, like "the lady" in English (§4): "la señora es
    alérgica a la penicilina" → `patient.sex` "F". A relation word ("mi mamá", "mi papá", "mi abuelito") is not.
15. **Witnessed onset needs seeing words** (§4c): "yo la vi cuando empezó", "estaba hablando conmigo y de repente…"
    → true; "yo estaba con él en la cocina" alone states presence, not seeing (no fact); "llegué y ya estaba así",
    "cuando salí ya estaba en el piso" are found → false; "oí el golpe" alone is neither.
16. **Missed dialysis is the presenting problem** when said as such ("se dializa lunes, miércoles y viernes y hoy no
    fue", "missed his Tuesday run") → `complaint.chief` "missed dialysis" (English b28_122). Being a dialysis
    patient alone is history (no fact).
17. **A volume is labeled as said**, as in English (§5e.5): "un litro de suero" → dose 1, unit "L" ("un" is a said one).
    "Suero" (IV fluid) is "iv fluids" unless the kind is named ("solución salina" → "sodium chloride").

## 6. Phenomena tags (use all that apply)
`clean`, `shorthand` (yom, sats, A&O, D-stick…), `spoken_numbers`, `correction`, `negation`, `attribution` (someone else's statement), `other_speaker` (`by: "other"`), `multi_event` (many facts in one utterance), `no_facts`, `uncertain` (hedged statements that must yield no fact), `brand_names`, `fahrenheit`, `disfluency` (uh, um, restarts), `asr_noise` (the kind of errors speech-to-text makes: missing punctuation, homophones, lowercase), `spanish` (spoken in Spanish, §5f), `code_switch` (Spanish and English mixed in one utterance, §5f).

## 7. Scoring (how `eval/bench_extract.py` uses labels)
- Headline F1 is over **structured keys** as exact `(key, normalized value)` pairs.
- **Free-text keys** (`complaint.chief`, `stroke.deficits`, `transport.destination`, `scene.notes`) are scored by **key presence** only, because paraphrases are not errors.
- Role accuracy is measured on matched facts.
- Report precision and recall, not only F1. Run model extractors 3 times and report the spread (AGENTS.md hard rule 3).
