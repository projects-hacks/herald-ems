# TASKS.md: Herald task board

Deadline **Fri 2026-09-25, 8:00 PM**. Internal target: submit by 6:00 PM. Feature freeze Fri 11:00 AM.
Build in **protect order** (P1 highest). If Thursday noon looks bad, cut from the bottom. Rules for agents: `AGENTS.md`.
Status: ✅ done · 🔄 in progress · ⏳ todo · ⛔ blocked. Update this file in the same PR as the work.

## Checkpoint: Wed 2026-09-23, evening
- ✅ **Engine:** 56 tests pass. They cover every NEWS2/RACE/field-triage band boundary, the stroke demo flow, the husband-vs-daughter contradiction, confirmed-only scoring, and relay reconciliation over a link that loses 50% of requests or ACKs (20 random seeds): 0 duplicates, 0 lost.
- ✅ **Stroke demo, end to end** (`scripts/replay.py scenarios/stroke_demo.json`): stroke alert 0/6 → 6/6, RACE 6 (positive), NEWS2 2 → 5 (medium), contradiction alert, clocks.
- ✅ **Speech → facts:** Whisper large-v3-turbo on the GPU; a 10.4 s clip round-trips (upload + STT + extraction) in 0.47 s.
- ✅ **Rules extractor baseline** on `eval/gold_v0.jsonl` (30 utterances): **F1 0.852**, role accuracy 0.942. Misses: spoken number words, self-corrections, "ETA to X is N", medication lists.
- ✅ **Relay over emulated links** (Toxiproxy):
  - Weak link: critical facts first in packets of ≤ 420 B (119 B, then 419 B), connection resets retried until ACKed.
  - Offline: updates queue.
  - Restored: the probe detects recovery and the full record syncs (31 timeline entries). 0 duplicates; about 99.8% of bytes kept on the vehicle.
- 🔄 **Local VLM/LLM:** Nemotron-3-Nano-Omni-30B-A3B NVFP4 via ZRT. Two start failures are fixed (missing Python headers, OOM from parallel JIT compiles); the third start is in progress.
- ✅ **Model selection research done** → `docs/MODEL_PLAN.md`:
  - Text: A3B MoE NVFP4 only (Nemotron-3-Nano-30B-A3B primary, Qwen3-30B-A3B-FP8 fallback, Nemotron-Omni also in the bake-off).
  - Vision: Nemotron-Omni primary, Qwen3.6-35B-A3B-NVFP4 fallback.
  - STT: keep Whisper.
  - Fine-tune: Qwen3-4B/1.7B BF16 LoRA with PEFT+TRL.

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
| P5.2 | Smoke test on `eval/photos/synthetic_*.jpg` once the VLM is serving | ML | ⛔ VLM starting | warfarin + SpO2 94 / PR 104 read correctly |
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
| M1 | Serve Nemotron-3-Nano-Omni NVFP4 with the fixes in AGENTS.md (first start compiles kernels for ~15 min; cached after) | ML | 🔄 | `curl 127.0.0.1:8080/v1/models` lists `omni` |
| M2 | Bake-off on `eval/gold_v0.jsonl` (MODEL_PLAN §5): rules vs Omni vs Nemotron-3-Nano-30B-A3B vs Qwen3-30B-A3B-FP8. **One model served at a time.** | ML/data | ⏳ | table in MODEL_PLAN |
| M3 | Lock: best F1 with p95 ≤ 2 s; on a tie, prefer the model that also reads photos | ML lead | ⏳ | decision logged |
| M5 | 30-min soak test of the chosen model (NVFP4 instability reports); confirm MARLIN in the log; warm-up before the demo | ML | ⏳ | no errors |
| M6 | `sudo apt install python3.12-dev` (removes the include-path workaround) | lead | ⏳ | — |
| M4 | Gold set v1: ~100 utterances incl. shorthand, number words, negations, corrections, attribution; two labelers | data | ⏳ | agreement reported |

## Infra, deliverables, pitch
| ID | Task | Owner | Status |
|---|---|---|---|
| I1 | GitHub: repo currently returns 404 publicly (private?). Add all five as collaborators; make it public before submission | lead | ⏳ |
| I2 | `setup.sh` / Docker Compose that rebuilds everything from a clean clone (the node is wiped after the event) | integration | ⏳ |
| I3 | README: evidence, architecture diagram, metrics table, how local/hybrid inference works | integration | 🔄 |
| D1 | Interactive deck: problem → solution → architecture → benchmarks → impact | pitch | ⏳ |
| D2 | 2-minute video (use `scripts/replay.py` for the screen capture) | pitch | ⏳ |
| D3 | Socials during the hack, tagging sponsors | pitch | ⏳ |
| D4 | Ask the organizers: does the overall prize depend on track? → submit to Community Impact (recommended) or Local Agentic | lead | ⏳ Thu AM |
| D5 | Fill in owners (`CONTRIBUTING.md` §5) | lead | ⏳ |
| D6 | Create a Hugging Face token (write access) and a private repo for adapters; share it with the ML owner only, never commit it | lead | ⏳ |
