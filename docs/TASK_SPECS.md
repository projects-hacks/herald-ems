# Task specs for the handed-off work

These are the tasks moved out of Rajeev's lane (Wed 2026-09-23) into collaborators' full-stack lanes. Lanes are
feature slices: each owner builds the backend, the UI, and the tests for the feature. Each spec below is complete
enough for you and your coding agent to start without a meeting: goal, what to read, where the code goes, the steps,
the tests, the acceptance bar, what bites on this box, and anything only Rajeev can do.

## Rules that apply to every spec

1. **Read `AGENTS.md` first,** especially hard rules 1–4 and the pitfalls. Rule 4 is the architecture:
   - Code goes in the package that owns the responsibility (the layout table in AGENTS.md).
   - New dependencies are `typing.Protocol`s in `herald/core/ports.py`, wired once in `herald/api/context.py` (`build_context`).
   - Clinical and product content goes in `config/` with its source, never as Python literals.
   - Settings go in `herald/config/settings.py`.
2. **Work in your own clone** (`~/work/<handle>/herald-ems`) on a branch `feat/<lane>-<topic>`. Run your own server on your own port (8101–8104); **8100 is the demo instance**.
3. **Anything that touches `herald/` goes through a PR reviewed by Rajeev.** Keep PRs small: one step of a spec per PR is fine.
4. **Tests:**
   - `~/miniforge3/envs/zgx/bin/python -m pytest -q` must pass before every commit.
   - New code gets tests. For API tests, use `tests/fakes.py` (`make_client`, `FakeModel`, `FakeVision`, `FakeSTT`); never call a real model in tests.
5. **API contract changes** (new endpoints, new snapshot fields) are recorded in `docs/UX_PLAN.md` §5 in the same PR. Also add a line under "New in the contract" in TASKS.md.
6. **The shared Python environment is `zgx`** (torch 2.14.0+cu130, built for this GPU).
   - **Never let pip replace torch, torchaudio, or transformers.**
   - Install with a constraints file:
     ```bash
     PY=~/miniforge3/envs/zgx/bin/python
     $PY -m pip freeze | grep -iE "^(torch|torchaudio|torchvision|transformers|numpy)==" > /tmp/zgx-constraints.txt
     $PY -m pip install -c /tmp/zgx-constraints.txt <package>
     $PY -m pip check
     ```
   - If a package insists on a different torch, **stop and ask Rajeev**. Don't force it.
7. **The GPU is shared.**
   - Never restart `omni` or `ems-b` (`zrt status` shows them). Only Rajeev swaps models.
   - Small helper models (TTS, diarization) run in your own process; check `free -g` first.
8. **No AI attribution anywhere** (hard rule 1). **No real patient data**, and **no one's voice without their consent.**

---

## S1. UI fixtures: record the WebSocket sequences the UI is built against (B9 → Collaborator 1)

**Goal:** five recorded `/ws` message sequences in `ui/public/fixtures/`, so every frontend state can be built and tested on a laptop without the Nano. The REPLAY banner keeps them from being mistaken for live data.

**Read:** `docs/UX_PLAN.md` §5.7–5.8 (store and fixture player), `scripts/record_ws.py`, `scripts/replay.py` (`--url`, `--fast`, `--no-llm`), `scenarios/stroke_demo.json`.

**Steps** (on the Nano, your own port, e.g. 8101):
1. Start your server with the relay pointed at the emulated link:
   ```bash
   scripts/link.sh start 127.0.0.1:8200        # once; Toxiproxy :9000 -> ED receiver :8200 (already running on the Nano)
   HERALD_ED_URL=http://127.0.0.1:9000 HERALD_LLM_MODEL=ems-b PORT=8101 scripts/run_dev.sh
   ```
2. For each fixture, reset first (`curl -XPOST localhost:8101/api/incident -H 'content-type: application/json' -d '{"dispatch":"possible stroke"}'`), then start the recorder in a second terminal:
   `~/miniforge3/envs/zgx/bin/python scripts/record_ws.py ws://127.0.0.1:8101/ws ui/public/fixtures/<name>.jsonl`
3. Record:

   | Fixture | How |
   |---|---|
   | `stroke_demo` | `scripts/replay.py scenarios/stroke_demo.json --url http://localhost:8101`. Authorize the relay (`POST /api/relay/authorize {"destination":"Regional"}`), then switch the link weak → down → good (`POST /api/netem/{mode}`) during the replay |
   | `rules_only` | the same replay with `--no-llm` |
   | `model_error` | restart your server with `HERALD_LLM_MODEL=not-served` (every model phase fails and is recorded as `error`), then replay |
   | `photo` | `curl -XPOST localhost:8101/api/photo -F file=@eval/photos/synthetic_pill_warfarin.jpg -F mode=pill_bottle` |
   | `offline` | authorize the relay, set the link `down`, replay, and leave it down so updates queue |
4. Stop each recorder with Ctrl+C. Check each file: one JSON object per line, `t_ms` increasing, no `pong` messages (the recorder skips them).

**Acceptance:** all five files are committed. Each one replays in the fixture player (`?fixture=<name>`) and shows the intended state. They contain only synthetic scenario text.

**Pitfalls:** don't record on port 8100 (the demo instance), and never record a real person's speech.

---

## S2. Rebuild everything from a clean clone (I2 → Collaborator 1)

**Goal:** the Nano is wiped after the event. Anyone must be able to go from a clean `git clone` to a running Herald with one script and the README.

**Read:** `README.md`, `AGENTS.md` (Run, pitfalls), `scripts/serve_models.sh`, `scripts/run_dev.sh`, `requirements.txt`, `docs/UX_PLAN.md` §5.10 (`scripts/build_ui.sh`).

**Build `scripts/setup.sh`** (idempotent; every step prints what it did and what to do on failure):
1. **Check the platform:** aarch64 + `nvidia-smi` present, and the `zgx` conda env with torch 2.14 (print the version). If the env is missing, print the exact commands from AGENTS.md; don't try to build it.
2. **Python dependencies:** `pip install -c <constraints> -r requirements.txt` (the constraints recipe from rule 6), then `pip check`.
3. **Models:** `zrt status`. If `omni` or `ems-b` isn't serving, print the exact `zrt serve` commands. The flags are in `scripts/serve_models.sh`; the ems-b command is in `docs/MODEL_PLAN.md` §4. `HF_TOKEN` comes from `~/.config/herald/secrets.env`. Don't start models automatically: that takes 7–23 minutes and memory planning.
4. **UI:** if `ui/` exists, run `scripts/build_ui.sh`.
5. **Tests:** `python -m pytest -q`.
6. **Print the run commands:** the server, the ED receiver, the link emulator, replay.
7. Add a "From a clean clone" section to `README.md` that points at `scripts/setup.sh`.

**Acceptance:** `git clone` into `/tmp/herald-clean`, run `scripts/setup.sh`, and the tests pass. `PORT=8103 scripts/run_dev.sh` serves `/api/health`. The printed model commands match what `zrt status` shows. Rajeev re-runs it once to confirm.

**Pitfalls:** `sg zrt -c "…"` is needed in old shells. `set -euo pipefail` with `ssh -T` exits 1 even on success; capture its output instead (see `scripts/dev_git_setup.sh`).

---

## S3. Interpreter: Spanish ↔ English at the patient's side (P8 → Collaborator 2)

**Goal:**
- A Spanish-speaking patient or family member speaks. The medic sees the English, the facts land in the picture unconfirmed, and the Spanish original is kept as evidence.
- The medic types or says an English question, and Herald shows and speaks it in Spanish.

Everything runs locally.

**Read:** `herald/models/stt.py` (`WhisperSTT`), `herald/models/llm_client.py`, `herald/api/capture.py` (`CaptureService.text`), `herald/core/schema.py` (`Provenance`), `docs/UX_PLAN.md` §3.1.11 and §4.

**Design:**

| Piece | Where | Details |
|---|---|---|
| `Translator` interface | `herald/core/ports.py` | `translate(text: str, source: str, target: str) -> str` |
| LLM translator | `herald/models/translator.py` (`LLMTranslator`) | Uses the **vision/general model** (`ctx.vision_model`, i.e. `omni`), not the fine-tuned extractor. Prompt in `config/prompts/translate.md`: translate faithfully, add nothing, keep numbers, units, drug names and times exactly, return `{"translation": "..."}`. Strict JSON through `chat_json(schema=...)` |
| Language detection | `WhisperSTT.transcribe` | Return the detected language in the result dict (`language`). With `language=None` Whisper detects it; read it from the pipeline output (`return_language=True`), and add a test using a fake pipeline |
| Speech synthesis | `herald/core/ports.py` `SpeechSynthesizer.speak(text, lang) -> bytes (wav)`; `herald/models/tts.py` (`KokoroTTS`, `hexgrad/Kokoro-82M`, Spanish voice) | Runs on CPU or GPU in-process. The audio is saved as `data/audio/tts_<id>.wav` and served by the existing `GET /api/audio/{id}` |
| Provenance | `herald/core/schema.py` `Provenance` | Add `original_text: Optional[str]` and `language: Optional[str]`. Record it in UX_PLAN §5 |
| Patient speaks | `POST /api/interpret/listen` (audio, `speaker`) in a new router `herald/api/routes/interpret.py` | STT (detect) → if not English, translate to English → `CaptureService.text(english, captured_by=other, speaker=…)`, with `trace.heard` carrying `{original, language}` and provenance carrying the original. Facts from other speakers are already unconfirmed; keep it that way |
| Medic speaks | `POST /api/interpret/say` `{text, target:"es"}` | Translate + TTS → `{translation, audio_id}`. It is logged as a transcript entry of kind `interpreter` (heard = English, translation = Spanish). It is **not** a fact |
| Wiring | `herald/api/context.py` | `translator` and `tts` fields in `AppContext`, built in `build_context` (tests pass fakes) |
| UI | the interpreter panel on the NOW screen | Two big buttons ("Patient speaks" / "Say to patient"), the last exchange in both languages, and ▶ for the Spanish audio |

**Steps:**
1. Interfaces + `LLMTranslator` + prompt file + tests with a `FakeModel`.
2. Language detection in `WhisperSTT` + test.
3. `KokoroTTS`. **Install with constraints** (rule 6). Kokoro's Spanish G2P needs `espeak-ng`, **a system package: ask Rajeev to run `sudo apt install espeak-ng`**. If Kokoro can't install cleanly, ship the translation as on-screen text first and tell Rajeev.
4. Endpoints + provenance fields + trace + tests (`tests/test_interpreter.py`, using fakes for STT, translator and TTS).
5. UI panel.
6. **Measure:** 20 Spanish utterances with English gold facts, written by a Spanish speaker if one is on the team; keep them in `eval/interpreter_v1.jsonl`. Report fact F1 after translation vs English gold, and round-trip latency (speech in → English on screen; English in → Spanish audio out), 3 runs each.

**Acceptance:**
- A Spanish sentence ("Mi mamá toma Eliquis y es alérgica a la penicilina") becomes unconfirmed facts `meds.anticoagulant = apixaban` and `allergies = [penicillin]`, attributed to the speaker, with the Spanish original visible.
- An English question is spoken back in Spanish.
- Numbers are in MODEL_PLAN.

**Invariants:** translation never adds information. The original is always kept and viewable. No cloud calls: the translator uses `LocalLLMClient`, which refuses non-local URLs.

---

## S4. Speaker diarization: can one mic tell the medic from the family? (M8 → Collaborator 2)

**Goal:** measure whether `pyannote/speaker-diarization-community-1` (the model HP's Audio2Text and Doctor NoteAI use) correctly separates the medic from another speaker on two-speaker clips. If it's good enough, propose how Herald uses it. It would reduce reliance on the F key for "someone else is speaking".

**Needs Rajeev first:** the model is **gated on Hugging Face**. Rajeev must open https://huggingface.co/pyannote/speaker-diarization-community-1, signed in as `rajeev-chaurasia` (the token owner), and accept the conditions. Do the same for any model it lists as required.

**Steps:**
1. **Environment:** pyannote pins its own torch. Don't install it into `zgx`. Instead:
   ```bash
   ~/miniforge3/envs/zgx/bin/python -m venv --system-site-packages ~/work/<handle>/diar-venv
   ~/work/<handle>/diar-venv/bin/pip install -c /tmp/zgx-constraints.txt pyannote.audio
   ```
   The constraints are from rule 6. If pip can't satisfy them, write down the conflict and stop. That's a result ("won't install alongside torch 2.14 on aarch64"), not a failure of yours.
2. **Data:** 10 two-speaker clips, 20–60 s each, recorded by teammates (one plays the medic, one plays family), with consent. Script each clip, and write the gold turns (who spoke when, to about 0.5 s) in `eval/diarization_v1.jsonl`. Keep the audio in `data/field_audio/diarization/` (gitignored).
3. **Metrics** (`eval/diarization_bench.py`):
   - diarization error rate (`pyannote.metrics`);
   - **word attribution accuracy:** the share of Whisper words (word timestamps) assigned to the right person;
   - processing time per clip.
4. **Report** in MODEL_PLAN §3: a numbers table, and a go/no-go against the bar DER ≤ 15% and attribution ≥ 90%.
5. **If go:** write a design note (not code yet) for `herald/models/diarization.py` implementing a `Diarizer` port. Cover how turns become `captured_by=other` utterances, and how the medic's voice is identified (e.g. whoever holds push-to-talk is enrolled as "medic"). Rajeev decides whether to integrate.

**Acceptance:** numbers from 3 runs in MODEL_PLAN, and a go/no-go recorded.

---

## S5. Mass-casualty mode: several patients on one rig (P11 → Collaborator 3)

**Goal:** during a multi-patient call, the medic keeps a separate patient picture per patient and switches between them. On a weak link, the relay sends the most critical patient's updates first.

**Read:** `herald/core/incident.py`, `herald/api/context.py` (`AppContext.incident`, `new_incident`, `full_state`), `herald/relay/relay.py` (`Relay`, `pending`, `_build`), `config/relay.yaml`, `config/vocabulary.yaml`, `tests/test_relay.py`, `ed_receiver/app.py` (already keys everything by incident id `i`).

**Design:**

| Piece | Where | Details |
|---|---|---|
| Triage category | `config/vocabulary.yaml`: new key `triage.category` (`type: str`, `kind: measure`, `values: [immediate, delayed, minimal, expectant, dead]`) | The medic's SALT category, captured like any fact (tap or voice), so it has provenance. Add `values` support to `Vocabulary.validate` (reject values outside the list) with a test |
| Roster | `herald/core/roster.py` (`PatientRoster`) | `{patient_id: Incident}`, `labels`, `active_id`. Methods: `add(label) -> Incident` (via a factory the context passes in), `activate(id)`, `active()`, `summaries()` → `[{id, label, triage, summary, readiness_done, readiness_total}]` |
| Context | `herald/api/context.py` | `AppContext.roster`. Keep `AppContext.incident` as a **property returning the active incident**, so capture, trace and every existing route keep working unchanged. `new_incident()` resets the roster to one patient |
| Snapshot | `AppContext.full_state()` | Adds `patients` (the summaries) and `active_patient`. Record them in UX_PLAN §5 |
| API | `herald/api/routes/patients.py` | `GET /api/patients`; `POST /api/patients {label}`; `POST /api/patients/{id}/activate`. Captures go to the active patient (no change to capture routes) |
| Relay across patients | `herald/relay/relay.py` + `config/relay.yaml` | `Relay` takes a getter returning **all** incidents (keep single-incident construction working for existing tests). `config/relay.yaml` gains `triage_rank: {immediate: 0, delayed: 1, minimal: 2, expectant: 3, dead: 4, unknown: 1}`. Pending rows sort by (triage rank, tier, key). One packet still carries one patient (`i` = that incident's id), so the ED receiver needs no protocol change. `status()` reports per patient |
| UI | NOW screen patient strip; ED screen shows every incoming patient | A patient strip with the triage color and name, where tapping switches. The ED screen lists patients by triage rank |

**Steps:**
1. `triage.category` + `values` validation + tests.
2. `PatientRoster` + context property + tests (existing tests must pass untouched).
3. Routes + snapshot fields + tests.
4. Relay across patients + tests: **two patients, weak link: the immediate patient's critical update is sent before the minimal patient's.** Also: 0 duplicates / 0 lost across a flaky link with two patients (reuse the seeds in `tests/test_relay.py`).
5. UI (NOW strip, ED list).

**Acceptance:** the tests above pass; live on your port, two patients with different triage categories show the priority order in the relay log and on the ED screen. Contract documented.

**Pitfalls:** the relay loop runs in the background (`run_forever`), so keep `tick()` fast. Don't break the single-patient demo: it is the default and must look identical.

---

## S6. Medication and allergy normalization with RxNorm (B4 → Collaborator 3)

**Goal:** drug names reach the patient picture as standard generic names with an RxNorm code, whatever was said: a brand ("Lipitor"), a speech-to-text misspelling ("lipiter", "eloquis"), or a generic. This replaces the hand-written word lists (`config/lexicons.yaml` `anticoagulants`) with the national drug vocabulary: the approach production clinical systems use, and the coding NEMSIS uses (RxNorm) for medications and allergies.

**Read:** the research summary in `docs/MODEL_PLAN.md` (grounding and normalization); `herald/extraction/model.py` (the only speech extractor; the old rules merge is `eval/baselines/rules_plus_model.py`), `herald/models/vision.py` (uses `lexicons.yaml`); `config/vocabulary.yaml` (`meds.list`, `meds.anticoagulant`, `allergies`); the labeling guide §4 (generic, lowercase).

**Data:**
- **RxNorm Current Prescribable Content** from the NLM: https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html. It needs no UMLS licence.
- Download the latest monthly zip, and record its release date in `config/terminology.yaml`. If the download page requires a login you don't have, **ask Rajeev** (human in the loop).
- The build script writes to `data/terminology/`. Keep it out of git (add it to `.gitignore`), and record the rebuild command.
- **Anticoagulant class:** a reviewed list in `config/terminology/anticoagulants.yaml` with ATC codes as the source: B01AA vitamin K antagonists (warfarin); B01AB heparins (heparin, enoxaparin); B01AE direct thrombin inhibitors (dabigatran); B01AF direct factor Xa inhibitors (apixaban, rivaroxaban, edoxaban). Antiplatelets (B01AC: clopidogrel, aspirin, ticagrelor) are explicitly **not** anticoagulants.

**Design:**

| Piece | Where | Details |
|---|---|---|
| Build | `scripts/build_rxnorm_index.py` | From `RXNCONSO.RRF` (SAB=RXNORM; TTY in IN, PIN, BN, SCD, SBD, PSN, SY) and `RXNREL.RRF` (`tradename_of`, `has_ingredient`), build a map from every name (lowercase) to its **ingredient** (IN) name and RxCUI. Write SQLite or JSON to `data/terminology/` |
| Interface | `herald/core/ports.py` `Normalizer.normalize(key, value) -> NormalizedValue` (value, code, score, method) | |
| Implementation | new package `herald/terminology/` (`rxnorm.py`: `RxNormNormalizer`) | Match in order, stopping at the first hit: exact (casefold) → fuzzy (`rapidfuzz` ratio ≥ 90 on names ≥ 5 characters) → phonetic (`jellyfish` Double Metaphone; accept only a single candidate). Return the ingredient name (lowercase), the RxCUI, the score, and the method. **No match: keep the spoken text and mark it unresolved**, never guess |
| Where it runs | `ExtractionPipeline` (after extraction) and `VisionReader` (replacing its `lexicons.yaml` lookup) | Applies to `meds.list`, `meds.anticoagulant` (and derives it from `meds.list` when an item's ingredient is in the anticoagulant class), and drug `allergies`. The spoken form stays in `provenance.text` |
| Schema | `FactIn.code: Optional[str]` (RxCUI) | Record it in UX_PLAN §5; the UI shows it in fact details |
| Wiring | `herald/api/context.py` | Built once and injected. Tests use a tiny in-memory index |

**Steps:**
1. Install `rapidfuzz` and `jellyfish` with constraints (rule 6).
2. Download + build script + `config/terminology.yaml` (release, source URL).
3. Normalizer + unit tests: Lipitor → atorvastatin; lipiter → atorvastatin; eloquis → apixaban; cumadin → warfarin; Plavix → clopidogrel (and **not** an anticoagulant); "something for her thyroid" → unresolved.
4. Wire it into the pipeline and vision; delete the `anticoagulants` word list from `config/lexicons.yaml` once nothing reads it.
5. **Measure:** tune thresholds on **gold v1 (dev) only**. Then run `eval/bench_extract.py --gold eval/gold_v2.jsonl` **once** per extractor and report the med/allergy precision and recall before and after in MODEL_PLAN. **Never tune on gold v2**: it's the held-out set.

**Acceptance:** the unit tests pass; med and allergy recall on gold v2 improves with no precision loss beyond the run-to-run spread; the word list is gone.

**As built (2026-09-24; results in MODEL_PLAN §0g):**
- `jellyfish` has no Double Metaphone, so the phonetic step uses Metaphone plus a Levenshtein spelling floor.
- Coding runs inside each extractor rather than only in `ExtractionPipeline`, because the live capture path calls the rules and model extractors directly.
- `FactIn.code` is a list for list keys (one RxCUI per item).
- `config/terminology/supplement.yaml` adds Coumadin, which is missing from the prescribable subset.
- The anticoagulant class also lists fondaparinux (B01AX05), pending review.

---

## S7. 30-minute soak test and the pre-demo warm-up runbook (M5 → Collaborator 3)

**Goal:** prove the full stack runs 30 minutes under demo load without errors, drift or memory growth, and write the checklist the presenter runs before going on stage.

**Steps:**
1. **`scripts/soak.py`:** for 30 minutes, loop `scenarios/stroke_demo.json` against your port (reset the incident each loop), with the model on and the relay authorized through the link emulator. Every 30 s, record:
   - the model-phase latency from the trace (`trace.model.ms`), errors (`status == "error"`), and relay failures;
   - `free -g` and `zrt status` memory.
   Write `runs/soak_<date>.jsonl` and a summary.
2. Confirm the Omni server uses MARLIN kernels: `sg zrt -c "grep -i marlin /opt/hp/zrt/run/vllm-omni.log | head"`.
3. **`docs/RUNBOOK.md`** (link it from AGENTS.md's document map): the warm-up sequence. Measured on 2026-09-23: warm restart of Omni takes 7.6 min to ready; first request 1.6 s, then 0.9 s.
   - `zrt status` shows `omni` and `ems-b` Ready.
   - Send 3 warm requests to each.
   - `/api/health` shows `stt_loaded: true`.
   - The ED receiver answers `/ping`.
   - The link emulator is in `good`.
   - Replay once.
   - Reset the incident.

**Acceptance:** 30 minutes with 0 errors; p95 model latency in the last 5 minutes within 20% of the first 5; no memory growth over 1 GB. The runbook is rehearsed once by Collaborator 4.

---

## S8. Field robustness: real people, their own words, real noise (B8 → Collaborator 4)

**Goal:** answer the team lead's question with evidence: does Herald work when someone who isn't us speaks, in their own words, with noise? Every gold set so far is text. This one is **spoken**.

**Method:** the label is the card, not the speech.
1. **Cards** (`eval/field_cards_v1.jsonl`, 30 cards):
   - Each card is a short fact bundle a speaker must convey, e.g. "man, 72; left face drooping; BP 188 over 102; takes Eliquis; normal at 1:40". Speakers say it **in their own words**; no script.
   - Write the facts in the labeling guide's normalized form (`docs/LABELING_GUIDE.md`). Cover every call type and several attributions ("the wife says…").
   - Whoever writes the cards (a person or an agent) **must not read `eval/gold_*` files.**
2. **Recordings:** at least 5 people. Get consent, and tell them the audio stays on the Nano and is deleted after the event. Each person says 10 cards in two conditions: quiet, and with ambulance or road noise playing from a phone.
   - Record on a laptop mic at 16 kHz WAV. The NOW screen's push-to-talk or any recorder works.
   - Save as `data/field_audio/<person>/<card>_<quiet|noise>.wav`. That folder is gitignored; audio is personal data.
   - The manifest `eval/field_v1.jsonl` has one line per clip: card id, file, condition, speaker id (not their name).
3. **Scoring** (`eval/field_bench.py`): speech-to-text (`WhisperSTT`) → extractor (build it the way `eval/bench_extract.py` does) → score against the card with the same scorer (`atoms`, `score` from `eval/bench_extract.py`).
   - Report per-key precision and recall, the quiet vs noise difference, and bootstrap 95% confidence intervals, 3 runs.
   - If Python isn't your thing, do steps 1–2 and hand the manifest to Rajeev for step 3.
4. **Report** in MODEL_PLAN §5 (and a slide): "N people, M clips, own words, road noise: F1 …".

**Acceptance:** at least 5 speakers and at least 100 clips; numbers with confidence intervals in MODEL_PLAN.

**Pitfalls:** don't use judges' or strangers' voices without consent, and never real patients.
