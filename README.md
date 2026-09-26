# Herald

**The patient's story arrives before the doors open.**

Herald is an AI copilot for the back of the ambulance. It listens to the crew, the patient and the family, reads the
patient monitor through a camera, keeps a checked patient record while the paramedic works, pre-alerts the emergency
department over a weak link, and hands the patient over in one tap. **Every model runs on one HP ZGX Nano in the
vehicle. Zero cloud AI calls.**

Team LastMinute · HP Edge AI SJSU Hackathon, September 2026 · Jenil Savalia · Tushar Singh · Vineet Malewar ·
Shivani Jariwala · Rajeev Ranjan Chaurasia

![Herald system architecture: ambulance inputs feed local AI on the HP ZGX Nano; a deterministic engine keeps the patient record and decides what is sent; a weak-link relay updates the emergency department board, which acknowledges back](docs/architecture.png)

## The problem

A paramedic treats, remembers and reports at the same time.

- **During the call, minutes matter.** An untreated stroke costs 1.9 million neurons a minute (Saver, *Stroke* 2006);
  each 30-minute delay in a heart attack raises 1-year mortality by 7.5% (De Luca et al., *Circulation* 2004).
- **After the call, the report comes late.** Hospitals received only about half of EMS patient reports, and 26.3% of
  those within 2 hours (155,423 transports; Shanley et al., *Prehospital Emergency Care* 2025).
- **At the door, the handover is spoken and incomplete.** 97.6% of handovers were verbal only; allergies were missing
  in 55.4%, and the EMS record was available in 7.2% (Braverman et al., *International Emergency Nursing* 2026).
  When the ED saw live prehospital data before arrival, team readiness rose from 7.1 to 12.8 out of 15 (Bleeg et al.,
  *Journal of Emergency Medicine* 2026).
- **And the network drops exactly when it is needed:** rural roads, basements, disasters.

## What Herald does

| | |
|---|---|
| **Listens hands-free** | One room microphone hears the crew, the patient and the family. Speech gates drop noise and other languages; small talk is forgotten. |
| **Speech → facts** | Whisper large-v3-turbo transcribes (a 10 s clip in about 0.3 s); a **Qwen3-4B we fine-tuned on this box** turns the words into typed facts (vitals, medications, allergies, onset, stroke and STEMI findings, treatments) in about 1 s. |
| **Checks every fact (agentic)** | A second model, **Qwen3-VL-30B-A3B fine-tuned on this box**, re-reads the words and keeps only facts they actually state. A fact enters the record on its own only when the check kept it and the model's confidence clears a calibrated bar. **Name, allergies, medications, drugs given and code status always wait for one tap.** |
| **Reads the monitor** | The camera reads HR, BP, SpO2, RR and EtCO2 about every 15 s straight into live trends; a reading that jumps implausibly is held for the medic. |
| **Copilot on every call** | County alert checklists (stroke, STEMI, trauma, sepsis) show what is still missing; published scores (NEWS2, RACE, G.F.A.S.T., field triage) are computed by plain code; clocks and reassessment reminders run. |
| **Protocols on voice** | "Show me the protocol for STEMI" returns Santa Clara County's own passage, quoted and cited (document, section, page, date). |
| **Destination and ETA** | Set by voice, or suggested from the county's rules (nearest STEMI, stroke or trauma centre) with a road-route ETA computed on the vehicle (OSRM). |
| **Weak-link pre-alert** | Only confirmed facts leave the vehicle: most critical first, 420-byte packets on a weak link, queued and reconciled when the link returns. The ED board replies ("Received", "Cath lab activated"). |
| **One-tap handover** | A spoken MIST / SBAR report from confirmed facts, frozen and sent at hand over, with a FHIR R4 export; the next patient starts clean. |
| **The medic decides** | Herald never recommends treatment. Scores, checklists and what gets sent are plain, tested code; protocol text is the county's own. |

## Measured results (held-out test set, 3 runs each)

| Extractor (speech → facts) | F1 | Precision | Recall | Who said it | Latency p50 / p95 |
|---|---|---|---|---|---|
| Nemotron-3-Nano-Omni 30B-A3B, prompted | 0.661 | 0.69 | 0.63 | 0.84 | 0.95 / 1.9 s |
| **Qwen3-4B fine-tuned on this box, FP8 (live)** | **0.950** | **0.96** | **0.94** | **0.97** | 1.1-1.5 / 2.4-3.1 s |

- **99.4%** of the medic's facts that confirmed themselves were correct (160 of 161 on the held-out set).
- **0 facts lost, 0 duplicates** across 20 seeds at 50% packet loss with 420-byte packets.
- **1,746** numbered protocol sections recovered from 32 county documents, none spurious; with local reranking the
  right passage is first for 41 of 52 questions.
- **Drug names to RxNorm on the box:** precision 0.933 → 0.956, nothing lost across 42 runs.
- **0 cloud AI calls:** every model loads from local folders; a running server makes no outbound connection except
  the ED relay and the protocol sync, both through one egress policy.

### Why these metrics

- **F1** counts both wrong and missed facts; each hurts a patient in a different way.
- **Who said it**: a family member's words are not the medic's finding.
- **Latency**: the medic is working live; the record has to keep up with speech.
- **Self-confirmed accuracy**: those facts skip the medic's tap, so they carry the strictest bar.
- **Packet loss**: ambulances lose signal; nothing confirmed may be lost or duplicated on the way to the ED.
- **Protocol recovery and retrieval**: a quoted rule is only useful if it is the county's exact text.

Gold sets were written and labeled by two independent annotators (agreement F1 0.979) who never saw the extractors
or training data. Method and every run: [`docs/MODEL_PLAN.md`](docs/MODEL_PLAN.md).

## Demo and links

| Page | Address |
|---|---|
| Landing page | `http://localhost:8100` |
| Medic app ("Open Herald" starts a fresh case) | `http://localhost:8100/app/` |
| Recorded call, plays by itself | `http://localhost:8100/app/?fixture=stroke_demo` |
| ED board | `http://localhost:8200` |
| Monitor simulator | `http://localhost:8100/monitor.html` |

## Architecture

Models turn speech, camera frames and documents into facts or passages. Everything that decides is plain, tested
code: the patient record, scores, checklists, what counts as confirmed and what gets sent. Clinical tables, county
rules and prompts live in `config/` as reviewed data with their sources.

| Path | What |
|---|---|
| `herald/extraction/` | Speech to facts: the fine-tuned extractor, confidence, grounding, the check step |
| `herald/capture/` | Camera: monitor watch, frame selection, device readings and the jump check |
| `herald/core/` | Fact model, vocabulary, patient record, confirmation policy |
| `herald/scoring/`, `herald/checklists/` | NEWS2, RACE, G.F.A.S.T., field triage; county alert checklists |
| `herald/knowledge/` | County protocol search, quoting and citation |
| `herald/transport/` | Destination from county rules, road-route ETA (local OSRM) |
| `herald/relay/`, `herald/egress/` | Weak-link relay to the ED; the single policy point for anything leaving the box |
| `herald/reporting/` | MIST / SBAR handover report, FHIR R4 export |
| `herald/api/` | FastAPI app and WebSocket hub |
| `ui/` | Landing page, medic app, monitor simulator (React, TypeScript) |
| `ed_receiver/` | The emergency department board |
| `eval/` | Gold sets, benchmarks, adversarial sets, protocol answer keys |

## Run it

On the HP ZGX Nano (aarch64, GB10, CUDA 13), from a checkout of `main`:

```bash
scripts/setup.sh          # first time: checks the platform, installs requirements
scripts/herald.sh up      # starts everything and waits until speech, extraction and vision are ready
```

`herald.sh up` serves the two fine-tuned models on HP Z Runtime (:8080), builds the UI, and starts the ED board
(:8200), the link emulator (:9000), the road router (:5100) and the app (:8100). `herald.sh status`, `logs` and
`down` do the rest. A container build is also available: `docker compose up --build herald`.

Browsers allow the microphone and camera only on `localhost` or HTTPS, so forward the ports from a laptop:

```bash
ssh -N -L 8100:localhost:8100 -L 8200:localhost:8200 <user>@<nano>
```

Then open `http://localhost:8100` and click **Open Herald**. The ED board is `http://localhost:8200` and the
monitor simulator is `http://localhost:8100/monitor.html` (point the camera at it).

- Tests: `python -m pytest -q` (backend) and `npx vitest run` in `ui/` (screens).
- Benchmarks: `eval/bench_extract.py`, `eval/adversarial_bench.py`.
- Running the ED board on a second machine: `pip install fastapi "uvicorn[standard]"`, then
  `python -m uvicorn ed_receiver.app:app --port 8200`, and point `HERALD_ED_URL` at it.

## Privacy and the cloud

No code path in Herald can call a cloud AI service: the model client accepts only local addresses, and the app
refuses to start with anything else. The only data that leaves the vehicle is the ED update and the county protocol
sync, and every outbound request passes one allow, queue or deny decision (`herald/egress/`, `config/egress.yaml`),
logged and counted at `GET /api/egress`. Patient audio and photos stay on the vehicle and are deleted when the
encounter ends. The active call is kept in encrypted local storage so a restart does not lose it.

## Sources

- Saver JL. Time is brain, quantified. *Stroke* 2006.
- De Luca G et al. Time delay to treatment and mortality in primary angioplasty. *Circulation* 2004.
- Shanley J et al. EMS patient care report availability after transport. *Prehospital Emergency Care* 2025.
- Braverman A et al. EMS to ED handovers, an observational study. *International Emergency Nursing* 2026.
- Bleeg RC et al. Real-time prehospital data on an ED screen. *Journal of Emergency Medicine* 2026.
- Royal College of Physicians. National Early Warning Score (NEWS2), 2017.
- Pérez de la Ossa N et al. RACE scale. *Stroke* 2014.
- Santa Clara County EMS policies and protocols, including 501, 602, 605, 700-A04, 700-A08 and 700-A13 (2026).
- Newgard CD et al. National Guideline for the Field Triage of Injured Patients, 2021.

Team LastMinute, HP Edge AI SJSU Hackathon, September 2026. Licensed under the terms in `LICENSE`.
