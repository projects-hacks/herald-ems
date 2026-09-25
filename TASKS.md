# TASKS.md: Herald task board

## Tushar review follow-up (Fri 25 Sep)

Owner-requested integration: `feat/c1-now-screen` + `feat/agentic-capture` + `feat/ui-review-gaps`, checked together on `feat/merge-tushar-work` before updating main. The ambulance workspace is the default medic screen; detailed and guided-demo views remain available. See [MERGE_VERIFICATION.md](docs/MERGE_VERIFICATION.md). This delivery does not waive real-model, physical-device or clinical acceptance gates.

U1/U2/U3, U4/U5/U6/U7, U8 frontend, U10/U11 and X3 implemented, now integrated with the ambulance UI and C1 agentic capture at the owner's request. Combined checks: 465 backend tests passed, one skipped; 77 UI tests passed; build and contrast checks passed. Details in [UI_REVIEW_GAPS.md](docs/UI_REVIEW_GAPS.md). Physical mic/tablet/three-metre ED checks remain. U13 stays gated on model lock with Jenil; U8 startup default remains with Vineet; C1 real-model acceptance still needs Rajeev's serving approval.

Deadline **Fri 2026-09-25, 8:00 PM**. Internal target: submit by 6:00 PM. Feature freeze Fri 11:00 AM.
**Scope: the full product ships. Nothing is cut** (team lead, 2026-09-23). P1–P10 is the **build order** (dependencies and what gets hardened first), not a cut list. If something runs late, add people to it. The only things we never build are safety principles, not scope cuts: treatment/dose/eligibility advice, cloud AI inference, and self-trained clinical predictors. Rules for agents: `AGENTS.md`.
Where decisions live: product spec and pitch → `/home/hp18/Documents/team-last-minute/.agent/ideas/herald-ems-copilot.md` (Nano only) · models → `docs/MODEL_PLAN.md` · UI → `docs/UX_PLAN.md` · hackathon rules and history → `/home/hp18/Documents/team-last-minute/.agent/context.md` (Nano only). The full document map is in `AGENTS.md`.
Status: ✅ done · 🔄 in progress · ⏳ todo · ⛔ blocked. Update this file in the same PR as the work.

## Medic experience implementation — 2026-09-25 (@tushar-fs clone)

- ✅ Ambulance workspace replaces the default medic sidebar: stable latest-reading positions, persistent capture/priority controls, large view, in-place details, daylight/night themes.
- ✅ Explicit-start continuous ambient audio with bounded local clip uploads, unverified-speaker confirmation holds, and incident-scoped delayed extraction.
- ✅ Camera preview → freeze → zoom → local photo reading; file picker/drop alternative; visible background reading status and camera cleanup.
- ✅ Research and interaction rationale in `docs/AMBULANCE_WORKSPACE.md`; field simulation, real-device rehearsal, streaming STT/diarization and durable capture remain open. Browser screenshot checks blocked by browser download timeout.
- ✅ Cabin checkpoint: 117 backend tests, 44 frontend tests, production build, theme-token contrast and whitespace checks pass; updated bundle and AudioWorklet served on port 8101. No claim of hardware or clinical validation.

- ✅ Persistent voice/typed/photo capture and vocabulary-driven manual entry in the modern UI; release/permission race and keyboard interaction regressions covered.
- ✅ Workflow navigation, screen-local phases, explicit identity incompleteness, contextual score tiles, timestamped vitals, and clearer verification/change/gap sections.
- ✅ Atomic validated fact correction with retained evidence, audit trace, stale-edit conflicts and explicit confirmation.
- ✅ Nonblocking disconnected state with last-received data and writes paused; receiving-system delivery distinguished from clinician acknowledgment.
- ✅ Confirmed-fact handoff draft with unresolved fields, text download and collapsed packet diagnostics.
- 🔄 Full lifecycle, durable offline persistence, receiver human acknowledgment, administration-event schema, integration and real medic validation remain open. See `docs/MEDIC_UX_IMPLEMENTATION.md` for boundaries and verification limitations.

## S9 agentic capture — Tushar, `feat/agentic-capture`

| Scope | Status |
|---|---|
| Backend package, policy/gate/buffer/scheduler, RxNorm label verification, redacted used-frame storage | Implemented; fake-only regression tests |
| API and UX_PLAN §5 contract, continuous browser camera + monitor ROI, NOW controls/trace/mismatch review | Implemented; automated UI tests; physical camera/ROI sign-off pending |
| Synthetic timed replay and CPU-only integration rehearsal | Implemented; see [AGENTIC_CAPTURE.md](docs/AGENTIC_CAPTURE.md) |
| Real-model acceptance, three-run timing/accuracy checks and 30-minute soak | Pending explicit Rajeev confirmation that `herald-f` is serving; no GPU/model loads authorized yet |
| Delivery | PR to main requested Friday afternoon; S9 deadline Fri 11 PM PDT per handoff (supersedes the older board deadline for this task only) |

## Checkpoint: Thu 2026-09-24, 18:00 UTC (11:00 PDT) (verified: every line below checked against the repo and the live server)
**Scope (team lead, 2026-09-24): a copilot for every EMS call, not a stroke tool.** Stroke stays the demo story.

**Live on port 8100** (`/api/health`, `zrt status`):
- **speech → facts: `ems-e-v2-fp8`** (run E v2: every call type, and the call's dispatch as context);
- **photos, flowcharts, protocol ranking: `qwen3vl-fp8`** (Qwen3-VL-30B-A3B-Instruct, Apache-2.0; replaced Nemotron-Omni after a level bake-off, MODEL_PLAN §2a);
- speech → text: Whisper large-v3-turbo; search embeddings: bge-base;
- drug coding: RxNorm release 2026-09-08 (PR #1);
- protocol lookup: **32 current Santa Clara documents, 1,804 passages**, 7 figure pages read, destination audit OK;
- still loaded: `ems-d-fp8` (run D, rollback); Omni and run C are cached, not loaded.
- **Tests: 366 pass** (`python -m pytest -q`).

**Held-out results** (3 runs; MODEL_PLAN §0h, §0i, §2a, §0j):
- extraction F1 on gold v2: rules 0.444 · Omni 0.661 · run C 0.871→0.885 (grounding fix) · run D 0.916 · **run E v2 0.948–0.952** (+0.032 over run D, 95% CI [+0.013, +0.053]);
- G.F.A.S.T. F1: run D 0.923 → **run E v2 0.961**;
- every call type (gold v3, 100 utterances, two blind annotators): **F1 0.92**; new fact types **0.84**: medications given 0.91, pain 0.90, EtCO2 0.90, trauma mechanism 0.89, GCS total 0.87, trauma injuries 0.79, procedures 0.76. **Weak: trauma criteria 0.28 (recall 0.19) and suspected infection 0.20 (recall 0.11)** (see "Open risks");
- dispatch context (gold_ctx, 60): F1 0.918, G.F.A.S.T. 0.896; no stroke facts wrongly given on other-dispatch lines;
- auto-confirm at 0.8: 173 of 327 held-out medic facts confirm themselves, **1 wrong** (a role; run D: 5);
- adversarial (as ingested): 19/25 seen, 24/40 unseen; the three new failures are held for a tap in the app;
- latency p50 / p95: 1.1–1.5 / 2.4–3.1 s on held-out; longer lines with many facts about 2.5 / 3.5 s;
- vision (45 synthetic photos): Qwen3-VL F1 0.989, 43/45 exact; Omni 0.978, 42/45. Protocol ranking (22 questions): right passage first 17 vs 13.
- drug names (held-out, run D predictions): precision 0.933 → 0.956 and recall 0.850 → 0.871 with coding (MODEL_PLAN §0j).

**Done since the last checkpoint** (all merged to `main`):
- model-only speech extraction (no regex rules), 503 when the model is down, `llm_available` / `vision_available`;
- per-fact confidence from token probabilities; auto-confirm at 0.8; held facts always wait for a tap;
- **run D** (spoken fact order, speaker line) and **run E v2** (every call type + dispatch; 49 fact types): trained, measured, live;
- vocabulary: records for **medications given** and **procedures done**, pain, GCS eye/verbal/total, EtCO2, pregnancy weeks, trauma mechanism / injuries / criteria, suspected infection, 12-lead reads STEMI / transmitted; the snapshot lists every event (`events`);
- **county alerts:** Santa Clara Policy 605 trauma criteria, 700-A04 sepsis pre-notification, STEMI checklist (12-lead reads STEMI, transmitted, aspirin time), each item cited;
- **27 more county protocols** archived with sources and checksums, all indexed (sections checked against a CPU-built key); 59 protocol questions;
- **vision bake-off** and the switch to Qwen3-VL; photo prompts store generic drug names and "DNR" / "full code";
- **gold sets:** v3 (every call type, 0.993 agreement), gold_ctx (dispatch, 1.000), new-key labels on v1/v2 (0.986 / 0.993);
- **PR #1 merged** (RxNorm drug coding, Shivani); **PR #2 merged** (field robustness kit, Jenil);
- local models load from disk only (no network at startup; 0 outbound connections checked); the live test found and fixed 5 bugs (MODEL_PLAN §0g);
- a speaker on someone else's mic gets the role their words imply (neighbor → bystander, staff → family; Jenil's request).

**Demo scenario** (`scenarios/stroke_demo.json`, replayed on run E v2): every stroke-alert item is extracted, "Onset was witnessed" included. Last known well, onset and deficits come in below the confidence bar, so the script has a second tap step: **Stroke alert 6/6**, NEWS2 5, RACE 6, G.F.A.S.T. 4 of 4, allergy contradiction. **Jenil: re-rehearse with this version** (two tap steps).

**Open risks (in order):**
1. **The new UI is not on GitHub.** No branch from Collaborator 1 (C1.x) exists; `main` has only the classic `web/` screens. Feature freeze is Fri 11:00.
2. **Nothing is measured on real voices or real photos yet.** The field kit is merged (C4.9); it needs ≥5 consenting people. Props and real photos (C4.1, C4.2) are not done.
3. **Weak new fact types:** trauma criteria (recall 0.19) and suspected infection (0.11). The trauma alert still fires from vitals (computed), but injury-pattern criteria are mostly missed. The fix is training data (a run F), not code.
4. **Latency** is above the 2 s p95 target on long multi-fact lines (about 3.5 s).
5. **Adversarial:** three regressions with run E v2 (two injected "DNR"s, a bystander's "give her 325 aspirin" recorded as given). All are held for a tap in the app.

**Decisions:**
1. ✅ Guard: the model reads everything; flagged utterances wait for a tap (Rajeev).
2. ✅ No regex rules; the model is the only extractor; auto-confirm at 0.8 (Rajeev).
3. ✅ Scope: every call type; trauma, sepsis and STEMI county alerts (Rajeev, 2026-09-24).
4. ✅ Vision: Qwen3-VL replaces Omni (Rajeev, after the level bake-off).
5. ✅ Run E v2 replaces run D live (Rajeev).
6. ⏳ County PDFs no archive holds: download by hand into `data/protocols/santa_clara/` (700-A02, A05, A07, A11, P05, S02, S15; AO 2025-006 and 2025-007, which amend Policy 602 and Table B). Links: `docs/research/county_protocols_2026-09.md` §4.
7. ⏳ For Collaborator 2's specs: accept the pyannote terms on Hugging Face (S4) and `sudo apt install espeak-ng` (S3).
8. ⏳ The 2025/2026 "policy changes" memos are not indexed (they state old rules as "changed X to Y"). Index them only if we want "what changed this year" answers.

## Earlier checkpoint: Thu 2026-09-24, 00:50 UTC (Wed 17:50 PDT)
**Live on port 8100:**
- `ems-c-fp8` (fine-tuned extractor) for speech and `omni` for photos, with protocol lookup ready (371 sections, destination audit OK).
- County config Santa Clara: G.F.A.S.T. beside RACE, routing rule quoted from 700-A13.
- Tests: 97 pass.

**Held-out results (gold v2, 3 runs):**
- extraction F1: rules 0.444 · Omni 0.661 · rules + Omni 0.693 · run B 0.861 · **run C FP8 0.871**;
- G.F.A.S.T. F1 **0.789** (precision 0.90);
- p50 about 1.0 s;
- unseen adversarial attacks: run C alone 25/40 (best).

Everything is in `docs/MODEL_PLAN.md` §0e, §0f and §5.

**Done since the last checkpoint:**
- modular restructure (AGENTS rule 4);
- clinical citations verified against publishers (RACE evidence corrected);
- county config with G.F.A.S.T.;
- plausibility validation;
- FP8 serving;
- run C with G.F.A.S.T.;
- protocol lookup with online sync (real two-version demo);
- the lanes rebalanced into full-stack slices with complete specs (`docs/TASK_SPECS.md`);
- README rewritten for judges;
- model card on the private HF repo.

**Demo scenario updated for Santa Clara** (`scenarios/stroke_demo.json`; **Collaborator 4, re-rehearse with this version**):
- The exam line now states the speech finding.
- A `confirm` step taps the four G.F.A.S.T. items.
- The destination is Regional, a Comprehensive Stroke Center in Table B.
- Replayed end to end on the live models: stroke alert 6/6, G.F.A.S.T. 4 of 4 with the county routing rule quoted, RACE 6, NEWS2 2 → 5, and the allergy contradiction.

**Decisions at that time** (all settled or carried into the checkpoint above):
1. ✅ **DECIDED (Rajeev, 2026-09-24): the model reads everything, and anything from a flagged utterance waits for the medic's tap.**
   - `HERALD_GUARD_POLICY=unconfirm` is now the default.
   - Each held fact carries `provenance.hold_reason`, e.g. *said together with a command to the system ("mark her as"): check before confirming*, and it must be clearly visible on screen (C2.2).
2. ✅ **DECIDED (Rajeev, 2026-09-23): no regex rules in the product; the model is the only extractor.** "If the model is down, the whole app is down; we cannot compromise quality." The rules extractor lives only in `eval/baselines/` as a baseline. If the extraction model isn't served, `POST /api/transcript` and `/api/audio` return 503, the words are kept, and `/api/health` shows `llm_available: false`.
   - ✅ **DECIDED (Rajeev): auto-confirm by the model's own confidence, threshold 0.8** (`config/confirmation.yaml`). Held-out: 134 of 320 medic facts confirm themselves, 3 wrong, none a clinically wrong value. Other speakers, photos, code status, contradictions, and guard-held facts always need a tap.
   - Two alternative confidence measures were tested and rejected on held-out data (MODEL_PLAN §0g): they let clinically wrong facts through (empagliflozin as an anticoagulant).
3. **County PDFs.** Download the current versions into `data/protocols/santa_clara/` (links in chat). Protocol lookup works on archived copies until then.
4. **For Collaborator 2's specs:** accept the pyannote model terms on Hugging Face (S4) and `sudo apt install espeak-ng` (S3).

## Earlier checkpoint: Wed 2026-09-23, 22:15 UTC
**Since 20:15**
- ✅ **Held-out gold v1 (100 items)**: two independent annotators, fact F1 0.993 before adjudication; 3 disagreements settled and written into `docs/LABELING_GUIDE.md` §3/§4/§4b.
- ✅ **Scorer v2** (atomic facts: per list item, unioned list facts, normalized time phrasing), unit-tested. Effect on saved predictions: ±0.01.
- ✅ **Frozen extractors on gold v1, 3 runs each:** rules **0.571** · Omni **0.672** (spread 0.012) · rules + Omni **0.729** (spread 0.019). The v0 numbers (0.917 / 0.860 / 0.964) were optimistic, as warned: the drop is genuine (audited), not the scorer or the labels. Details and the error taxonomy are in `docs/MODEL_PLAN.md` §5. **gold v1 is now a dev set; gold v2 (fresh, same protocol) is the held-out set.**
- ✅ **Direction from the team lead: no hardcoding.** Extraction errors are fixed through the model (training data, general instructions), never with lookup tables or phrase regexes.
- ✅ **Fine-tune run A** (Qwen3-4B-Instruct-2507, LoRA r16, 2 epochs, 3,000 composed rows): eval loss 0.756 → 0.021 on the synthetic split (in-distribution only). Adapter at private `rajeev-chaurasia/herald-extractor-lora`; merged model at private `rajeev-chaurasia/herald-extractor-lora-merged-a`, served by ZRT as `ems` (15% memory). Go/no-go 4 passed: outputs differ from base, JSON parses. Gold v1 numbers: see M2.
- ✅ **Backend asks from `docs/UX_PLAN.md`, all done:** WebSocket ping → pong on both `/ws`; `GET /api/meta` + `scripts/export_ui_contract.py` (keys, relay tiers, change rules, checklists); `scripts/record_ws.py`; `trace.heard.stt.ms`; failed-photo trace entry; monitor-panel trace entries (and `POST /api/facts` is all-or-nothing); ED `last_contact_at`; `/classic/` mount with the React build at `/` when present. 77 tests pass.

**Done before 20:15**
- ✅ **Engine + tests:** 56 tests pass (77 now). Every NEWS2/RACE/field-triage band boundary; the stroke demo flow; contradictions; confirmed-only scoring; relay reconciliation over a link that loses 50% of requests/ACKs (20 seeds): 0 duplicates, 0 lost.
- ✅ **Stroke demo end to end** (`scripts/replay.py`): alert 0/6 → 6/6, RACE 6, NEWS2 2 → 5, contradiction, clocks.
- ✅ **Relay on emulated links** (Toxiproxy): weak → critical-first packets ≤ 420 B with retries; offline → queued; restored → probe detects recovery, full sync (31 entries), 0 duplicates, ~99.8% kept local.
- ✅ **Speech:** Whisper large-v3-turbo on the GPU; 10.4 s clip round-trip 0.47 s.
- ✅ **Local model serving:** `omni` (Nemotron-3-Nano-Omni-30B-A3B NVFP4) on `127.0.0.1:8080`. First start took 23 min (kernel compile; cached now).
- ✅ **Photo reading (synthetic images):** pill bottle → warfarin 3/3 (1.1 s warm); pulse oximeter → SpO2 94 / HR 104 3/3 (1.5 s). Range checks added. **Real prop photos not tested yet (P5.4).**
- ✅ **Extraction bake-off, audited** (3 runs each, `docs/MODEL_PLAN.md` §5):

  | Extractor | Mean F1 | Spread |
  |---|---|---|
  | Rules | 0.903 | deterministic |
  | Omni alone | 0.825 | 0.05 |
  | Rules + Omni | 0.897 | 0.02 |

  - The model raises recall (0.96–0.97) but adds false facts, so model-only facts now arrive unconfirmed.
  - On 30 utterances the difference from rules is within noise. **We need a bigger gold set (M4) before claiming the model helps.**
  - Fixed along the way: a scoring flaw (free text scored by exact string), a gold label inconsistency, and runaway JSON (unbounded value types).
- ✅ **Infra:** code on GitHub (`projects-hacks/herald-ems`, first commit on `main`); collaborators added; per-person git setup script; `python3.12-dev` installed; HF token in the shared secrets file; private repo `rajeev-chaurasia/herald-extractor-lora` created.

**Open decisions / risks**
- Is the text model worth it? Run Nemotron-3-Nano-30B-A3B (text-only) through the same bake-off once the gold set is ~100 items (M2/M4).
- One gold utterance (g01) makes Omni run to the token cap (~4 s) every time. Now bounded at 160 tokens; root cause not yet known.
- UI/UX plan: research running → `docs/UX_PLAN.md`, then U-tasks below.

## Who does what: per-person lanes (assigned Wed 2026-09-23)

**How to claim a lane:**
- Replace "Collaborator N" below with your GitHub handle, and add yourself to `CONTRIBUTING.md` §5.
- Work in your own clone, `~/work/<handle>/herald-ems`, on a branch `feat/<lane>-<topic>`. Run `scripts/dev_git_setup.sh` first: your agent must check your git identity (AGENTS.md hard rule 2).
- Read `AGENTS.md` first (all hard rules, including rule 4: modular, no hardcoded content), then the docs listed for your lane.
- Update the status here in the same PR as the work.

**Ground rules:**
- **Lanes are feature slices, not frontend vs backend** (team lead, Wed 2026-09-23). Each owner builds the backend, the UI, and the tests for their features. Handed-off backend work has a complete spec in [`docs/TASK_SPECS.md`](docs/TASK_SPECS.md) (S1–S8): goal, files, design, steps, tests, acceptance, pitfalls.
- **Backend work follows AGENTS.md hard rule 4:** the right package, interfaces in `herald/core/ports.py`, wiring in `herald/api/context.py`, content in `config/`, tests with `tests/fakes.py`.
- **Anything touching `herald/` is a PR reviewed by Rajeev.** Never restart the shared models (`qwen3vl-fp8`, `ems-e-v2-fp8`, `ems-d-fp8`; check `zrt status`), and never let pip replace torch in the `zgx` env (TASK_SPECS rule 6).
- **UI work builds against the API contract:** `GET /api/meta`, `/ws`, the snapshot shape in `docs/UX_PLAN.md` §4–5, and the fixtures in `ui/public/fixtures/`.
- **Everything is built; nothing is cut.** If a lane runs late, others join it (build order: UX_PLAN §7.1).
- **Feature freeze: Fri 11:00. Submission target: Fri 18:00** (hard deadline 20:00).
- **If there are only three collaborators,** Collaborator 3 takes Collaborator 4's lane from phase C, as UX_PLAN §7.2 plans.

**New in the contract since UX_PLAN was written** (all live on port 8100, all tested):
- **G.F.A.S.T. and RACE side by side:**
  - `scores.gfast` and `scores.race`, plus `scores.stroke_scales` and `scores.primary_stroke_scale`.
  - A `gfast_positive` alert carries `county_rule`, the county's routing text quoted from Protocol 700-A13.
  - The stroke checklist item for the scale is `@gfast` in Santa Clara and `@race` elsewhere.
- **County:**
  - `snapshot.county` holds `{id, name}`.
  - `GET /api/county` returns the full config; `POST /api/county/{id}` switches live (`santa_clara`, `generic`).
- **Rejected facts:** `trace.rules.rejected[]` and `trace.model.rejected[]` list facts refused as physically impossible, e.g. "sats 400".
- **Protocol lookup** (`herald/knowledge/`):
  - `GET /api/protocols` returns status, document versions and effective dates, `review_required`, and the destination audit.
  - `GET /api/protocols/search?q=` returns the county's passages with document, section, page, effective date and `answerable`.
  - `GET /api/protocols/{doc}/page/{n}` returns the page image (PNG).
  - `POST /api/protocols/sync` runs a sync now; `POST /api/protocols/{doc}/reviewed` clears a review flag.
  - The snapshot has a `protocols` block (`ready`, `review_required`, `destination_audit_ok`, documents).
- **G.F.A.S.T. from speech:** the live model (`ems-e-v2-fp8`) extracts `exam.gfast.*`. Items below the confidence bar arrive unconfirmed; the medic's taps complete the screen.
- **Drug coding (RxNorm, S6; merged with PR #1; live on 8100 since 2026-09-24, index release 2026-09-08):** drug values of `meds.list`, `meds.anticoagulant`, `allergies` and `meds.given.drug` are RxNorm ingredient names; every fact has `code` (a `Coding {system, code}`: RxNorm, or ICD-10-CM Z88.x for a class allergy such as "sulfa"; a list per item for list keys; `null` = not coded) and `provenance.normalized[]` (as said → coded, with the method). A drug matched only by spelling, sound, as a combination or from product words waits for a tap with `provenance.hold_reason` (C2.2 shows it). Trace facts carry `code`; `GET /api/health` has `terminology.rxnorm_release`. UX_PLAN §5.9d.
- **Every call type (run E v2, 2026-09-24):**
  - new keys in `config/vocabulary.yaml`: `meds.given` and `procedures.done` are **records** (a JSON object per event: drug, dose, unit, route, time, by, count; procedure, time, detail, by), plus `vitals.pain`, `vitals.gcs_eye/verbal/total`, `vitals.etco2`, `patient.pregnancy_weeks`, `trauma.mechanism`, `trauma.injuries`, `trauma.criteria` (a controlled list), `infection.suspected`, `ecg.stemi_reading`, `ecg.transmitted`;
  - the snapshot's **`events`** lists every medication given and procedure done in order (`facts` keeps the latest per key);
  - the incident's dispatch is passed to the model (`POST /api/incident {dispatch}`).
- **County alerts:** `scores.trauma_605` (Policy 605 red/yellow criteria with letters and citations; major burn shown separately) and `scores.sepsis_700a04` (the county's "sepsis pre-notification"); Santa Clara checklists for **trauma, sepsis and STEMI** (items cite their source; record items like `meds.given[drug=aspirin]`); `GET /api/meta` `scores.json` and `checklists.json`. UX_PLAN §5.9c.
- **Model availability:** `GET /api/health` has `llm_available` and `vision_available`; with no extraction model, `POST /api/transcript` / `/api/audio` return 503 and keep the words.
- **Held facts:** `provenance.hold_reason` (guard, and non-exact drug matches) always waits for a tap.
- **Also already live:** WebSocket ping → pong, `GET /api/meta`, `trace.heard.stt.ms`, the failed-photo and monitor-panel trace entries, ED `last_contact_at`, and `/classic/`.

### Rajeev Chaurasia (@rajeev-chaurasia): lead + backend, models, eval, infra (claimed)
Docs: `docs/MODEL_PLAN.md`, `docs/LABELING_GUIDE.md`, `eval/`.

| # | Task | Status | Done when |
|---|---|---|---|
| B1 | Final held-out numbers on gold v2 for every extractor (rules, Omni p3, fine-tuned run B; alone and with rules), 3 runs, contamination check | ✅ Rajeev: final 3-run table in MODEL_PLAN §5 (rules 0.444 · Omni 0.661 · rules + Omni 0.693 · **run B 0.861** · rules + run B 0.854) | table in MODEL_PLAN §5; the deck uses only these |
| B2 | Modular restructure (AGENTS rule 4): packages by responsibility, interfaces, all clinical content in `config/` | ✅ Rajeev: merged to `main`, 90 tests pass, smoke-tested live | merged; live app on 8100 runs it |
| B3 | Grounded extraction: each model fact carries its transcript quote + assertion (present/absent/uncertain) + subject; the deterministic quote check drops ungrounded facts (research: Abridge/Nabla/Corti pattern) | 🔄 Rajeev: numbers are grounded (a vital, dose or ETA must be a number that was said, in digits or words: `herald/extraction/numbers.py`; held-out F1 +0.014 from grounding fixes). Quote spans per fact not done | precision up on gold v2 with no recall loss beyond the spread |
| B4 | Medication normalization with RxNorm | ➡️ moved to Collaborator 3 (C3.7, spec S6); ✅ PR #1 (review fixes by Rajeev) | brand names and ASR misspellings map to generics on gold v2 |
| B5 | G.F.A.S.T. extraction: labeling-guide rules, annotated training data, run C fine-tune, gold G.F.A.S.T. labels (two annotators) | ✅ Rajeev: labeling rules (§4d), gold G.F.A.S.T. labels (two annotators, 99–100% identical), training data, **run C: held-out G.F.A.S.T. F1 0.789 (P 0.90), main F1 0.871**; was live as `ems-c-fp8` (now run E v2, B11) | G.F.A.S.T. items extracted from speech; measured |
| B6 | Latency: fine-tuned model p95 ≤ 2 s (FP8 serving or the 1.7B run B) | ⚠️ Rajeev: FP8 halved latency (run C p95 2.24 s). **Run E v2 misses the target**: held-out p50 1.1–1.5 s, p95 2.4–3.1 s; long multi-fact lines about 2.5 / 3.5 s (it writes more facts). Options: the 1.7B base for run F, or shorter outputs | p50/p95 measured 3× |
| B7 | P9 protocol lookup + online sync (document-parser bake-off on the county PDFs, local index, cited sections, version on screen, review flag on update) | 🔄 Rajeev: `herald/knowledge/` built and tested: Table B 168/168 from the text layer, flowchart read by the local vision model, hybrid search + model reranking (top-1 14/22, top-3 19/22, refusals 2/3 on the first 25 questions), sync on good link with review flags, destination audit. **2026-09-24: 32 documents indexed** (the 27 new current files incl. Policy 605, sepsis, trauma, shock, chest pain, overdose, falls, hemorrhage, pediatrics, 302/410/420/430/500; 1,804 passages): numbered sections 1,746/1,746 against the CPU answer key with none extra, every effective date read from its file, 8 figure pages configured; qa_gold 59 questions; retrieval without the reranker (hybrid, 52 answerable, deterministic): top-1 26, top-3 37, in the reranker's 8: 43 (`eval/bench_protocols.py`, `eval/protocols/README.md` §5). Live on 8100 since 2026-09-24 with Qwen3-VL (7 new figures read, no errors). Pending: 700-A02/A05/A07/A11, AO 2025-006/007 and other files no archive holds (Rajeev downloads), rerank bench on the 59 questions, UI panel, demo mirror | "open the stroke protocol" shows 700-A13 §3.2 with its effective date |
| B8 | Field robustness eval (real people, own words, noise) | ➡️ moved to Jenil (C4.9, spec S8) | per-key precision/recall with confidence intervals |
| B9 | UI fixtures | ➡️ moved to Collaborator 1 (C1.5, spec S1) | the frontend can build every state without the Nano |
| B11 | **Every call type + dispatch (run E):** new keys, labeling rules (§4c dispatch rule, §4e, §5b), 780 + 750 annotated lines from independent annotators, gold v3 / gold_ctx / new-key labels (two blind annotators each), run E v1 → dispatch-assignment flaw found on dev → run E v2 | ✅ Rajeev: **live as `ems-e-v2-fp8`**: held-out F1 0.950 (+0.032, significant), G.F.A.S.T. 0.961, every-call F1 0.92, new keys 0.84; weak: trauma criteria, suspected infection (MODEL_PLAN §0i) | measured on dev, held-out, v3, gold_ctx; 3 runs; bootstrap |
| B12 | **Vision bake-off** (level: both official FP8, same serving and prompts): Nemotron-Omni vs Qwen3-VL-30B-A3B on 45 synthetic photos, the flowchart, protocol ranking | ✅ Rajeev: Qwen3-VL ≥ Omni everywhere, better ranking (17 vs 13 of 22 first); Apache-2.0; **live as `qwen3vl-fp8`** (MODEL_PLAN §2a) | decision logged |
| B13 | **County trauma, sepsis and STEMI alerts** (Policy 605, 700-A04, 700-A08/M09/501/602): criteria scores and checklists as config, every item cited | ✅ Rajeev (reviewed subagent work): `config/scores/trauma_605.yaml`, `sepsis_700a04.yaml`, `santa_clara.json` `alerts`; 264 → 366 tests | a rollover with SBP 84 at 70 flags red N.3 and yellow O/U; a UTI with fever, HR 112, RR 24 meets the sepsis rule |
| B14 | **Live end-to-end test on the real models** (not only unit tests) | ✅ Rajeev: found and fixed model-availability, speaker-attribution, hub-at-startup, number-grounding and snapshot-events bugs (MODEL_PLAN §0g) | the pitch scenario replays on the live stack |
| B10 | P11, P8, M8, M5, I2 | ➡️ moved: P8 + M8 → Collaborator 2 (S3, S4); P11 + M5 → Collaborator 3 (S5, S7); I2 → Collaborator 1 (S2). Rajeev reviews their `herald/` PRs | see the rows below |

### Tushar Singh (@tushar-fs): NOW screen, trace, fixtures, clean-clone setup (claimed; was Collaborator 1)
**Merged to `main` on 2026-09-24** (Tushar's work as his commit; contract updates by Rajeev on top: records such as medications given read as text, the model chip uses `llm_available` with no "rules only", the trace shows the model step or monitor readings, and the pre-alert card switches between open checklists; 25 vitest tests incl. a live every-call snapshot). **Still to do in this lane:** show `events` (every dose and procedure) as a timeline, tiles for `scores.trauma_605` / `scores.sepsis_700a04`, the model-not-running state (UX_PLAN §3.1.14), and the fixtures C1.5 lists.
Docs: `docs/UX_PLAN.md` §1–2 (principles, tokens), §3.1 (NOW screen), §4 (trace), §5.7–5.8 (store, fixtures), §5.10 (build and serving).

| # | Task | Hours | Needs | Done when |
|---|---|---|---|---|
| C1.1 | 🔄 `feat/c1-now-screen`: toolchain pinned per §5.3, tokens for both themes, `npm run contrast` passes (ratios match §2.2), build served at `/`; **left:** the `/?tokens` preview and grayscale screenshots. **U1:** toolchain (React + TS + Vite + Tailwind + shadcn/ui) and design tokens | 2 | — | `npm run build` produces `ui/dist`, served at `/` (UX_PLAN U1 checklist) |
| C1.2 | 🔄 `feat/c1-now-screen`: store, heartbeat, stale detection, backoff, fixture player with replay controls; 21 vitest tests; **left:** the live stop-the-server check. **U2 frontend:** WebSocket store with heartbeat and stale detection, and a fixture player (`?fixture=…&speed=…`) with the REPLAY banner | 1.5 | C1.1 | stale scrim within 3 s of stopping the server; fixtures replay |
| C1.3 | 🔄 `feat/c1-now-screen`: dashboard layout (sidebar with Overview / Patient / Vitals & trends / ED handoff / Transcript, top bar, KPI row), one Needs-attention queue replacing the alert slot (UX_PLAN §2 note), pre-alert card with ED sync, scores (G.F.A.S.T. first in Santa Clara), medic/explain/narrow layouts, S0/S1/S6/S9/S10; **left:** second-checklist popover, county-policy sheet, keyboard-order audit, the non-team viewer test. **U3:** NOW screen layout and states S0–S10, including **G.F.A.S.T. and RACE side by side** (primary scale first, the county name shown, `county_rule` on the `gfast_positive` alert) | 5 | C1.2 | a non-team viewer says "a checklist filling up"; U3 checklist |
| C1.5 | 🔄 `stroke_demo` recorded (ems-c-fp8, relay authorized, 44 messages, ends 6/6 READY); four to go. **UI fixtures (B9)**: record `stroke_demo`, `rules_only`, `model_error`, `photo`, `offline` → `ui/public/fixtures/`. **Spec S1** | 1 | — | all five replay in the fixture player |
| C1.6 | **Clean-clone setup (I2)**: `scripts/setup.sh` + README section; the Nano is wiped after the event. **Spec S2** | 2 | — | clean clone → tests pass → server runs |
| C1.4 | **U6:** "Herald thinking" trace panel: every card state a–j, effects, the explain-mode stage line, and `rejected[]` as "Not recorded: … (implausible)" | 4 | C1.3 | T1–T10 in UX_PLAN §4.12 pass |

### Collaborator 2: capture, trust, interpreter, diarization
Docs: `docs/UX_PLAN.md` §3.1.11 (capture bar), §3.1.13 (hotkeys), §3.2–3.3, §4.9 (audio/photo evidence), U4/U10/U13/U14.

| # | Task | Hours | Needs | Done when |
|---|---|---|---|---|
| C2.1 | **U4:** push-to-talk (Space = medic, F = other speaker), typed input, and the monitor-panel fallback (`POST /api/facts`) | 2 | C1.1, C1.2 | a clip round-trips; the monitor entry shows in the trace |
| C2.2 | **U13:** confirm/reject and the contradiction card, with both sources and ▶ audio. **Held facts** (`provenance.hold_reason` set, i.e. said together with a command to the system) get a distinct "held · check" badge in both the Patient picture and the trace. The reason is shown in words, and confirming one shows the reason again at the moment of the tap | 2 | C1.3 | one tap per confirm; the contradiction clears on confirm; a held fact is unmistakable at arm's length |
| C2.3 | **U10:** link UX and reconciliation on both screens: queued / sent / "reconciled · 0 duplicates · 0 lost" (P3.2) | 2 | C1.3, C3.2 | the counter appears on both screens after restore |
| C2.5 | **Interpreter (P8)**: Spanish ↔ English end to end: translator + language detection + Kokoro TTS + endpoints + interpreter panel + 20-utterance eval. **Spec S3** (needs Rajeev: `sudo apt install espeak-ng`) | 5 | C2.1 | a Spanish sentence becomes unconfirmed English facts with the original kept; English is spoken back in Spanish |
| C2.6 | **Speaker diarization evaluation (M8)**: pyannote community-1 on 10 two-speaker clips; DER + word attribution; go/no-go. **Spec S4** (needs Rajeev: accept the model's terms on Hugging Face) | 2 | — | numbers in MODEL_PLAN §3 |
| C2.4 | **U14 UI:** the judge beat (daughter on the F mic; "Mom's allergic to aspirin" becomes a contradiction) | 1 | C2.1, C2.2 | rehearsed with a stranger (with Collaborator 4) |

### Collaborator 3: ED screen, presenter, multi-patient mode, medication coding, soak test
Docs: `docs/UX_PLAN.md` §3.4 (ED screen), §3.5 (presenter), §3.6 (phone capture), §5.9 (telemetry contract), U8/U9/U12/U15.

| # | Task | Hours | Needs | Done when |
|---|---|---|---|---|
| C3.1 | **U8:** presenter controls: link Good / Weak / Down (`/api/netem/{mode}`), new incident, **county switch** (`POST /api/county/{id}`, P12: the checklist and stroke scale change on screen) | 1.5 | C1.3 | Shift+G/W/D and the county switch work live |
| C3.2 | **U9:** ED screen (`ed.html` → `ed_receiver/web/`): "INCOMING STROKE ALERT", LKW clock, anticoagulant in red, bytes per packet, `last_contact_at` (P2.5) | 3 | C1.1, C1.2 | readable from 3 m |
| C3.3 | **U12:** phone capture page restyle (`ui/public/capture.html`) | 1 | C1.1 | photo → facts on the NOW screen; the failed-photo state shown |
| C3.4 | **U15 strip:** telemetry strip (tokens/s, GPU W, Wh, $ vs cloud with the stated rates and sources, cloud AI calls 0) | 1.5 | C1.3 | the UX_PLAN §5.9 contract rendered; honest labels |
| C3.5 | **P4.3:** show field-triage criteria only on trauma or fall dispatches | 0.5 | C1.3 | hidden on stroke |
| C3.6 | **Mass-casualty mode (P11)**: patient roster, `triage.category`, relay across patients by triage rank, patient strip + ED list. **Spec S5**. 🔄 Vineet (`feat/p11-mass-casualty`): backend, ED list, replay and standalone NOW strip implemented; 411 backend tests + 27 UI tests pass; no-model live replay on :8103/:8203 sent immediate before minimal. Pending: Tushar places the strip and the 3-run `herald-f` voice check after the model is available | 5 | C3.2 | two patients on a weak link: the immediate one's update goes first |
| C3.7 | ✅ PR #1 (Shivani; review fixes by Rajeev) **Medication normalization with RxNorm (B4)**: pinned RxNorm release + RxNav brand supplement (Coumadin, Zofran, Vicodin), exact → product name → combination → contained / fuzzy → phonetic, class allergies → ICD-10-CM (NEMSIS), `Coding` on facts, non-exact matches held for a tap, classes and drug keys in config. **Spec S6**. Held-out gold v2 drug keys, live run D: P 0.933 → 0.956, R 0.850 → 0.871 (F1 0.890 → 0.911); Omni F1 0.484 → 0.875; 200 atoms fixed, 0 lost across 42 saved runs; auto-confirm unchanged (MODEL_PLAN §0j). ✅ merged; index built and live on 8100 (release 2026-09-08) | 3.5 | — | med/allergy recall up on gold v2 with no precision loss beyond the spread |
| C3.8 | **30-minute soak test + pre-demo runbook (M5)**: `scripts/soak.py`, backend check, `docs/RUNBOOK.md`. **Spec S7** | 1 | — | 🔄 Vineet: harness + runbook done; 30.1 min / 1,413 model calls / 0 errors / stable memory, but latency window invalidated by concurrent model download + vision benchmark. Exclusive-GPU rerun pending |

### Jenil Savalia (@Jenil133): pitch, field evaluation, and deliverables (claimed)
Docs: the product spec on the Nano (`/home/hp18/Documents/team-last-minute/.agent/ideas/herald-ems-copilot.md` §10–§14), `.agent/context.md` (judging criteria), `docs/UX_PLAN.md` U11/U14/U16/U17.

| # | Task | Hours | Needs | Done when |
|---|---|---|---|---|
| C4.1 | **Props (P5.3):** fingertip pulse oximeter; empty pill bottle with a printed "WARFARIN 5 MG" label; a printed CA POLST | 1 | — | bought or printed |
| C4.2 | **Real photo test set (P5.4):** ~50 phone photos of the props (angles, glare, low light), with the value in each photo written down (backend scores them) | 1.5 | C4.1 | the photo-reading accuracy number for the deck |
| C4.3 | **Second machine (P2.3):** run `ed_receiver` on a teammate laptop on a hotspot; Nano → Toxiproxy :9000 → laptop:8200 | 1 | — | two screens, two networks |
| C4.4 | **U11:** two-screen stage and the 3 m test on the real displays; OBS scene | 2 | C3.2 | readable from 3 m |
| C4.5 | **Rehearsals:** link hotkeys ×5 (P2.4), the judge beat with a stranger (P6.2, U14 script), the mic test on a real laptop (P1.5) | 2 | C2.4, C3.1 | no stumble in 3 full runs |
| C4.6 | **D4 + U16:** ask the organizers whether the overall prize depends on track (Community Impact recommended), and ask HP about registering on the ZGX console | 0.5 | — | answers recorded in `.agent/context.md` |
| C4.7 | **D1:** interactive deck: problem → solution → architecture → held-out benchmarks (B1 numbers only) → impact | 3 | B1 | reviewed by Rajeev |
| C4.9 | **Field robustness eval (B8)**: 30 fact cards, ≥5 people in their own words, quiet + road noise, ≥100 clips; scored with confidence intervals. **Spec S8**. 🔄 Jenil (`feat/c4-field-eval`): tooling done and tested: blind-written cards (`eval/field_cards_v1.jsonl`, 30 cards / 169 facts; second blind labeler agrees 30/30, F1 1.000 — an upper bound, see `eval/field/README.md`), the recording station (`python -m eval.field.recorder --station <you>`, port 8105: consent, per-station speaker codes and one shared audio folder so several teammates can record at once, counterbalanced quiet/noise blocks, withdraw & delete that is verified before it is logged; records with the app's own `web/wav.js`), `eval/field_bench.py` (Whisper → live extractor → the gold-v2 scorer; 3 runs; intervals over clips and speakers; quiet − noise resampled by speaker; omission review by listening to each clip, independent of any model's output), session guide `eval/field/README.md`. ✅ **merged to main (PR #2, 2026-09-24)**, 365 tests pass after merge. **Next: recordings with ≥5 consenting people**, then MODEL_PLAN numbers | 3 | — | numbers in MODEL_PLAN §5 and a slide |
| C4.8 | **U17 / D2:** 2-minute video (`scripts/replay.py` for the screen capture) and **D3:** socials tagging sponsors | 3 | all | uploaded, linked in the README |

### Open tasks: anyone can pick
These are in nobody's lane. To claim one, put your GitHub handle in "Claimed by", work in your own clone on `feat/<topic>`, and take it end to end in one PR: backend, model data, eval, UI, and docs. Don't split it into follow-ups.

| # | Task | Hours | Needs | Claimed by | Done when |
|---|---|---|---|---|---|
| O1 | **Medications the crew gives** (aspirin 324, nitroglycerin, naloxone, ondansetron, D10 …) as `meds.given` records, NEMSIS eMedications.03–.06. **Status:** ✅ key and labeling rules (`config/vocabulary.yaml`, LABELING_GUIDE §4e), gold v3 labels and run E training data (Rajeev); ✅ drug coding to RxNorm with holds (PR #1, MODEL_PLAN §0j: v3 `meds.given` F1 0.915 with run E, unchanged by coding). ✅ run E v2 live: `meds.given` F1 0.91 on gold v3 (P 0.95, R 0.88); the snapshot lists every dose (`events`); ⏳ screens: NOW timeline, trace and ED screen show the given drug with its code; ⏳ relay tier reason in `config/relay.yaml` (already tier 1) | 2 (screens) | run E served | — | "Gave 324 of aspirin, chewed, at 14:05" shows as aspirin (RxNorm 1191), 324 mg, PO, 14:05 on the NOW screen, the trace and the ED screen, and ticks Santa Clara's STEMI aspirin item |

**Requests to backend** (any lane adds rows; Rajeev triages):

| From | Request | Status |
|---|---|---|
| @Jenil133 | **A speaker on the other mic who is a neighbor, friend, coworker or other non-relative is recorded as `family`.** `herald/core/schema.source_role` maps any speaker label that isn't a role name to `family`, and `ModelExtractor` uses that role for every fact on someone else's mic, but LABELING_GUIDE §3 makes a neighbor a bystander. `config/vocabulary.yaml` already groups these words (`field_synonyms.by`: family / facility / bystander …), so the same groups could decide the source role. Found while writing the field cards (fc28, a neighbor on the mic, will show it) | ✅ fixed 2026-09-24: `config/vocabulary.yaml` `people` groups decide the speaker's role (`speaker_roles`: neighbor, coworker, police → bystander; facility staff → family), shared by the app and the benchmarks; test in `tests/test_trace.py` |
| @tushar-fs | `relay.status().kept_local_pct` goes negative (−57.5% in the recorded stroke replay): typed input has no audio, and every good-link full sync re-sends the whole timeline, so bytes sent exceed local bytes. The ER footer would read "−57.5% kept on the vehicle". | ✅ fixed on `feat/p11-mass-casualty`: bytes kept local is clamped to 0–100%; regression covers the recorded 25,837 / 16,403-byte replay |
| @tushar-fs | `scripts/replay.py` writes LKW_TIME in the box's clock (UTC) but the server reads clock times in `HERALD_TZ` (Pacific), so the demo's LKW clock shows about +06:04 instead of about +01:04. | ✅ fixed in PR #3: replay and soak use `HERALD_TZ` |

## P1: Speech → patient picture → NOW screen, gap-first
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P1.1 | Engine: facts, provenance, checklists, gaps, contradictions, trends, clocks | Rajeev | ✅ | tests pass |
| P1.2 | Push-to-talk (Space = medic, F = other speaker) → `/api/audio` | frontend | ✅ | works via `http://localhost:<port>` |
| P1.3 | NOW screen matches spec §5: stroke alert at top, "needs attention", scores, ER status, ▶ provenance | frontend | 🔄 | a non-team viewer says "it's a checklist filling up", not "a form" |
| P1.4 | Confirm/reject UX for unconfirmed facts; the contradiction card shows both sources with ▶ audio | frontend | ✅ basic, ⏳ polish | one tap per confirm |
| P1.5 | Mic test with a real laptop over a port forward; record and replay provenance audio | pitch+frontend | ⏳ | the judge's own voice plays back |

## P2: Relay: network cut, critical update reaches the ED screen
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P2.1 | Relay: priority tiers, byte budget, ACK/seq, retries, idle probe, full sync on a good link | Rajeev | ✅ | `tests/test_relay.py` + live run |
| P2.2 | ED receiver + screen (`ed_receiver/`) | relay/frontend | ✅ basic | shows the banner, critical fields, packets, bytes, duplicates |
| P2.3 | Run the ED receiver on a **second machine** (teammate laptop on hotspot); Nano → Toxiproxy :9000 → laptop:8200 | relay+pitch | ⏳ | two screens, two networks |
| P2.4 | Rehearse Shift+W / Shift+D / Shift+G five times; the pill shows "(emulated)" | pitch | ⏳ | no stumble |
| P2.5 | ED screen polish: big "INCOMING STROKE ALERT", LKW clock, warfarin in red, packet bytes visible | frontend | ⏳ | readable from 3 m |

## P3: Reconciliation
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P3.1 | Tests: 0 duplicates / 0 lost over a flaky link | Rajeev | ✅ | 20 seeds pass |
| P3.2 | On-screen counter after restore: "reconciled · 0 duplicates · 0 lost" | frontend | ⏳ | visible on both screens |

## P4: Published scores
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P4.1 | NEWS2 + RACE + 2021 field triage, unit-tested, sources in code/UI | Rajeev | ✅ | tests pass |
| P4.2 | Verify which stroke scale the **Santa Clara County** destination policy uses (RACE vs LAMS vs C-STAT); switch if needed | Rajeev | ✅ Santa Clara uses **G.F.A.S.T.** (Protocol 700-A13, eff. 2026-01-01; 4/4 → Comprehensive Stroke Center unless > 45 min); RACE kept beside it | policy PDF cited in the README |
| P4.3 | Show field-triage criteria only for trauma/fall dispatches | frontend | ⏳ | hidden on stroke |
| P4.4 | County criteria: Santa Clara Policy 605 trauma (red/yellow/considerations) and 700-A04 sepsis pre-notification, cited per criterion | Rajeev | ✅ (= B13) | tested scenarios in `tests/test_county_scores.py` |

## P5: Eyes (photo reading)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P5.1 | `herald/models/vision.py`, `/api/photo`, `web/capture.html`; live model `qwen3vl-fp8` (B12); prompts store generic drug names and "DNR" / "full code", and read glucometers and thermometers | ML/frontend | ✅ | — |
| P5.2 | Synthetic photo set (`eval/photos/`, 45 images, 31 degraded; `eval/vision_bench.py`) | ML | ✅ Qwen3-VL F1 0.989, 43/45 exact (a glucometer "HI" and a POLST with only section B are missed) | numbers in MODEL_PLAN §2a |
| P5.3 | Props: fingertip pulse oximeter, empty bottle with a printed "WARFARIN 5 MG" label, printed CA POLST | pitch | ⏳ | bought/printed |
| P5.4 | Photo test set: ~50 real phone photos of the props (angles, glare) + gold labels → photo-reading accuracy | data | ⏳ | number for the deck |

## P6: Judge beat (contradiction in a judge's voice)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P6.1 | Engine: other-speaker facts unconfirmed; contradiction alert with both sources | Rajeev | ✅ | test passes |
| P6.2 | Card for the judge: "Mom's allergic to aspirin"; the F-key mic with speaker label "daughter" | pitch | ⏳ | rehearsed with a stranger |

## P7–P10 (all ship; built after P1–P6 are solid)
| ID | Task | Owner | Status | Notes |
|---|---|---|---|---|
| P7 | Simulated monitor panel | frontend | ✅ | fallback for P5 |
| P8 | Interpreter (Spanish ↔ English: Whisper + LLM + Kokoro TTS), statements land in the timeline with the original kept | Collaborator 2 (S3) | ⏳ | a Spanish answer shows up translated in the chart; round-trip latency measured |
| P9 | Protocol lookup: county policy PDFs → local search, read-only, cited section shown | Rajeev | ✅ backend, 32 documents live; 🔄 UI panel, rerank bench on 59 questions (= B7) | "open the stroke protocol" shows the right county section |
| P11 | Multi-patient mass-casualty mode: several patient pictures on one rig; the relay prioritizes across patients by triage color | Collaborator 3 (S5) | 🔄 implementation and no-model live acceptance done on `feat/p11-mass-casualty`; NOW placement + `herald-f` voice check pending | two patients, the critical one's update goes first on a weak link |
| P12 | County configuration file (stroke scale, checklist items, destinations, reassessment interval); switch counties live | Rajeev (backend) + Collaborator 3 (switch UI, C3.1) | ✅ backend: `config/counties/*.json`, `POST /api/county/{id}`; UI in C3.1 | switching county changes the checklist and scale on screen |
| P10.0 | Synthetic data (`scripts/compose_synth.py`, template composition; teacher generation piloted and rejected, MODEL_PLAN §4): 3,000 rows, 2,448 / 274 / 278 | Rajeev | ✅ | labels correct by construction |
| P10.1 | Go/no-go checklist (MODEL_PLAN §4) | Rajeev | ✅ 1–4 · 🔄 5 (latency) | failures get a root cause and a fix path the same morning |
| P10.2 | Run A: Qwen3-4B-Instruct-2507 BF16 LoRA r16 on composed data ✅ (0.635 on v1: covered 19/31 keys); **run B: same base on 1,200 annotated utterances ✅ (0.903 on v1 dev, 0.860 on held-out v2)**; run C (+ G.F.A.S.T.) 0.885; run D (spoken order, speaker line) 0.916; **run E v2 (every call type + dispatch) 0.950, live**; Qwen3-1.7B ⏳ (only if latency needs it) | Rajeev | ✅ run E v2 | table: F1, exact match, JSON validity, role acc, p50/p95, J/utterance |
| P10.3 | Serve: **ZRT's proxy routes by label only, so a LoRA module name 404s** ("unknown model name"). Merged model pushed to a private HF repo and served as `ems` (`scripts/merge_lora.py`). Fine-tuned models decode in JSON mode (the strict schema made it append "?" to every fact) | Rajeev | ✅ | outputs differ from base |
| P10.4 | Improve the fine-tune through **data, not rules**: onset vs LKW, brands and misspellings → generics, corrections, negative exams, home vs EMS-given meds, no invented vitals (the gold v1 dev-half error taxonomy, MODEL_PLAN §5) | Rajeev | ✅ run B (data from 8 independent annotators) | judged on gold v2 only |

## Models (lock before building further on them)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| M1 | Serve Nemotron-3-Nano-Omni NVFP4 with the fixes in AGENTS.md | Rajeev | ✅, then replaced by Qwen3-VL for vision (B12); Omni stays cached for rollback | `omni` serving on :8080 |
| M2 | Bake-off (MODEL_PLAN §5). gold v1 dev: rules 0.571, Omni p3 0.710, rules + Omni 0.764, run B 0.903. **gold v2 held-out (run 1): rules 0.444, Omni 0.644, rules + Omni 0.696, run B 0.860, rules + run B 0.854.** Always 3 runs; report the spread | Rajeev | ✅ all 3 runs; later runs in MODEL_PLAN §0h, §0i (run E v2 0.950 held-out) | table in MODEL_PLAN |
| M3 | Lock: best F1 with p95 ≤ 2 s; on a tie, prefer the model that also reads photos | Rajeev | ✅ **locked: run E v2** (team lead, 2026-09-24): best held-out F1; p95 is above 2 s on long lines (B6) | decision logged |
| M5 | 30-min soak test of the chosen models; record the actual kernel backend; warm-up before the demo | Vineet (S7) | 🔄 harness/runbook done; uncontended acceptance rerun pending | no errors, no drift, stable memory |
| M6 | `python3.12-dev` installed | lead | ✅ | — |
| M7 | 30-item gold v0 → **independent held-out gold v1 (100 items)**: labeler A writes and labels per `docs/LABELING_GUIDE.md`, labeler B labels blind, agreement measured, disagreements adjudicated | Rajeev | ✅ F1 0.993; bench 3× done | agreement ≥ 0.9 F1 between labelers; bench rerun 3× on v1 |
| M7b | **Gold v2 (100 items), the held-out set from now on**: same protocol, stricter phrasing variety; quotas for onset phrasing, non-anticoagulant brand names, misspelled drug names, EMS-given drugs | Rajeev | ✅ 100 items, 320 facts, agreement F1 0.976 before adjudication; 15 disagreements settled into LABELING_GUIDE §4c | agreement ≥ 0.9; adjudicated `eval/gold_v2.jsonl`; every extractor 3× |
| M8 | Speaker diarization (`pyannote/speaker-diarization-community-1`, the model HP's Audio2Text and Doctor NoteAI use): check it installs on aarch64 with torch 2.14 (gated on HF: accept terms with the team token), then measure whether it labels medic vs family correctly on multi-speaker clips | Collaborator 2 (S4) | ⏳ | works on 10 two-speaker clips, or a documented reason it can't |
| M9 | Adversarial speech eval + prompt-injection containment (`herald/extraction/guard.py`, `eval/adversarial_v1.jsonl`, `eval/adversarial_bench.py`) | Rajeev | ✅ earlier: 25/25 rules and pipeline. Live run E v2: 19/25 as ingested (two injected DNRs and an advice line regress; all held for a tap) | see MODEL_PLAN §0b, §0i |
| M9b | Fresh adversarial set (≥30) written by someone who hasn't read `guard.py`; measure guard false positives on gold v1 | Rajeev | ✅ `eval/adversarial_v2.jsonl` (40, unseen): rules 22/40, Omni 15–17, rules + Omni 18–19; guard false positives 0/200 on gold v1+v2. Run D 24/40, **run E v2 24/40**. Improvement via training data | pass rate on unseen attacks; 0 legitimate facts blocked on gold v1 |
| M10 | Measure warm restart time of `omni` (the kernel cache is populated now) and whole-stack cold start; write the pre-demo warm-up procedure | Rajeev | ✅ measured: stop 4 s, warm restart to ready 7.6 min (cold first start was 23 min), first request 1.6 s, then 0.9 s. Warm-up checklist: in the demo runbook (C4.5) | numbers in MODEL_PLAN; checklist in the demo runbook |
| M4 | **Gold set v1: ~100 utterances** incl. shorthand, number words, negations, corrections, attribution; two labelers; free-text keys scored by presence. **Blocks the text-model decision** (30 items can't separate ±0.04) | Rajeev | ✅ (= M7) | agreement reported |

## UI / UX (plan being researched → `docs/UX_PLAN.md`; U-tasks land here)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| U0 | Evidence-based UX plan: clinical alarm/color standards, human-AI interaction guidelines, "Herald thinking" trace panel, production component stack, what HP/NVIDIA provide on the ZGX | frontend lead | ✅ first version; 🔄 being expanded to full detail | `docs/UX_PLAN.md` |
| U5 | **Backend done:** every `transcripts[]` entry carries `trace` (heard → model facts with status running/done/error/unavailable → effects on the checklist, scores, alerts, gaps → per-fact relay eligibility); two-phase update in place (words first, facts on the same entry); `trace.rules` is empty for speech since the rules extractor was removed | Rajeev | ✅ | `tests/test_trace.py` |
| U15-API | **Backend done:** `GET /api/telemetry` (tokens, tok/s, GPU W and utilization, energy Wh, local $ vs cloud-equivalent $ with stated rates, cloud AI calls 0) and `GET /api/stack` (models with readiness + intelligence services, in HP's console format) | Rajeev | ✅ | `tests/test_telemetry.py`; frontend renders it in U15 |
| U1–U17 | Frontend build per `docs/UX_PLAN.md` §6, **by the frontend teammates** | frontend | ⏳ | see UX_PLAN |

## Infra, deliverables, pitch
| ID | Task | Owner | Status |
|---|---|---|---|
| I1 | GitHub repo live, collaborators added ✅; **make it public before submission** | Rajeev | 🔄 |
| I2 | `setup.sh` / Docker Compose that rebuilds everything from a clean clone (the node is wiped after the event) | Collaborator 1 (S2) | ⏳ (B10)
| I3 | README: evidence, architecture diagram, metrics table, how local/hybrid inference works | integration | 🔄 |
| D1 | Interactive deck: problem → solution → architecture → benchmarks → impact | pitch | ⏳ |
| D2 | 2-minute video (use `scripts/replay.py` for the screen capture) | pitch | ⏳ |
| D3 | Socials during the hack, tagging sponsors | pitch | ⏳ |
| D4 | Ask the organizers: does the overall prize depend on track? → submit to Community Impact (recommended) or Local Agentic | lead | ⏳ Thu AM |
| D5 | Fill in owners (`CONTRIBUTING.md` §5) | Rajeev | 🔄 lanes assigned in this file; collaborators add handles
| D6 | HF token in `~/.config/herald/secrets.env`; private repo `rajeev-chaurasia/herald-extractor-lora` | lead | ✅ |
