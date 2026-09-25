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
5. **API contract changes** (new endpoints, new snapshot fields) are recorded in `docs/API_CONTRACT.md` in the same PR.
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

**Read:** `scripts/record_ws.py`, `scripts/replay.py` (`--url`, `--fast`, `--no-llm`), `scenarios/stroke_demo.json`.

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

**Read:** `README.md`, `AGENTS.md` (Run, pitfalls), `scripts/serve_models.sh`, `scripts/run_dev.sh`, `requirements.txt`, `docs/API_CONTRACT.md` (`scripts/build_ui.sh`).

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

**Read:** `herald/models/stt.py` (`WhisperSTT`), `herald/models/llm_client.py`, `herald/api/capture.py` (`CaptureService.text`), `herald/core/schema.py` (`Provenance`), `docs/API_CONTRACT.md` and §4.

> **Use `ctx.knowledge_model` for translation, not `ctx.vision_model` or `ctx.text_model`** (added 2026-09-25).
> It is a `TextModel` on the app context and is always set, so there is nothing to guard against. By default it *is*
> the photo-reading client, so today it behaves exactly as `ctx.vision_model` would. But if run F's fine-tune wins
> speech and photos while losing the base model's kept abilities, `HERALD_KNOWLEDGE_MODEL` moves translation,
> protocol reranking and figure transcription onto the untuned base model (`docs/TRAINING_PLAN.md` §7a; the operator
> procedure is `docs/RUNBOOK.md` §7). Reaching for `ctx.text_model` or `ctx.vision_model` instead would silently keep
> translation on the fine-tune and lose that protection. `tests/test_knowledge_model.py` pins the wiring.

**Design:**

| Piece | Where | Details |
|---|---|---|
| `Translator` interface | `herald/core/ports.py` | `translate(text: str, source: str, target: str) -> str` |
| LLM translator | `herald/models/translator.py` (`LLMTranslator`) | Uses the **vision/general model** (`ctx.vision_model`, i.e. `omni`), not the fine-tuned extractor. Prompt in `config/prompts/translate.md`: translate faithfully, add nothing, keep numbers, units, drug names and times exactly, return `{"translation": "..."}`. Strict JSON through `chat_json(schema=...)` |
| Language detection | `WhisperSTT.transcribe` | Return the detected language in the result dict (`language`). With `language=None` Whisper detects it; read it from the pipeline output (`return_language=True`), and add a test using a fake pipeline |
| Speech synthesis | `herald/core/ports.py` `SpeechSynthesizer.speak(text, lang) -> bytes (wav)`; `herald/models/tts.py` (`KokoroTTS`, `hexgrad/Kokoro-82M`, Spanish voice) | Runs on CPU or GPU in-process. The audio is saved as `data/audio/tts_<id>.wav` and served by the existing `GET /api/audio/{id}` |
| Provenance | `herald/core/schema.py` `Provenance` | Add `original_text: Optional[str]` and `language: Optional[str]`. Record it in `docs/API_CONTRACT.md` |
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

### S3 revision (Fri 2026-09-25): what changed since this spec was written. It overrides the table above where they differ.
1. **Spanish facts don't need translating first.** Run F trains the extractor on 829 Mexican Spanish lines
   (batches 32–39): Spanish speech goes **straight to the extractor**, which returns the same English canonical facts,
   and the Spanish utterance is already kept as the fact's evidence (`provenance.text`). Translation is for the medic
   to **read** (an English line under the Spanish on screen) and for **speaking to the patient**.
   - Keep a measured fallback: a setting `HERALD_INTERPRETER_FACT_PATH=direct|translate_first` (default `direct`).
   - Measure both on `eval/gold_es_v1.jsonl` (60 lines; command in `eval/README_gold_es.md`), 3 runs each, once
     `herald-f` serves. The better one is the default; write the numbers in MODEL_PLAN.
2. **The translator model and prompt already exist.** Use the served general model, `ctx.vision_model` (label
   `herald-f` after the switch; `qwen3vl-fp8` before), with **`config/prompts/translate.yaml`**, not a new
   `translate.md`: `system` plus the `directions.en_es` and `directions.es_en` templates.
   - Call it exactly the way `scripts/build_replay_set.py` does (`chat_json`, JSON mode, no strict schema). The
     fine-tuned model was trained to keep this ability with this exact request, so any other prompt is untested.
3. **TTS: use Piper, not Kokoro.** Piper is ONNX, runs on the CPU, needs no torch, and works on this box now.
   - Binary: `~/.venvs/piper-es/bin/piper`.
   - Mexican Spanish voices: `~/.venvs/piper-es/voices/es_MX-claude-high.onnx` and `es_MX-ald-medium.onnx`. English
     voices are in `~/.cache/piper-voices/` if a read-back is ever needed.
   - `PiperTTS` implements `SpeechSynthesizer`, calling the binary through `subprocess` (the paths are settings:
     `HERALD_TTS_BIN`, `HERALD_TTS_VOICE_ES`).
   - `espeak-ng` is now installed system-wide (1.51), so Kokoro is possible later, but Kokoro pulls torch and must
     never be pip-installed into the zgx env.
4. **Whisper changes stay with the model owner (Kiro, Phase 7): S3 only uses them.** Kiro changes
   `herald/models/stt.py`:
   - `WhisperSTT` returns the detected `language` in its result dict (keep the `transcribe_many` / `_mono16k` API);
   - the priming prompt depends on the language (no drug names for Spanish; "alergias" was heard as "Eliquis" in
     `runs/es_speech/whisper/report.json`);
   - a repetition-loop guard.

   S3 **does not edit `stt.py`**. Build the interpreter against a fake STT that returns `{"text", "language"}` and
   switch to the real one when Kiro's change lands.
5. **Safety check on every translation** (deterministic, no model):
   - every number, drug name and negation word in the source must appear in the translation; numbers are compared
     after the spoken-number parser, `config/numbers.yaml` en/es;
   - if one is missing, the screen shows "check the translation", and the Spanish audio **is not played
     automatically**; the medic can still tap ▶ after reading.
   - Herald only translates the medic's own words. It never writes its own questions or instructions to the patient
     (AGENTS invariant 3).
6. **No GPU until `herald-f` serves** (about Fri 3 AM PDT; the 30B is training). Build everything against fakes.
   - Whisper checks can run on the **CPU** now: `CUDA_VISIBLE_DEVICES=""` through
     `scripts/run_job.py --name s3-whisper-cpu --need-gib 6 -- …`, without `--gpu`, because the training run refuses
     other GPU jobs.
   - The translator and extractor measurements wait for `herald-f`.
7. **UI.** The React NOW screen is Tushar's. Build the interpreter panel as a separate component
   (`ui/src/features/interpreter/InterpreterPanel.tsx`: "Patient speaks" and "Say to patient" buttons, the last
   exchange in both languages, ▶ for the Spanish audio, the "check the translation" warning) against your contract in
   `docs/API_CONTRACT.md`, then tell Tushar where to place it. The React mic port (his list) is what "Patient speaks" records with;
   until it lands, use the classic `web/` push-to-talk path.
8. **Eval.** `eval/interpreter_v1.jsonl`:
   - 20 English medic lines (questions, instructions, reassurance) with reference Spanish;
   - 20 Mexican Spanish patient or family lines with reference English;
   - written independently of the training data (don't open `data/annotated`), reviewed by a Spanish speaker if one
     is on the team.

   Report, 3 runs each:
   - the safety-check pass rate (numbers, drugs and negations preserved);
   - a 0–2 human faithfulness score per line;
   - the round-trip latency (speech in → English on screen; English in → Spanish audio out).

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
| Snapshot | `AppContext.full_state()` | Adds `patients` (the summaries) and `active_patient`. Record them in `docs/API_CONTRACT.md` |
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
| Schema | `FactIn.code: Optional[str]` (RxCUI) | Record it in `docs/API_CONTRACT.md`; the UI shows it in fact details |
| Wiring | `herald/api/context.py` | Built once and injected. Tests use a tiny in-memory index |

**Steps:**
1. Install `rapidfuzz` and `jellyfish` with constraints (rule 6).
2. Download + build script + `config/terminology.yaml` (release, source URL).
3. Normalizer + unit tests: Lipitor → atorvastatin; lipiter → atorvastatin; eloquis → apixaban; cumadin → warfarin; Plavix → clopidogrel (and **not** an anticoagulant); "something for her thyroid" → unresolved.
4. Wire it into the pipeline and vision; delete the `anticoagulants` word list from `config/lexicons.yaml` once nothing reads it.
5. **Measure:** tune thresholds on **gold v1 (dev) only**. Then run `eval/bench_extract.py --gold eval/gold_v2.jsonl` **once** per extractor and report the med/allergy precision and recall before and after in MODEL_PLAN. **Never tune on gold v2**: it's the held-out set.

**Acceptance:** the unit tests pass; med and allergy recall on gold v2 improves with no precision loss beyond the run-to-run spread; the word list is gone.

**As built (2026-09-24; results in MODEL_PLAN §0j, contract in `docs/API_CONTRACT.md`):**
- `jellyfish` has no Double Metaphone, so the phonetic step uses Metaphone plus a Levenshtein spelling floor.
- Coding runs inside the model extractor and the photo reader (injected from the composition root through `herald/terminology/factory.py`), and on `POST /api/facts`. There is no rules path in the product any more.
- Drug keys are content: `config/terminology.yaml` `keys` lists the list keys, record fields (`meds.given.drug`) and class files. Adding a key or a class is a config change.
- `FactIn.code` is a FHIR-style `Coding {system, code}`, a list for list keys (one per item). Class allergies ("sulfa", "penicillin") get NEMSIS eHistory.06's ICD-10-CM Z88 codes.
- A trailing strength is dropped only with a unit; numbered products match RxNorm product names ("Tylenol 3" → acetaminophen / codeine) or stay unresolved.
- Combinations ("ipratropium-albuterol") and words RxNorm uses only in product names ("nitro spray") resolve too (team lead, 2026-09-24). Every non-exact match waits for the medic's tap with the reason (`provenance.hold_reason`).
- The release is pinned (dated URL + sha256). Brands missing from the prescribable subset (Coumadin, and retired ones like Zofran and Vicodin) come from NLM's public RxNav API at build time, cached; the hand supplement is gone.
- The labeling guide now names drugs by RxNorm ingredient; two gold labels were renamed to match (§0j).
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

## S9. Agentic capture: Herald decides when to look (U-capture → Tushar)

**Goal.** Herald's eyes work without the medic. A camera (the tablet or phone on a mount, or a USB camera on the box)
feeds frames to the backend. A cheap filter drops almost all of them. An **agent policy** decides when a frame is
worth reading (the monitor changed; speech mentioned a drug being given or a POLST; a new alert; the handoff is
near). The chosen frame goes to the vision model, and the facts land in the patient picture **unconfirmed**, with the
frame as evidence. A **"Show Herald"** button keeps the manual path. **Vision also checks speech:** when the medic
says a drug is being given, Herald reads the vial label in view and flags a mismatch ("said naloxone, label reads
ondansetron").

**Why.** Voice gives actions and history, and vision gives readings and documents. The medic has no free hands to
take photos in an emergency, so the agent captures and proposes, and the medic only confirms. This is the product's
"copilot, not autopilot" line made visible.

**The agent's limits (invariants; tests enforce them):**
- It **may** decide when to capture, pick the frame, read it, add unconfirmed facts, attach evidence, flag a
  mismatch, and refresh vitals and trends.
- It **never** confirms its own readings (photo facts always start unconfirmed: AGENTS.md invariant 4), never acts on
  the patient, never recommends, and never changes a spoken fact because of what it saw. A mismatch is a flag the
  medic resolves.
- **No video goes to the model.** Only chosen still frames do, and speech always has priority on the GPU.
- **Privacy.** Frames live in memory only (a few-second ring buffer). A frame is written to disk only if it produced a
  fact or a flag, and faces are blurred before it is stored. The camera is aimed at the equipment and the stretcher
  area. An on-screen "Herald sees" indicator shows whenever it's on, and it can be switched off. It is off by default.

**Constraints:**
- The 30B is being trained until about Fri 2–3 AM PDT, so **no model or GPU load during development.** Build and test
  everything against fakes (`tests/fakes.py`) and a replay frame source. The real-model check happens after
  `herald-f` serves.
- The deadline is Fri 11 PM PDT.
- Follow AGENTS.md rule 4: package by responsibility, interfaces in `herald/core/ports.py`, wiring only in the
  composition root, content in `config/`, settings in `herald/config/settings.py`, and the API contract recorded in
  `docs/API_CONTRACT.md` in the same PR.
- Work in your own clone (`~/work/tushar-fs/herald-ems`) on branch `feat/agentic-capture`; commits as you; PR to main.

### Design (package `herald/capture/`, one responsibility per module, each under ~300 lines)

| Module | Responsibility | Key types |
|---|---|---|
| `herald/core/ports.py` | Interfaces: `FrameSource.frames() -> Iterator[Frame]` and `close()`; `IncidentListener.on_change(event: IncidentEvent)` | `Frame(id, ts, jpeg: bytes, w, h, source)` and `IncidentEvent(kind: facts_added\|alert_new\|eta_changed, facts, summary_diff)`, dataclasses in `herald/capture/types.py` |
| `sources.py` | Frame sources behind `FrameSource` | `BrowserFrameSource` (frames pushed from a page over the WebSocket below), `LocalCameraSource` (USB/V4L2 camera on the box via OpenCV, optional), `ReplayFrameSource` (a folder of JPEGs at a given fps: tests and demo rehearsal) |
| `gate.py` | The cheap filter; numpy + PIL only; about 5 ms per frame at 320 px grey | `FrameGate.assess(frame, roi) -> GateResult(sharp: float, changed: float, bright: float, passed: bool, reason)`. Sharpness is the variance of a 3×3 Laplacian; change is the mean absolute difference against the last *accepted* frame inside the ROI; brightness rejects frames that are too dark or blown out. Thresholds come from config. |
| `buffer.py` | Ring buffer of the last N seconds of gated frames; pick the best frame in a time window | `FrameBuffer.add(frame, gate)` and `best(since, until, roi=None) -> Frame \| None` (the sharpest frame that passed the gate) |
| `policy.py` | **The agent's decision rules, from config:** which event triggers which capture | `CapturePolicy.on_event(event) -> list[CaptureIntent]` and `on_tick(now, gate_state) -> list[CaptureIntent]`; `CaptureIntent(trigger, mode, window_s, roi_target, purpose: record\|verify)` |
| `scheduler.py` | Rate limit and priority | A token bucket (default one automatic vision call per 10 s; manual captures bypass it); at most one automatic vision request in flight; **skips when a speech extraction is running** (`ctx.text_model` busy flag, or a counter of in-flight `_extract` tasks in `CaptureService`) |
| `verify.py` | Deterministic check of speech against vision (no model) | `DrugCheck.compare(dose_fact, frame_facts) -> match\|mismatch\|unreadable`, comparing RxNorm-coded drug names (both sides go through the existing `ctx.coder`). A match attaches the frame as evidence on the dose record. A mismatch sets a hold on the dose ("Said naloxone; label seen: ondansetron: check before confirming") and raises a caution-level check item. Unreadable does nothing. |
| `privacy.py` | Face blur and storage decisions | `blur_faces(jpeg) -> jpeg` (OpenCV Haar frontal-face cascade shipped with OpenCV, Gaussian-blur each box); `store(frame) -> photo_id` only for frames that produced a fact or a flag, written to `settings.photo_dir / "auto"` (gitignored, like `data/photos/*`) |
| `agent.py` | Orchestration: consumes frames, runs the gate and buffer, asks the policy, schedules, calls `CaptureService.photo(...)`-style reading, runs `DrugCheck` for verify intents, records the trace | `CaptureAgent.start()/stop()`, an asyncio task in the app; `last_decisions` for the status endpoint |

**Where it plugs in:**
- `herald/api/capture.py`: add an observer list. After `ingest_batch` and in `_extract` (after the model's facts
  land), emit `IncidentEvent(facts_added, facts, tracer.diff(before, after))`. When the summary diff shows a new
  alert, emit `alert_new`; when `transport.eta_min` changes, emit `eta_changed`. `CaptureAgent` registers as a
  listener in the composition root (`herald/api/context.py`). This is the only change to existing capture code.
- **Reading a chosen frame** reuses the photo path, `CaptureService.photo(raw, mode)`, extended with provenance
  arguments: `trigger`, `frame_id`, `auto=True`. The trace entry kind stays "camera", with `trigger`, `reason` and a
  thumbnail id.
- **Verify intents** (a drug given by the crew) read the frame with the `pill_bottle` prompt but **do not add
  `meds.list` facts** (a vial being drawn up is not a home medication). They feed `DrugCheck` only.
- **Record intents** (monitor, bottle bag, POLST) add facts as usual: monitor → vitals, bottles → `meds.list`, form →
  `code_status`. Photo facts are unconfirmed.
- **Duplicate suppression for the monitor:** if every value read equals the latest fact for that key and the last
  monitor fact is under `max_interval_s` old, add nothing (log "unchanged"). Trends still get a point at least every
  `max_interval_s`.
- **ROI (region of interest).** The medic (or the demo operator) draws a box around the monitor once on the camera
  preview, then `POST /api/capture/roi`, stored per incident. Monitor captures are cropped to the ROI (plus a 10%
  margin) before reading, which matters because a mounted camera sees the monitor small. Without an ROI, monitor
  watch is off and only speech-triggered and manual captures run.

### Content: `config/capture.yaml` (reviewed data, with a comment on every number)

```yaml
fps_in: 1                      # frames the source sends per second
gate: {sharp_min: 60, change_min: 0.06, bright_min: 25, bright_max: 235, width: 320}
buffer_s: 6
rate: {auto_calls_per_s: 0.1, max_in_flight: 1, skip_while_speech: true}
monitor: {roi_margin: 0.10, stable_frames: 2, min_interval_s: 15, max_interval_s: 60}
triggers:                      # the agent's rules: event -> capture. Keys come from the MODEL's facts, not phrases.
  - {on: fact, key: meds.given, where: {by: crew}, mode: pill_bottle, purpose: verify, window_s: 8}
  - {on: fact, key: meds.list, mode: pill_bottle, purpose: record, window_s: 8}
  - {on: fact, key: meds.anticoagulant, mode: pill_bottle, purpose: record, window_s: 8}
  - {on: fact, key: code_status, mode: form, purpose: record, window_s: 10}
  - {on: alert_new, mode: monitor, purpose: record}
  - {on: eta_changed, when: {lte: 5}, mode: monitor, purpose: record, once: true}
suppress_during: [cpr_in_progress]        # a checklist/state id, if present: record-only monitor captures continue
privacy: {store: used_only, blur_faces: true, dir: auto}
```

**Why triggers use the model's facts and not phrase lists:** AGENTS.md says extraction fixes go into the model, not
regexes. The model already turns "drawing up 0.4 of Narcan" into a `meds.given` record, so the agent reacts to that
record, not to words.

### Settings (`herald/config/settings.py`)
- `HERALD_CAPTURE_SOURCE`: `off` (default), `browser`, `local:/dev/video0` or `replay:<dir>`.
- `HERALD_CAPTURE_AUTO`: `0` (default) or `1`, the starting state of the switch.
- The config file path, if needed.

### API contract (record all of it in `docs/API_CONTRACT.md`, with TypeScript types)
- `WS /ws/frames`: binary JPEG messages from the capture page (≤ 1280 px long side, ≤ `fps_in`). The server replies
  `{accepted, gate: {sharp, changed, passed}}` at most once a second, for the preview indicator.
- `GET /api/capture/status` → `{auto, source, fps_in, roi, last: {ts, trigger, mode, reason, facts, photo_id} | null,
  counts: {frames, gated, captured, stored}}`.
- `POST /api/capture/auto {on: bool}`: the on/off switch. Off stops everything, and the buffer is cleared.
- `POST /api/capture/roi {x0, y0, x1, y1}` (normalized 0–1, target `monitor`); `DELETE` clears it.
- `POST /api/capture/now {mode?: monitor|pill_bottle|form|scene}`: the manual "Show Herald" button. It takes the best
  frame of the last 2 s (or the next frame), bypasses the gate and the rate limit, and uses the same read path.
- **Snapshot:** add a `capture` block (`auto`, `source`, `sees: off|watching|reading`, and the last decision). Trace
  entries for automatic captures carry `trigger`, `reason` ("monitor changed 12%", "speech: fentanyl given → read the
  vial label", "new alert: STEMI → monitor"), `photo_id` and the facts.
- **A dose record with a mismatch** carries `provenance.hold_reason` and a `verify: {status: mismatch|match,
  label_drug, photo_id}` field on its fact view.

### Capture page (`web/capture.html`, served by the backend) and NOW screen (`ui/`, Tushar)
1. **Capture page, continuous mode:** `getUserMedia` (rear camera), draws to a canvas, sends a JPEG every
   1/`fps_in` s over `/ws/frames`, and shows a live preview with the ROI drawn.
   - **Secure context needed:** `getUserMedia` works only on HTTPS or localhost. Options: run the page on the
     presenter laptop via `http://localhost:<port>` (SSH port forward, as for the mic), or serve HTTPS with a
     self-signed certificate (a setting). Document both. The existing one-tap photo mode (`<input capture>`) stays
     as the fallback.
   - **Drawing the ROI:** drag a box on the preview → `POST /api/capture/roi`.
2. **NOW screen:**
   - **"Herald sees" indicator:** off (grey), watching (steady), or reading (pulse, while a vision call runs).
     Colors and motion follow the screen rules in AGENTS.md; this is status, not an alarm.
   - **On/off toggle.**
   - **"Show Herald" button**, with a mode picker defaulting to auto (monitor if an ROI is set, else label).
   - **Trace cards for automatic captures:** thumbnail, trigger and reason, facts proposed, and confirm taps
     (unchanged).
   - **Mismatch:** a caution-level check item on the dose ("Said naloxone · label: ondansetron"), with the thumbnail
     and the two actions "Keep as said" or "Edit"; the medic decides. A match shows a small "label seen ✓" badge on
     the dose.

### OpenCV (face blur, optional camera source)
There's no `cv2` in the zgx env. Install **without dependencies** so pip can't touch numpy or torch: first
`~/miniforge3/envs/zgx/bin/pip install --dry-run --no-deps opencv-python-headless` (check the version), then the real
install with `--no-deps`, and `python -c "import cv2, numpy, torch; print(cv2.__version__, numpy.__version__,
torch.__version__)"` before and after (torch and numpy versions must not change).
- If the wheel can't import against the env's numpy, keep `blur_faces` behind a feature check, set
  `privacy.store: none` (keep no frames at all; facts keep a text provenance), and report it.
- `LocalCameraSource` is optional; the browser source is the demo path.

### Tests (fakes only, no GPU)
- **`tests/test_capture_gate.py`:** sharp vs blurred frames (synthesize with PIL blur), change detection inside vs
  outside the ROI, too dark or too bright.
- **`tests/test_capture_policy.py`:**
  - every trigger in the config maps to the right intent;
  - a `meds.given` fact by family (not crew) does not trigger verify;
  - `eta_changed` fires once at ≤ 5;
  - suppression works.
- **`tests/test_capture_scheduler.py`:** the token bucket, one in flight at most, a skip while speech is in flight,
  manual captures bypass it.
- **`tests/test_capture_verify.py`:** match, mismatch and unreadable. Both sides coded with the real RxNorm coder, as
  in `tests/test_build_train_set.py`, so "Narcan" and a "naloxone hydrochloride" label match. A mismatch sets the hold
  and never changes the dose value.
- **`tests/test_capture_agent.py`,** with `ReplayFrameSource` and a `FakeVision` that returns canned facts per frame
  id, driving the app through the HTTP API:
  - monitor changes → new unconfirmed vitals with trigger `monitor_changed`;
  - unchanged frames → no duplicates;
  - "we're drawing up 0.4 of Narcan" (fake extractor returns `meds.given` by crew) plus an ondansetron label frame in
    the window → a mismatch flag on the dose and no `meds.list` fact;
  - a matching label → evidence attached;
  - `POST /api/capture/now` works with auto off;
  - auto off → zero vision calls;
  - privacy: no files written for frames that produced nothing; stored frames went through `blur_faces`.
- **The contract test** (`tests/test_contract.py` pattern): the new snapshot fields and trace fields exist and are
  typed.
- **`python -m pytest -q`** passes (the whole suite).

### Demo replay
`scenarios/auto_capture_demo.json` plus `scenarios/frames/auto_capture/` (synthetic frames: render monitor frames
with `scripts/vision_train` renderers or pick from `eval/photos`; a vial label frame; a POLST frame from
`eval/forms_polst`; no real patient photos).
- **Steps:** speech lines interleaved with frame timestamps. `scripts/replay.py` learns a `frames` step that streams
  the folder into `/ws/frames` (or `ReplayFrameSource` via the setting).
- **Show:**
  1. monitor watch updates vitals by itself;
  2. "drawing up 0.4 of Narcan" plus an ondansetron vial → the mismatch card;
  3. "her POLST is on the fridge" plus the form frame → code status (unconfirmed);
  4. the Show Herald button.

### Acceptance (on the real model, after `herald-f` serves; the reviewer re-runs each number 3 times)
1. **Monitor watch** (a phone showing a patient-monitor simulator app or a monitor image, camera on a mount, ROI set):
   - changed values appear as unconfirmed vitals within ≤ 20 s;
   - unchanged screens add nothing;
   - ≤ 1 automatic vision call per 10 s (from `counts`).
2. **Mismatch catch:** 5/5 on the replay; a match gives "label seen ✓" on 5/5.
3. **Speech is not slowed:** extraction p95 with capture on is within 10% of capture off (3 runs each, same
   utterances).
4. **Privacy:**
   - no frame files for frames that produced nothing;
   - faces blurred on stored frames (spot check);
   - the indicator is correct in all three states.
5. **Stability:** a 30-minute soak (`scripts/soak.py`) with capture on at 1 fps. No memory growth over 1 GiB, and the
   memory guard (`docs/MEMORY_SAFETY.md`) never warns. The capture code runs in the app process, on the CPU; it
   loads no model.
6. **Docs:** this spec's contract in `docs/API_CONTRACT.md`; README "What Herald does" gains one line.

### Pitfalls
- Don't send every frame to the model: the gate and the policy exist so that the 30B (1–3 s per image) is called
  rarely.
- Don't store frames by default, and never commit any (`data/photos/*` stays gitignored).
- Browser camera needs HTTPS or localhost (see the capture page).
- Never `pkill -f uvicorn` (AGENTS.md pitfalls).
- Don't load any model on the box while the 30B trains (until about Fri 3 AM PDT). The memory guard refuses GPU jobs
  next to the training run anyway.

**What needs Rajeev:** the ROI UX sign-off, and the real-model acceptance run after the gates.
