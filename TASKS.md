# TASKS.md: Herald task board

Deadline **Fri 2026-09-25, 8:00 PM**. Internal target: submit by 6:00 PM. Feature freeze Fri 11:00 AM.
**Scope: the full product ships. Nothing is cut** (team lead, 2026-09-23). P1–P10 is the **build order** (dependencies and what gets hardened first), not a cut list. If something runs late, add people to it. The only things we never build are safety principles, not scope cuts: treatment/dose/eligibility advice, cloud AI inference, and self-trained clinical predictors. Rules for agents: `AGENTS.md`.
Where decisions live: product spec and pitch → `/home/hp18/Documents/team-last-minute/.agent/ideas/herald-ems-copilot.md` (Nano only) · models → `docs/MODEL_PLAN.md` · UI → `docs/UX_PLAN.md` · hackathon rules and history → `/home/hp18/Documents/team-last-minute/.agent/context.md` (Nano only). The full document map is in `AGENTS.md`.
Status: ✅ done · 🔄 in progress · ⏳ todo · ⛔ blocked. Update this file in the same PR as the work.

## Checkpoint: Wed 2026-09-23, 22:15 (verified)
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

## P1: Speech → patient picture → NOW screen, gap-first
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P1.1 | Engine: facts, provenance, checklists, gaps, contradictions, trends, clocks | backend | ✅ | tests pass |
| P1.2 | Push-to-talk (Space = medic, F = other speaker) → `/api/audio` | frontend | ✅ | works via `http://localhost:<port>` |
| P1.3 | NOW screen matches spec §5: stroke alert at top, "needs attention", scores, ER status, ▶ provenance | frontend | 🔄 | a non-team viewer says "it's a checklist filling up", not "a form" |
| P1.4 | Confirm/reject UX for unconfirmed facts; the contradiction card shows both sources with ▶ audio | frontend | ✅ basic, ⏳ polish | one tap per confirm |
| P1.5 | Mic test with a real laptop over a port forward; record and replay provenance audio | pitch+frontend | ⏳ | the judge's own voice plays back |

## P2: Relay: network cut, critical update reaches the ED screen
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P2.1 | Relay: priority tiers, byte budget, ACK/seq, retries, idle probe, full sync on a good link | relay | ✅ | `tests/test_relay.py` + live run |
| P2.2 | ED receiver + screen (`ed_receiver/`) | relay/frontend | ✅ basic | shows the banner, critical fields, packets, bytes, duplicates |
| P2.3 | Run the ED receiver on a **second machine** (teammate laptop on hotspot); Nano → Toxiproxy :9000 → laptop:8200 | relay+pitch | ⏳ | two screens, two networks |
| P2.4 | Rehearse Shift+W / Shift+D / Shift+G five times; the pill shows "(emulated)" | pitch | ⏳ | no stumble |
| P2.5 | ED screen polish: big "INCOMING STROKE ALERT", LKW clock, warfarin in red, packet bytes visible | frontend | ⏳ | readable from 3 m |

## P3: Reconciliation
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P3.1 | Tests: 0 duplicates / 0 lost over a flaky link | relay | ✅ | 20 seeds pass |
| P3.2 | On-screen counter after restore: "reconciled · 0 duplicates · 0 lost" | frontend | ⏳ | visible on both screens |

## P4: Published scores
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P4.1 | NEWS2 + RACE + 2021 field triage, unit-tested, sources in code/UI | backend | ✅ | tests pass |
| P4.2 | Verify which stroke scale the **Santa Clara County** destination policy uses (RACE vs LAMS vs C-STAT); switch if needed | data | ⏳ | policy PDF cited in the README |
| P4.3 | Show field-triage criteria only for trauma/fall dispatches | frontend | ⏳ | hidden on stroke |

## P5: Eyes (photo reading)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P5.1 | `herald/models/vision.py`, `/api/photo`, `web/capture.html` | ML/frontend | ✅ code | — |
| P5.2 | Smoke test on `eval/photos/synthetic_*.jpg` | ML | ✅ 3/3 each | warfarin + SpO2 94 / PR 104 read correctly |
| P5.3 | Props: fingertip pulse oximeter, empty bottle with a printed "WARFARIN 5 MG" label, printed CA POLST | pitch | ⏳ | bought/printed |
| P5.4 | Photo test set: ~50 real phone photos of the props (angles, glare) + gold labels → photo-reading accuracy | data | ⏳ | number for the deck |

## P6: Judge beat (contradiction in a judge's voice)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P6.1 | Engine: other-speaker facts unconfirmed; contradiction alert with both sources | backend | ✅ | test passes |
| P6.2 | Card for the judge: "Mom's allergic to aspirin"; the F-key mic with speaker label "daughter" | pitch | ⏳ | rehearsed with a stranger |

## P7–P10 (all ship; built after P1–P6 are solid)
| ID | Task | Owner | Status | Notes |
|---|---|---|---|---|
| P7 | Simulated monitor panel | frontend | ✅ | fallback for P5 |
| P8 | Interpreter (Spanish ↔ English: Whisper + LLM + Kokoro TTS), statements land in the timeline with the original kept | ML | ⏳ | a Spanish answer shows up translated in the chart; round-trip latency measured |
| P9 | Protocol lookup: county policy PDFs → local search, read-only, cited section shown | data | ⏳ | "open the stroke protocol" shows the right county section |
| P11 | Multi-patient mass-casualty mode: several patient pictures on one rig; the relay prioritizes across patients by triage color | backend | ⏳ | two patients, the critical one's update goes first on a weak link |
| P12 | County configuration file (stroke scale, checklist items, destinations, reassessment interval); switch counties live | backend | ⏳ | switching county changes the checklist and scale on screen |
| P10.0 | Synthetic data (`scripts/compose_synth.py`, template composition; teacher generation piloted and rejected, MODEL_PLAN §4): 3,000 rows, 2,448 / 274 / 278 | ML/data | ✅ | labels correct by construction |
| P10.1 | Go/no-go checklist (MODEL_PLAN §4) | ML | ✅ 1–4 · 🔄 5 (latency) | failures get a root cause and a fix path the same morning |
| P10.2 | Run A: Qwen3-4B-Instruct-2507 BF16 LoRA r16 ✅ trained; run B: Qwen3-1.7B ⏳ | ML | 🔄 | table: F1, exact match, JSON validity, role acc, p50/p95, J/utterance |
| P10.3 | Serve: **ZRT's proxy routes by label only, so a LoRA module name 404s** ("unknown model name"). Merged model pushed to a private HF repo and served as `ems` (`scripts/merge_lora.py`). Fine-tuned models decode in JSON mode (the strict schema made it append "?" to every fact) | ML | ✅ | outputs differ from base |
| P10.4 | Improve the fine-tune through **data, not rules**: onset vs LKW, brands and misspellings → generics, corrections, negative exams, home vs EMS-given meds, no invented vitals (the gold v1 dev-half error taxonomy, MODEL_PLAN §5) | ML/data | ⏳ | judged on gold v2 only |

## Models (lock before building further on them)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| M1 | Serve Nemotron-3-Nano-Omni NVFP4 with the fixes in AGENTS.md | ML | ✅ | `omni` serving on :8080 |
| M2 | Bake-off (MODEL_PLAN §5) on gold v1: rules ✅ 0.571, Omni ✅ 0.672, rules + Omni ✅ 0.729 (3 runs each); fine-tuned `ems` (run A) 🔄 running; Nemotron-3-Nano-30B-A3B text ⏳. Final claims only on gold v2. Always 3 runs; report the spread | ML/data | 🔄 | table in MODEL_PLAN |
| M3 | Lock: best F1 with p95 ≤ 2 s; on a tie, prefer the model that also reads photos | ML lead | ⏳ | decision logged |
| M5 | 30-min soak test of the chosen model (NVFP4 instability reports); confirm MARLIN in the log; warm-up before the demo | ML | ⏳ | no errors |
| M6 | `python3.12-dev` installed | lead | ✅ | — |
| M7 | 30-item gold v0 → **independent held-out gold v1 (100 items)**: labeler A writes and labels per `docs/LABELING_GUIDE.md`, labeler B labels blind, agreement measured, disagreements adjudicated | data | ✅ F1 0.993; bench 3× done | agreement ≥ 0.9 F1 between labelers; bench rerun 3× on v1 |
| M7b | **Gold v2 (100 items), the held-out set from now on**: same protocol, stricter phrasing variety; quotas for onset phrasing, non-anticoagulant brand names, misspelled drug names, EMS-given drugs | data | 🔄 labeler A ✅ (317 facts), labeler B running | agreement ≥ 0.9; adjudicated `eval/gold_v2.jsonl`; every extractor 3× |
| M8 | Speaker diarization (`pyannote/speaker-diarization-community-1`, the model HP's Audio2Text and Doctor NoteAI use): check it installs on aarch64 with torch 2.14 (gated on HF: accept terms with the team token), then measure whether it labels medic vs family correctly on multi-speaker clips | ML | ⏳ | works on 10 two-speaker clips, or a documented reason it can't |
| M9 | Adversarial speech eval + prompt-injection containment (`herald/extraction/guard.py`, `eval/adversarial_v1.jsonl`, `eval/adversarial_bench.py`) | ML/eval | ✅ 25/25 rules and 25/25 ×3 pipeline (was 21 and 18–19) | see MODEL_PLAN §0b |
| M9b | Fresh adversarial set (≥30) written by someone who hasn't read `guard.py`; measure guard false positives on gold v1 | eval | ⏳ | pass rate on unseen attacks; 0 legitimate facts blocked on gold v1 |
| M10 | Measure warm restart time of `omni` (the kernel cache is populated now) and whole-stack cold start; write the pre-demo warm-up procedure | ML | ⏳ | numbers in MODEL_PLAN; checklist in the demo runbook |
| M4 | **Gold set v1: ~100 utterances** incl. shorthand, number words, negations, corrections, attribution; two labelers; free-text keys scored by presence. **Blocks the text-model decision** (30 items can't separate ±0.04) | data | ✅ (= M7) | agreement reported |

## UI / UX (plan being researched → `docs/UX_PLAN.md`; U-tasks land here)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| U0 | Evidence-based UX plan: clinical alarm/color standards, human-AI interaction guidelines, "Herald thinking" trace panel, production component stack, what HP/NVIDIA provide on the ZGX | frontend lead | ✅ first version; 🔄 being expanded to full detail | `docs/UX_PLAN.md` |
| U5 | **Backend done:** every `transcripts[]` entry carries `trace` (heard → rules facts → model facts with status running/done/error → effects on the checklist, scores, alerts, gaps → per-fact relay eligibility); two-phase update in place | backend | ✅ | `tests/test_trace.py` |
| U15-API | **Backend done:** `GET /api/telemetry` (tokens, tok/s, GPU W and utilization, energy Wh, local $ vs cloud-equivalent $ with stated rates, cloud AI calls 0) and `GET /api/stack` (models with readiness + intelligence services, in HP's console format) | backend | ✅ | `tests/test_telemetry.py`; frontend renders it in U15 |
| U1–U17 | Frontend build per `docs/UX_PLAN.md` §6, **by the frontend teammates** | frontend | ⏳ | see UX_PLAN |

## Infra, deliverables, pitch
| ID | Task | Owner | Status |
|---|---|---|---|
| I1 | GitHub repo live, collaborators added ✅; **make it public before submission** | lead | 🔄 |
| I2 | `setup.sh` / Docker Compose that rebuilds everything from a clean clone (the node is wiped after the event) | integration | ⏳ |
| I3 | README: evidence, architecture diagram, metrics table, how local/hybrid inference works | integration | 🔄 |
| D1 | Interactive deck: problem → solution → architecture → benchmarks → impact | pitch | ⏳ |
| D2 | 2-minute video (use `scripts/replay.py` for the screen capture) | pitch | ⏳ |
| D3 | Socials during the hack, tagging sponsors | pitch | ⏳ |
| D4 | Ask the organizers: does the overall prize depend on track? → submit to Community Impact (recommended) or Local Agentic | lead | ⏳ Thu AM |
| D5 | Fill in owners (`CONTRIBUTING.md` §5) | lead | ⏳ |
| D6 | HF token in `~/.config/herald/secrets.env`; private repo `rajeev-chaurasia/herald-extractor-lora` | lead | ✅ |
