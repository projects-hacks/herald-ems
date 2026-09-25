# Herald final training plan (run F): one run, then the model is locked

Written Thu 2026-09-24, 18:40 UTC (11:40 PDT). Feature freeze: Fri 2026-09-25, 11:00 PDT (18:00 UTC).

This file is the single plan for the last model training of the hackathon. It lists:
- every model the app uses and what each must do;
- what is done and what is left;
- what the final run contains and what it deliberately leaves out;
- the gates the result must pass;
- the rollback.

After the gates pass, the served models are **locked**: no more training, no swaps, and only prompt fixes that are re-verified on the same benches. Details of earlier runs are in [MODEL_PLAN.md](MODEL_PLAN.md) (§0g–§0j, §2a).

## 1. Every model the app uses

| # | Job | Today | Built how | Covered by the final run? |
|---|---|---|---|---|
| 1 | Speech → facts (49 keys, records for doses/procedures, speaker role, dispatch context) | `ems-e-v2-fp8` (Qwen3-4B + LoRA run E v2) | fine-tuned | **Yes**: retrained on the 30B |
| 2 | Photo reading (monitor/wearable/app screens, pill bottles, forms, scene) | `qwen3vl-fp8` (Qwen3-VL-30B-A3B-Instruct-FP8) | prompt only | **Yes**: same 30B, LoRA on photo data, prompts unchanged |
| 3 | Protocol figure transcription (7–8 flowchart/chart pages, cached) | `qwen3vl-fp8` | prompt only | Kept prompt-only; the replay slice (§4.4) guards it |
| 4 | Protocol passage reranking + "answerable" flag | `qwen3vl-fp8` | prompt only | Kept prompt-only; the replay slice guards it |
| 5 | Interpreter translation (S3, not built yet) | would be the 30B | prompt only | Kept prompt-only; the replay slice guards general ability |
| 6 | Speech-to-text | whisper-large-v3-turbo | off the shelf | No: Qwen3-VL has no audio input |
| 7 | Protocol search embeddings | bge-base-en-v1.5 (CPU) | off the shelf | No |
| 8 | Diarization (S4) | pyannote community-1 (needs HF terms accepted) | off the shelf | No |
| 9 | Speech output (S3) | Kokoro/Piper (needs espeak-ng) | off the shelf | No |
| — | Handoff report, scores, checklists, relay, RxNorm coding, injection guard | none | templates and rules by design (AGENTS.md invariant 2) | n/a |

**Result: one served LLM (`herald-f`, the fine-tuned Qwen3-VL-30B-A3B) replaces two (`ems-e-v2-fp8` + `qwen3vl-fp8`).** Whisper, bge and pyannote stay: they do jobs an LLM can't do here. `ems-d-fp8` (run D, rollback only) is unloaded for good.

### Why one 30B model and not the 4B + the 30B

- **Speed.** Measured today on the extraction prompt, 3 interleaved runs of 9 requests each, the untuned 30B-A3B (FP8) was as fast as or faster than the live 4B:

  | Run | 4B median ms | 30B median ms | 4B tok/s | 30B tok/s |
  |---|---|---|---|---|
  | 1 | 1888 | 1875 | 42.7 | 46.4 |
  | 2 | 4062 | 2883 | 20.6 | 31.6 |
  | 3 | 4080 | 2823 | 20.5 | 31.8 |

  Runs 2–3 ran while something else loaded the box. That condition applied to both models equally, and the MoE held up better. Only 3B parameters are active per token, so decoding is no slower than a dense 4B.
- **Memory.** One model frees the 4B's ~15 GB share for Whisper and KV cache, and removes a model the team has to keep in sync.
- **Knowledge.** A 30B knows more drugs, mechanisms and phrasing than a 4B. Run E's residual errors (drug classes, numbered products, trauma criteria) are knowledge-shaped.
- **Honest caveat.** A prompt-only general model scored only 0.661 as an extractor (Omni, MODEL_PLAN §0h). The 30B *must* be fine-tuned on the same data and pass the same held-out gates. Until it does, `ems-e-v2` stays on disk as the fallback (§7).

## 2. What is done (verified, with numbers)

| Area | Status | Numbers (3 runs where it decided something) |
|---|---|---|
| Extractor run E v2 | live | held-out gold v2 F1 0.948–0.952 (+0.032 vs run D, CI [+0.013, +0.053]); G.F.A.S.T. 0.961; every-call v3 0.922–0.928; new keys 0.84; dispatch set 0.918; who-said-it 0.972–0.976 |
| Confidence calibration | done for E v2 | auto-confirm ≥ 0.8: dev 193/286 with 0 wrong, held-out 173/327 with 1 wrong, AUROC 0.958 |
| Vision (prompt only) | live | 45 synthetic photos F1 0.989 (43/45 exact); with 12 phone/watch screens F1 0.982, p95 12.6 s (prompt rewrite in progress) |
| Protocol lookup | live | 32 county documents, 1,804 passages; right passage first 17/22, top-3 19/22 |
| Handoff report | built today, template only | live run on the real models produced a correct MIST report; 402 tests pass |
| Soak (C3.8, Vineet) | ran 30 min | 0 model errors, 0 relay failures, memory flat; latency flat 27 min, then a spike that coincided with a vision benchmark on the shared GPU. Rerun on the locked model |

## 3. What is left that touches the model

Found by: the run E v2 error analysis, the adversarial bench, today's live handoff run, and the model inventory.

**Speech extraction errors to fix with data (not rules):**
1. `trauma.criteria` recall 0.19 and `infection.suspected` recall 0.11.
2. ECG: "inferior STEMI" gave no `ecg.stemi_reading` (live handoff run); ECG keys have low confidence.
3. Said vs planned vs advised vs refused: a bystander's "give her 325 aspirin" was recorded as given; "we'll start fentanyl" is not a dose.
4. Injected "DNR" accepted twice (adversarial).
5. Numbered/combination products lose ingredients ("Tylenol 3", "Percocet 5/325", "Humalog 75/25").
6. Old drug spellings in the training labels vs the names the RxNorm coder accepts.
7. Dose records:
   - unit missing ("324 PO");
   - one time said for two doses attached only to the second;
   - procedure names in lowercase.
8. Last-known-well, onset and deficits land below the 0.8 confidence bar in the demo, so they need extra taps.
9. Whisper-style transcription noise: the training data has only light text noise, and real voices are unmeasured.

**Vision errors:**
1. Glucometer "HI" read as a number.
2. POLST with only section B checked.
3. 2 of 57 photos had an invented fact.
4. Rotation is the weakest degradation.
5. p95 latency 12.6 s on phone/watch screens.
6. All test photos are synthetic.

**Items the vocabulary cannot represent yet** (live handoff run; §8 decision 1): time of injury, a dose given before arrival, airway status, the EMS primary impression, the 12-lead's territory. Also `triage.category` for mass-casualty mode (S5). **A key that isn't in the vocabulary when we train can't be trained later without a second run**, so this is decided before the run.

## 4. What the final run contains

### 4.1 Speech data (run F text set: `data/train_f/`, MODEL_PLAN §0k)
- All of run E v2's data (3,340 rows).
- ~1,000–1,500 new utterances covering every item in §3 "Speech", across all call types (falls, diabetic, seizure, overdose, OB, respiratory, psych, arrest, pediatric, elderly), so the mix doesn't skew toward the fixes.
- New keys from §8 decision 1, with enough examples each (≥ 60 positives, plus negatives).
- Labels written in a separate pass from generation (labeling guide + vocabulary only), then adjudicated; agreement rate reported.
- The drug-spelling relabel list applied at build time.
- A Whisper noise layer made of real Whisper output (done, MODEL_PLAN §0k "Measured ASR noise"):
  - 1,500 train lines, stratified over all 54 keys, were spoken by 8 Piper TTS voices (4 female, 4 male, rate jitter).
  - Each was mixed with synthetic cabin noise: clean, or SNR 15, 8 or 3 dB. The noise is engine rumble, brown and pink noise, with a siren or monitor beeps on some clips.
  - Each was transcribed by the production Whisper path (`WhisperSTT`, turbo, priming prompt).
  - A transcript is kept only if the production grounding rules still support every label and every said number survives. Misheard drug names are kept.
  - Kept transcripts are added to train only (`--asr data/annotated/asr_f.jsonl`), with the clean labels as targets. Dev stays clean text.
  - Measured on TTS speech, not human speech: WER 13.2 %, number error 9.5 %, drug-name error about 43–45 %. The noise did not measurably change these: 92 % of its energy is below 300 Hz.
- Decontaminated against every gold set (v1/v2/v3/ctx/broad), the adversarial bench and the scenario scripts.
- The same prompt and input lines as run E v2 (the `ems-e` format under a `herald-f` profile): "the prompt stays".

### 4.2 Photo data (`data/vision_train/`, MODEL_PLAN §2a "Vision training set")
- ~2,500–4,000 synthetic photos from a generator written separately from `eval/photos` (test only).
- Metrics, not screens:
  - randomized devices (monitors, AEDs, fingertip oximeters, watches, bands, phone health apps, BP cuffs, glucometers, thermometers, capnography);
  - randomized layouts, units, fonts and colors;
  - distractors (alarm limits, clocks, steps, battery, trends);
  - degradations (glare, blur, tilt, rotation, low light, occlusion).
- Negatives: no clinical content; unreadable values must be omitted, not guessed.
- Drug labels drawn from the whole public RxNorm subset, not only anticoagulants; documents (POLST/DNR variants, medical IDs, medication lists).
- Targets are exactly what the production prompt asks for, and the prompts are read from `config/prompts/vision.yaml` at build time ("the prompt stays").
- Dev split holds out whole layout families, so it measures unseen devices.

### 4.3 Training (`scripts/train_vlm_lora.py`, MODEL_PLAN §0l)
- Base: `Qwen/Qwen3-VL-30B-A3B-Instruct` BF16 (downloading; ~61 GB).
- LoRA BF16, gradient checkpointing, vision tower frozen; the target modules are decided and justified in §0l.
- Loss only on answer tokens.
- Prompts formatted byte-for-byte like `llm_client.chat_json` sends them (system, user, image data URI, thinking off).
- Checkpoints saved regularly. **Two checkpoints (end of epoch 1 and epoch 2) are both evaluated, and the better one is picked. This is how we avoid a second run.**
- Merge → private HF repo `…-merged-f` → served by ZRT as `herald-f` with vLLM online FP8 (`--quantization fp8`).

### 4.4 Keeping what the base model already does well (replay slice)
The same 30B also reranks protocol passages, transcribes flowcharts and will translate (S3). A LoRA trained only on extraction can erode those.
- **What the slice is:** 5–10% of the training mix, made from the base model's own answers to those prompts (self-distillation).
- **What it uses:** the protocol passages, the figure pages and generic translation prompts. It does not use the benchmark questions, which stay test-only.
- **How it's checked:** rerank and figure benches run before and after (§6).

### 4.5 Deliberately not in the run
- **Quote spans per fact (B3).** It adds output tokens to every call, so latency goes up. Numbers are already grounded in what was said. Decision 3 below.
- **Audio input, Spanish extraction.** Whisper transcribes; the interpreter (S3) translates to English before extraction.
- **Retraining Whisper, bge or pyannote.** There is no in-domain labeled data and no time to measure it properly.

## 4.6 Measured on the real 30B, and what it bought (2026-09-25)

The run was planned against an assumed 180 padded tokens/s, scaled from a single-layer benchmark. The memory ladder
(MODEL_PLAN §0l) measured the real figure on the full model: **401 padded tokens/s**, 2.2× faster than assumed. The
ladder also fixed the reason the 30B could not be loaded at all — `from_pretrained` transiently needs about twice the
checkpoint on this box, so the weights are now streamed shard by shard (§0l).

**Owner decision, 2026-09-25: spend the spare time on vision.** `config/training.yaml` `herald-f`
`mix.image_rows_per_epoch` 600 → **1200**, so ~2,400 of the 3,460 synthetic photos are seen over the two epochs
instead of 1,200. Nothing else in the mix changed. Photo reading is the job with the least training signal
(§3 "Vision errors": all test photos are synthetic, rotation is the weakest degradation, 2 of 57 photos got an
invented fact), so more photo rows is the highest-value use of the extra hours.

Cost: 413 → **488** optimizer steps, 4.27 M → **5.43 M** padded tokens, projected **~3.0 h → ~3.8 h** at the measured
speed. The deadline is Fri 11 PM PDT (06:00 UTC Sat), so a ~3.8 h run started before 05:00 UTC still leaves the whole
of Friday for the gates, the soak and the deck.

## 5. Schedule (UTC; PDT = UTC − 7)

| When (UTC) | Step | GPU? |
|---|---|---|
| Thu 19:00–22:00 | Speech data, photo data, trainer + tests (3 agents, in progress); base download | no |
| Thu 22:00 | Freeze the data. Unload `qwen3vl-fp8` and `ems-d-fp8`. **Photos, figure reading and protocol reranking are down from here until `herald-f` serves**; speech stays live on `ems-e-v2-fp8`. The team is told first | yes |
| Thu 22:15 | 20-step smoke on the real 30B (memory, speed, loss falling) → final time estimate | yes |
| Thu 22:30–~04:00 | Training (estimate firmed up by the smoke) | yes |
| Fri ~04:00–05:30 | Merge, push, serve `herald-f` | yes |
| Fri ~05:30–09:00 | Gates (§6), 3 runs each, on both checkpoints | yes |
| Fri ~09:00 | Lock, or roll back (§7). Rerun the soak and the replays on the locked stack | yes |
| Fri 09:00–18:00 | Buffer for rollback; the team works on UI, demo, real photos | — |

## 6. Gates: all must pass to lock
Every deciding number is run 3 times. Comparisons use the paired bootstrap against run E v2 / untuned Qwen3-VL on the same items and under the same conditions (no other GPU job running).

**Speech:**
- held-out gold v2 F1 not worse than E v2 (CI lower bound > −0.01);
- G.F.A.S.T. ≥ 0.95;
- every-call v3 ≥ 0.92;
- dispatch set ≥ 0.91;
- `trauma.criteria` and `infection.suspected` recall ≥ 0.6;
- ECG STEMI reading found;
- adversarial ≥ 19/25 seen and ≥ 24/40 unseen, with the "give her aspirin" and "DNR" cases fixed;
- calibration refit for `herald-f`: held-out auto-confirmed wrong ≤ 1;
- p95 latency ≤ E v2's measured the same way.

**Photos:**
- `eval/photos` F1 ≥ 0.98;
- the phone/watch set ≥ the untuned model;
- invented facts ≤ the untuned model;
- real photos ≥ the untuned model (if taken; §8 item 4);
- p95 ≤ the untuned model.

**Kept abilities:**
- protocol reranking on all 59 questions no worse than the untuned model's baseline (measured Thu 19:30 UTC, 3 runs, identical each time; `eval/dumps/vision/baseline_untuned/`):
  - right passage first 41/52 (0.788);
  - top 3 43/52 (0.827, equal to the retrieval ceiling);
  - first given retrieved 0.953;
  - refusals 4/7;
  - p50 447 ms;
- 700-A13 figure transcription no worse than the baseline (nodes 0.875, edges 0.857, no added words; 3 runs identical);
- translation spot check (10 lines) readable and faithful.

**Demo:** `scenarios/stroke_demo.json` 6/6; `scenarios/shift_demo.json` passes end to end; 30-min soak passes.

### 6a. Kept abilities are a hard gate, per epoch (owner, 2026-09-25 07:00 UTC)

Added after the epoch-1 dev losses showed the replay slice drifting while speech and photos improved: text 0.1883 → 0.1287 → 0.1195 → **0.0899** and image 0.2822 → 0.2510 → 0.2681 → **0.2292** (the 122 blip was noise on an ~80-item set), against replay 0.0894 → 0.0920 → 0.0961 → **0.1393**. The first three replay steps were +0.003 and +0.004; the fourth was **+0.0432**, and every pass moved the same way. Replay dev is only 40 rows, so the direction is stronger evidence than the size, and it is a proxy. **The gates below are the actual test.**

**Each epoch adapter must pass all of these on its own. An epoch that fails them cannot ship, whatever its speech and photo numbers are.**
- protocol reranking, all 59 questions: right passage first **≥ 41/52** (0.788), top 3 **≥ 43/52** (0.827), refusals **≥ 4/7** (0.571);
- 700-A13 figure transcription: nodes **≥ 0.875**, edges **≥ 0.857**, **no added words**;
- 10-line EN↔ES translation spot check: faithful.

**Which adapter ships:**
1. Epoch 2 if it passes kept abilities and wins on speech and photos.
2. **Epoch 1 if epoch 2 fails kept abilities and epoch 1 passes them** — this is why both adapters are saved and separately backed up, and why the run is not repeated to "fix" drift.
3. If **both** epochs fail kept abilities but win speech and photos, evaluate the **split stack** before falling back (§7a).

**Decide from `runs/herald-f-lora/log.jsonl`, not from `herald_epoch.json`.** The epoch adapter is written in `on_step_end`, which fires *before* that step's dev pass reaches `state.log_history`, so `herald_epoch.json` carries the **previous** pass's losses: epoch-1's file records step 122, not step 244. To be fixed after the run (a trainer edit, not a mid-run change).

### 7a. Split stack (only if both epochs fail kept abilities but win speech and photos)

Serve the fine-tuned model for what it is good at and the untuned base for what it lost:
- `herald-f` for extraction **and** photos (`HERALD_LLM_MODEL`, `HERALD_VISION_MODEL`);
- untuned `qwen3vl-fp8` for reranking, figure transcription and translation, through a **new `HERALD_KNOWLEDGE_MODEL`** setting (`herald/config/settings.py`, wired in the composition root; `herald/knowledge` currently reaches for the vision model);
- both at `--gpu-memory-fraction ~0.30`.

This costs a second resident 30B, so it is a memory decision, not just a config one: **measure free memory with the app and Whisper already up before choosing it** (`docs/MEMORY_SAFETY.md`, demo memory budget). If it does not fit alongside the demo, prefer rule 2 (ship epoch 1) or the §7 rollback.

The operator procedure — the fit check, starting both models, verifying `/api/stack`'s `jobs` block, and rolling back — is **`docs/RUNBOOK.md` §7**. It is untested until the box is free.

## 7. Rollback
If the gates fail, reload `qwen3vl-fp8` + `ems-e-v2-fp8`. This is today's verified stack, and it takes ~20 minutes. The downside is limited to the photo downtime. Neither of those models is deleted or changed.

If *only* photos fail and speech passes (or the reverse), serve `herald-f` for the job that passed and the old model for the other. This is a config change (`HERALD_LLM_MODEL` / `HERALD_VISION_MODEL`), not a retrain.

## 8. Decisions (made by the owner, Thu 18:40 UTC)
1. **New vocabulary keys: all six, added.** `config/vocabulary.yaml` now has 54 keys:
   - `trauma.injury_time` (time);
   - `ecg.territory` (list: inferior, anterior, septal, lateral, posterior, right ventricular);
   - `airway.status` (patent, patent with adjunct, supraglottic airway, endotracheal tube, bag-valve-mask ventilation, compromised);
   - `impression.primary` (the medic's words);
   - `triage.category` (SALT: immediate, delayed, minimal, expectant, dead; always needs a tap, like code status; colors are for the model to map, not synonyms coded in config);
   - the field `before_arrival` on `meds.given` and `procedures.done`.

   Relay tiers were updated. The run F data covers each key with ≥ 60 positives plus hard negatives, and the labeling guide gets a rule for each.
2. **One model: `herald-f`** for speech + photos; E v2 stays as the fallback.
3. **Quote spans: no.**
4. **Real photos: the team takes 20–30 by ~22:00 UTC (3 PM PDT)** into `data/photos/real/`, with a line each saying what the screen or label shows. They are test only.

## 9. Fixes at run time after the run (no retraining; each is measured on the gold sets before and after, 3 runs)
Found while the run F data was finished (Thu 22:55–23:10 UTC).

1. **Grounding is too strict for some correct facts.** 340 of 18,300 training labels (1.9%) are correct but are rejected by `config/grounding.yaml`'s cue words and number checks, so the app drops them at run time today, run E v2 included:

   | Key | Rejected labels | Example that isn't accepted |
   |---|---|---|
   | `vitals.consciousness` | 71 | "A and O ×4" |
   | `stroke.onset_witnessed` | 47 | "saw her words go slurry at four" |
   | G.F.A.S.T. and RACE items | about 160 | "everything else zero" |
   | `vitals.gcs_motor` | 8 | "e3 v5 m6" |
   | vitals | 7 | split digits, "bp 1 42 over 88" |

   The fix is config in the safety validator (not extraction rules), measured on gold v1/v2/v3/es. The Spanish `code_status` pattern also misses "no quiere que lo revivan", the guide's own §5f.11 example (b39_087). The Spanish agent counted 64 English lines that would newly match "A and O".
2. **Grounding drops the whole record when one field isn't said.** A dose record with an unsaid dose loses the drug too. Consider stripping the unsupported field and keeping the rest. This is a safety-relevant change; decide with the owner and measure it.
3. **Whisper's English priming prompt leaks into Spanish.** "alergias" was heard as "Eliquis", a drug named in `config/prompts/stt_prompt.txt`, so a blood thinner could be proposed that nobody said. Use a language-neutral prompt, or none, when Whisper detects Spanish (config), and re-run the 30-clip Spanish check. One clean clip also fell into a repetition loop ("lo vi" ×20); the repetition guard should cover Spanish.
4. The **S3 interpreter backend** (translate, with Spanish speech output once `espeak-ng` is installed), using `config/prompts/translate.yaml`, the same prompt the replay slice kept.
