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
| **Checks every fact (agentic)** | A second model, a **Qwen3-VL-30B-A3B we fine-tuned on this box**, re-reads the words and keeps only facts they actually state. A fact enters the record on its own only when the check kept it and the model's confidence clears a calibrated bar. **Name, allergies, medications, drugs given and code status always wait for one tap.** |
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
| **Qwen3-4B fine-tuned on this box, FP8 (live)** | **0.950** | **0.96** | **0.94** | **0.97** | 1.1–1.5 / 2.4–3.1 s |

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
or training data. The numbers are measured from transcripts; the full method, including what was noise and what was a
flaw in our own test, is in [`docs/MODEL_PLAN.md`](docs/MODEL_PLAN.md). Field evaluation with real crews is the
next step.

## Demo and links

- Landing page: `http://localhost:8100` · medic app: `http://localhost:8100/app/` ("Open Herald" starts a fresh case)
  · recorded call: `http://localhost:8100/app/?fixture=stroke_demo` · ED board: `http://localhost:8200` ·
  monitor simulator: `http://localhost:8100/monitor.html`
- Walkthrough of a full call: [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md)

## Architecture

```
CAPTURE                          PATIENT STATE (deterministic)             OUTPUTS
ambient / PTT audio ─┐           append-only facts with provenance         NOW screen (changes and gaps)
selected frames     ─┼─► facts ─► checklists · gaps · contradictions ────► protocol lookup (cited)
manual observations ─┘           trends · clocks · NEWS2 · RACE · G.F.A.S.T. relay → ED journey
        │                        (content: config/, reviewed and cited)
  Whisper → fine-tuned extractor (the only extractor) · vision model for photos
```

**The model never decides.** Language models only turn speech, photos, and document images into facts or passages. Checklists, scores, contradictions, clocks, and what gets sent are plain, tested code. Every clinical table and citation lives in `config/` as reviewed data.

| Path | What |
|---|---|
| `config/` | Reviewed content with sources: key vocabulary, score tables, checklists, relay tiers, prompts, county rules and protocol documents |
| `herald/core/` | Fact model, vocabulary, incident store, confirmation policy, and the projection to the patient picture |
| `herald/scoring/` | NEWS2, RACE, G.F.A.S.T., field triage: data-driven engines, tested at every band boundary |
| `herald/checklists/` | Alert-ready checklists (stroke from the county config, STEMI) |
| `herald/extraction/` | Speech → facts: the model extractor, per-fact confidence, grounding and injection guards |
| `herald/models/` | Adapters to the local model servers (localhost only), Whisper, photo reading, embeddings |
| `herald/knowledge/` | Protocol lookup: sections, tables, figures, hybrid search, sync with review flags |
| `herald/terminology/` | Drug and allergen names → RxNorm (brands, retired brands, misspellings, combinations), class allergies → ICD-10-CM; the code on each fact; anything not matched exactly waits for a tap |
| `herald/relay/` | Weak-link relay to the emergency department |
| `herald/egress/` | The one ALLOW / QUEUE / DENY decision point every outbound call passes through (`config/egress.yaml`) |
| `herald/telemetry/` | Tokens, GPU power, energy, cost vs a cloud equivalent |
| `herald/api/` | FastAPI app, WebSocket hub, composition root |
| `eval/` | Gold sets, benchmarks, adversarial sets, protocol answer keys, saved predictions; the hand-written rules extractor survives only here, as a baseline |

## Run it

**One command starts the whole system** on the ZGX Nano (aarch64, GB10, CUDA 13), from a checkout of `main`:

```bash
scripts/herald.sh up          # add --pull to fast-forward to origin/main first
```

It skips whatever is already running and verifies the rest: the one-time data (RxNorm drug index, Whisper and
embedding weights), the shipped models on HP Z Runtime :8080 (`ems-e-v2-fp8` for speech -> facts, `herald-f` for
photos, the monitor and protocol reranking; served one at a time and only if memory allows), the UI build, the ED
screen (:8200) behind the link emulator (:9000), and the app (:8100) with Whisper preloaded. It exits non-zero
unless speech, extraction and vision all report ready, then prints the URLs. `scripts/herald.sh status`,
`scripts/herald.sh logs` and `scripts/herald.sh down` (models keep serving) do the rest.

Browsers only allow the microphone and camera on `localhost` or HTTPS, so from a laptop forward the ports first:
`ssh -L 8100:localhost:8100 -L 8200:localhost:8200 <user>@<nano>`, then open `http://localhost:8100/app/` (medic; `/` is the landing page),
`http://localhost:8200` (ED) and `http://localhost:8100/monitor.html` (a monitor to point the camera at).

**First time on a fresh machine:** `scripts/setup.sh` checks the platform and installs `requirements.txt` pinned
against the env's torch/transformers (so pip can't move them), then `scripts/herald.sh up` does everything else.
For development with auto-reload, `scripts/run_dev.sh` still starts only the app.

**Containerized alternative:** `docker compose up --build herald` builds `ui/dist` and pre-fetches the public
STT/embedding weights (Whisper large-v3-turbo, bge-base-en-v1.5) into the image in one `docker build`, so it
needs no separate npm or model-download step — but it still expects `scripts/serve_models.sh` running on the
host first (ZRT/the fine-tuned models are not containerized; see the Dockerfile's top comment and
`docker-compose.yml`). `docker compose --profile full up --build` also starts the mock ED receiver.

For continuous observation, choose **Start listening** and **Camera → Start monitor watch**, granting each device explicitly. Adjust the monitor region and return to the overview; camera capture continues across care pages. Hiding the browser tab, changing patient or losing the connection stops the camera. For a second-laptop equipment simulation, open `/monitor.html`, start its synthetic journey and point the observing camera at that display. It sends no facts directly to Herald. Real inference must use an approved serving instance; see the capture setup above.

- **LAN access (a tablet in the back of the ambulance):** `scripts/run_dev.sh` and the Docker image bind
  `127.0.0.1` by default -- only this box can reach Herald. Reaching it from another device needs both
  `HERALD_BIND_HOST=0.0.0.0` and `HERALD_DEVICE_TOKEN=<a shared secret>` (every mutating `/api/*` request must
  send it back as `X-Herald-Token`; open the tablet's page once as `.../?token=<the same secret>` and the UI
  remembers it). Skip the token and any other device on that Wi-Fi can read and write patient state.
- **Destination and road ETA:** `scripts/herald.sh up` starts a local OSRM road router on :5100 (one-time map
  data: `scripts/routing_setup.sh`, the Santa Clara County OpenStreetMap extract, ~75 MB, prepared in seconds;
  map data (c) OpenStreetMap contributors, ODbL). The medic tablet shares its location with the vehicle server
  (Settings; the browser asks once, over the same localhost/HTTPS rule as the microphone, and re-reads the position
  every 15 s). The destination is set by voice or one tap, never from a dropdown: saying a county hospital
  ("Transporting to Regional") sets it once the local model matches the words to exactly one hospital on the county
  list, and while none is set Herald suggests ONE hospital from the county's own destination rules (Policy 602,
  700-A13: a stroke with G.F.A.S.T. 4 of 4 goes to the closest Comprehensive Stroke Center, a STEMI alert to the
  closest STEMI Receiving Center, a trauma alert to the closest trauma center, otherwise the closest emergency
  department) with a single Accept. The ETA follows the road route to the destination. Without the router or a fresh
  location the ETA is the crew's spoken estimate. Drive times are normal driving without traffic or lights and siren.
  Live diversion status is not available on the vehicle.
  Finishing an encounter asks how it ended (NEMSIS dispositions); a refusal or non-transport tells an already-alerted
  ED the patient is not coming.
- **Relay demo:** `scripts/link.sh start 127.0.0.1:8200`, then run `ed_receiver` on port 8200 and set `HERALD_ED_URL=http://127.0.0.1:9000`. Shift+G/W/D switch the emulated link.
- **Protocol-update demo** (two real versions of 700-S04): `scripts/demo_protocol_update.sh setup` and `HERALD_PROTOCOL_MIRROR=http://127.0.0.1:8300`.
- **Tests:** `python -m pytest -q`.
- **Benchmarks:** `eval/bench_extract.py`, `eval/adversarial_bench.py`.

### Encounter recovery and retention

Herald keeps the active roster, previous encounters and their delivery queues in authenticated, encrypted local recovery. The ciphertext is
`data/state/active-call.fernet`; its 0600 key is stored separately at
`~/.config/herald/state.fernet.key` (override with `HERALD_STATE_KEY_FILE`). A restart restores the active patient
roster, facts, transcript trace, audit entries and relay state, and the API marks the snapshot `restored: true`.
Finishing deletes registered audio/photos while retaining structured records. **Patients** separates adding someone at the same scene from finishing and starting the next encounter; previous handoffs open without changing the active patient. **ED handoff** records arrival and transfer-of-care times explicitly. Existing authorized updates keep their original destination and continue retrying. A new encounter requires new ED authorization. Restored encounters require a patient confirmation before capture resumes.

The key must not be committed or copied with patient data. If the key is missing, too broadly readable,
or the ciphertext fails authentication, Herald refuses to start rather than silently replacing the record.

Audio and photos remain local evidence files; they are deleted at call end but are not encrypted by this recovery
snapshot mechanism. Set `HERALD_PERSISTENCE=0` only for disposable tests or fixtures.

## When Herald escalates to the cloud, and when it refuses

There is no code path in Herald that can construct a request to a cloud AI provider. `LocalLLMClient`
(`herald/models/llm_client.py`) refuses to be built with anything but a `127.0.0.1` / `localhost` / `::1` URL
(`herald/config/settings.py` validates `HERALD_LLM_URL` the same way at startup), so extraction, photo reading,
and protocol reranking physically cannot address a cloud endpoint. The extraction and vision models are the
*only* language models Herald runs.

What can still leave the box is data: relay packets to the emergency department, and a protocol-document sync
against a mirror URL (`HERALD_PROTOCOL_MIRROR`). Every one of those, plus every local model call, is decided by
one policy point before it happens: `EgressPolicy.decide()` (`herald/egress/policy.py`, config `config/egress.yaml`).

- **ALLOW, never counted as a cloud escalation** — the destination is a local model endpoint on this box.
- **ALLOW** — the destination is on `config/egress.yaml`'s `ed_allow_list`, or is this deployment's own
  `HERALD_ED_URL` / `HERALD_PROTOCOL_MIRROR` (naming a host in the environment allow-lists it automatically).
- **QUEUE** — an allow-listed destination, but the relay's own measured link state is currently `down`; retried,
  nothing is sent or lost.
- **DENY, counted as a refused cloud call** — anything else. This is the default for every host Herald hasn't
  been explicitly told to trust.

Every decision is logged (bounded to the most recent 200, `config/egress.yaml` `decision_log_size`) and counted;
`GET /api/egress` returns the counts and the most recent 50 log entries. The
`cloud_ai_calls` counter shown on `GET /api/health`, `GET /api/stack`, `GET /api/telemetry`, and every incident
snapshot's `counters` is `0` because DENY happens before the request, not because the number is hardcoded —
`GET /api/egress`'s `cloud_calls_refused` counts how many times that refusal actually fired (a misconfigured
`HERALD_ED_URL`, a protocol mirror not on the allow-list, or a stray host during testing).

`POST /api/relay/config` runs the same check before it ever stores an ED URL: a non-local, non-allow-listed
host is rejected with `403` and never reaches `Relay.set_ed_url`.

## Evidence behind the scores (sources checked September 2026)

- **NEWS2** (Royal College of Physicians, Dec 2017; still the current version): pooled across 30 studies and 185,835 patients, 2-day mortality AUC 0.88, sensitivity 0.81, specificity 0.81 (Wei et al., *Ann Transl Med* 2023).
- **RACE ≥ 5** for large-vessel occlusion (Pérez de la Ossa et al., *Stroke* 2014): pooled across 9 studies, sensitivity 0.75, specificity 0.76 (Suzuki et al., *J Am Heart Assoc* 2026).
- **G.F.A.S.T.** (Santa Clara County EMS Protocol 700-A13, effective Jan 1, 2026): the published G-FAST at ≥ 3, pooled across 13 studies and 12,414 patients, gives sensitivity 0.73, specificity 0.74, AUC 0.80 (Wang et al., *Emerg Med J* 2026). The county routes on 4 of 4.
- **Field triage:** Newgard et al., National Guideline for the Field Triage of Injured Patients, 2021 (*J Trauma Acute Care Surg* 2022).
- **Stroke systems of care:** 2026 AHA/ASA Guideline for the Early Management of Acute Ischemic Stroke (*Stroke* 2026).
