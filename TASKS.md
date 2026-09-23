# TASKS.md: Herald task board

Deadline **Fri 2026-09-25, 8:00 PM**. Internal target: submit by 6:00 PM. Feature freeze Fri 11:00 AM.
Build in **protect order** (P1 highest). If Thursday noon looks bad, cut from the bottom. Rules for agents: `AGENTS.md`.
Status: ✅ done · 🔄 in progress · ⏳ todo · ⛔ blocked. Update this file in the same PR as the work.

## Checkpoint: Wed 2026-09-23, 20:15 (verified)
**Done**
- ✅ **Engine + tests:** 56 tests pass. Every NEWS2/RACE/field-triage band boundary; the stroke demo flow; contradictions; confirmed-only scoring; relay reconciliation over a link that loses 50% of requests/ACKs (20 seeds): 0 duplicates, 0 lost.
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
| P5.1 | `herald/vision.py`, `/api/photo`, `web/capture.html` | ML/frontend | ✅ code | — |
| P5.2 | Smoke test on `eval/photos/synthetic_*.jpg` | ML | ✅ 3/3 each | warfarin + SpO2 94 / PR 104 read correctly |
| P5.3 | Props: fingertip pulse oximeter, empty bottle with a printed "WARFARIN 5 MG" label, printed CA POLST | pitch | ⏳ | bought/printed |
| P5.4 | Photo test set: ~50 real phone photos of the props (angles, glare) + gold labels → photo-reading accuracy | data | ⏳ | number for the deck |

## P6: Judge beat (contradiction in a judge's voice)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| P6.1 | Engine: other-speaker facts unconfirmed; contradiction alert with both sources | backend | ✅ | test passes |
| P6.2 | Card for the judge: "Mom's allergic to aspirin"; the F-key mic with speaker label "daughter" | pitch | ⏳ | rehearsed with a stranger |

## P7–P10: cut first if needed
| ID | Task | Owner | Status | Notes |
|---|---|---|---|---|
| P7 | Simulated monitor panel | frontend | ✅ | fallback for P5 |
| P8 | Interpreter (Spanish ↔ English, Whisper + LLM + TTS) | ML | ⏳ | optional; only if P1–P6 are green Thu noon |
| P9 | Protocol lookup: county policy PDFs → local search, read-only | data | ⏳ | optional |
| P10.0 | Synthetic data generator (reverse generation: code samples fact bundles, the teacher writes utterances, the label is the bundle; ASR noise; template split) | ML/data | ⏳ tonight | needs the teacher model serving |
| P10.1 | Go/no-go checklist (MODEL_PLAN §4): install PEFT 0.21 + TRL 1.13 `--no-deps`, 10-step smoke train, adapter loads in vLLM | ML | ⏳ Thu 08:30 | failure → ship without it |
| P10.2 | Run A: Qwen3-4B-Instruct-2507 BF16 LoRA r16; run B: Qwen3-1.7B | ML | ⏳ Thu | table: F1, exact match, JSON validity, role acc, p50/p95, J/utterance |
| P10.3 | Serve the adapter: push to a **private HF repo** (needs `HF_TOKEN`) or `vllm serve <path>` from the ZRT venv | ML | ⏳ | outputs differ from base |

## Models (lock before building further on them)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| M1 | Serve Nemotron-3-Nano-Omni NVFP4 with the fixes in AGENTS.md | ML | ✅ | `omni` serving on :8080 |
| M2 | Bake-off (MODEL_PLAN §5): rules ✅, Omni ✅ (audited, 3 runs); Nemotron-3-Nano-30B-A3B text ⏳ after M4. Always 3 runs; report the spread | ML/data | 🔄 | table in MODEL_PLAN |
| M3 | Lock: best F1 with p95 ≤ 2 s; on a tie, prefer the model that also reads photos | ML lead | ⏳ | decision logged |
| M5 | 30-min soak test of the chosen model (NVFP4 instability reports); confirm MARLIN in the log; warm-up before the demo | ML | ⏳ | no errors |
| M6 | `python3.12-dev` installed | lead | ✅ | — |
| M4 | **Gold set v1: ~100 utterances** incl. shorthand, number words, negations, corrections, attribution; two labelers; free-text keys scored by presence. **Blocks the text-model decision** (30 items can't separate ±0.04) | data | ⏳ | agreement reported |

## UI / UX (plan being researched → `docs/UX_PLAN.md`; U-tasks land here)
| ID | Task | Owner | Status | Done when |
|---|---|---|---|---|
| U0 | Evidence-based UX plan: clinical alarm/color standards, human-AI interaction guidelines, "Herald thinking" trace panel, production component stack, what HP/NVIDIA provide on the ZGX | frontend lead | 🔄 research | `docs/UX_PLAN.md` merged |

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
