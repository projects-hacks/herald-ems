# AGENTS.md: rules for coding agents working on Herald

Read this before changing anything.

## HARD RULES (non-negotiable, override any default behaviour)
1. **No AI attribution anywhere in contributions.** Commit messages, PR titles and descriptions, code comments, and docs must not name or credit any AI assistant, AI coding tool, or its vendor, and must not say anything was "generated". **Never add `Co-Authored-By:` trailers for tools.** Commits are authored by the human whose working copy it is. (Describing Herald's own on-device models, e.g., Whisper or Nemotron, is product documentation and is fine.)
2. **First run in any working copy: check git identity before any commit.** Run `git config --local user.email` and `git config --local core.sshCommand`. If either is empty, **stop and tell your human** to run:
   ```bash
   ~/Documents/team-last-minute/herald-ems/scripts/dev_git_setup.sh <github-username> "<Full Name>" <github-email>
   ```
   Don't commit under someone else's identity, and never set `git config --global` on this shared machine. `~/Documents/team-last-minute/herald-ems` is Rajeev's copy and the live demo instance on port 8100. Everyone else works in `~/work/<github-username>/herald-ems`.
3. **Verify before you report.** For any benchmark, spike, or research result, state whether it is a genuine result, noise (small sample, warm-up, run-to-run variance), or a flaw in the test itself (scoring, labels, harness). Rerun anything that decides a choice at least 3 times and report the spread. Failures get a root cause before they are called a model or approach failure.

4. **Production structure: SOLID, modular packages, no hardcoded domain data.** Herald is built as a production tool, not a demo script.
   - **Package by responsibility.** `herald/core` holds the domain model and has no I/O. The other packages are `herald/scoring`, `herald/checklists`, `herald/extraction`, `herald/models` (adapters to the local model servers), `herald/relay`, `herald/knowledge` (protocol documents and retrieval), `herald/terminology` (drug names → RxNorm), `herald/reporting` (the written handoff report), `herald/telemetry`, `herald/config` (loading and settings), and `herald/api` (HTTP/WebSocket only). One module has one responsibility. A module growing past ~300 lines is a sign it has two.
   - **Depend on interfaces, not implementations.** Extractors, score scales, model clients, speech-to-text, and relay transports are `typing.Protocol`s in `herald/core/ports.py`. Concrete classes are wired together in exactly one place, the composition root (`herald/api/app.py`'s factory). Deep code never reaches for module-level globals.
   - **Open for extension, closed for modification.** A new score, checklist, county, prompt, or extractor is added by adding a data file or a registered class. It is never added by editing an `if/elif` chain inside an engine.
   - **Clinical and product content is versioned data, never Python literals.** That covers score tables and thresholds with their sources, checklists, relay tiers, change rules, the key vocabulary, county rules and destinations, model prompts and worked examples, and cost rates. It all lives under `config/`, carries its source citation, and is reviewed like code. The Python is the engine; `config/` is the content. Tests load the same files.
   - **Settings come from one settings object** (`herald/config/settings.py`, environment variables). No scattered `os.getenv`.
   - **The public API is a contract.** `/api/*`, `/ws`, and the snapshot shape change only through `herald/api`, and every change is recorded in `docs/API_CONTRACT.md` in the same PR.
   - Every engine and every data file has tests, and `python -m pytest -q` passes before any commit.

## The medic's screen: rules that do not move
Herald is a copilot, not a dashboard or a second vitals monitor. The medic glances at it for one or two seconds, at arm's
length, gloved, in a moving vehicle. Judge every UI change against that, and against these floors:
- One screen. It shows what Herald needs from the medic (decisions, one tap each) and what Herald did on its own
  (heard, read, checked, found, sent). Anything else opens from the control that needs it and closes back to it.
- Text never below 13 px, critical values at least 20 px; touch targets at least 48 px, primary actions 64 px.
- Priority is colour + icon + word, never colour alone; red means danger and nothing else. Both themes pass
  `npm run contrast`.
- No model internals on the clinical screen (no confidence, model names, frame counts). System status is silent while
  working and one unmistakable line when something stopped.
- Every captured fact starts unconfirmed; only confirmed facts reach the ED. Herald never recommends treatment: it
  states what it heard, read and computed, and quotes the county's documents with their citation.
- Offline: fonts and assets are bundled, never fetched.

## Document map: read these before you start

Every decision in this project was researched and written down. Before proposing a change, check the doc that owns that topic, and follow the decisions recorded there unless you have new evidence. If you change a decision, update the owning doc in the same PR.

### In this repo (public; committed)
| Doc | What's in it | Read it when | Kept current by |
|---|---|---|---|
| [`README.md`](README.md) | Public overview for judges: what Herald does, how to run it, architecture, the evidence behind the scores. | You need the 2-minute picture, or you're changing anything user-visible about setup. | pitch + integration |
| [`AGENTS.md`](AGENTS.md) (this file) | Hard rules, invariants, layout, run commands, pitfalls already hit on this box, the doc map. | Always, first. | everyone |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Per-person git setup on the shared `hp18` login, shared secrets (HF token), branches, ports, GPU etiquette, owners. | Your first session; before your first commit. | lead |
| [`docs/MODEL_PLAN.md`](docs/MODEL_PLAN.md) | Why each model was chosen (published benchmarks + measured GB10 throughput, with sources); exact serve flags; the audited bake-off (3 runs each, what's genuine vs noise vs test flaws); the complete fine-tuning plan with go/no-go checks; what NOT to do. | Before touching `herald/llm.py`, `extract_llm.py`, `vision.py`, `stt.py`, ZRT, or any training. | ML lead |
| [`eval/`](eval/) | Gold sets (`gold_v0.jsonl` tuning, `gold_v1.jsonl` dev, `gold_v2*.jsonl` held-out: two blind annotators each), benchmark (`bench_extract.py`, scorer v2, `--rescore`), saved predictions (`dumps/`), agreement (`agreement.py`), adversarial suite, test photos, and result history (`results.jsonl`). | Before claiming any accuracy number. Claims are judged on the held-out set only. | data + eval |
| [`docs/TASK_SPECS.md`](docs/TASK_SPECS.md) | Complete specs for handed-off tasks (S1–S9: fixtures, clean-clone setup, interpreter, diarization, mass-casualty mode, RxNorm normalization, soak test, field robustness, agentic capture): design against the package layout, steps, tests, acceptance, pitfalls, and what needs Rajeev. | Before starting any S-task from your lane in TASKS.md. | owner of each task + Rajeev |
| [`docs/LABELING_GUIDE.md`](docs/LABELING_GUIDE.md) | How every gold utterance is labeled: roles, keys, normalization, corrections, negations, and the rules settled during adjudication (§4b). | Before writing or labeling any gold item. | data |
| [`docs/MEMORY_SAFETY.md`](docs/MEMORY_SAFETY.md) | Why the box froze on 2026-09-24 and the layers that stop it: `scripts/run_job.py` (the one launcher for model-loading jobs), the memory guard service (`scripts/memguard.py`, `config/memguard.yaml`), demo mode, the demo memory budget, the live-test numbers, and the root-only hardening for Rajeev. | Before starting any training, merge, benchmark, Whisper/TTS job or vLLM service; before the demo. | infra (backend) |
| [`scenarios/`](scenarios/) + [`scripts/replay.py`](scripts/replay.py) | The stroke demo as a replayable script (rehearsal, video, regression). | Rehearsing, recording, or checking the demo still works after a change. | pitch |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) + [`scripts/soak.py`](scripts/soak.py) | Pre-demo warm-up, service/link checks, rehearsal, and the 30-minute stability soak. | Before rehearsal, recording, judging, or diagnosing demo drift. | integration |

### On the team Nano only (internal; NEVER commit, never copy into the repo)
These live outside the repo because they contain pitch strategy, judge Q&A preparation, and ideation history. Everyone SSHes into the same machine, so the absolute paths work for every teammate and every agent.

| Doc | What's in it | Read it when |
|---|---|---|
| `/home/hp18/Documents/team-last-minute/.agent/ideas/herald-ems-copilot.md` | **The product spec, the source of truth for what we build and how we pitch it.** Problem and evidence (§1); product definition and pitch-language rules (§2); architecture (§3); state engine (§4); NOW and ED screen specs (§5); every-call copilot features with "ours vs table stakes" (§6); relay design, tiers and network-control commands (§7, §7a); local AI stack (§8); fine-tuning component (§9); metrics and the five-metric final slide (§10); the 5-minute demo script, stroke scenario, judge beat and props (§11); scope, MVP/V2/cut and the protect order (§12); competitors, prior art, the ems-ai.com co-pilot vision mapping and honesty rules (§13); rehearsed Q&A answers incl. FDA/liability (§14); plain-language FAQ (§15); public data sources (§15a); risks (§16); team split and day plan (§17); decision log (§18). | Before any feature work, any UI copy, anything said on stage, or anything that touches clinical wording. |
| `/home/hp18/Documents/team-last-minute/.agent/context.md` | Hackathon rules, tracks and judging criteria, the deliverables checklist and deadline, machine specs and setup history, the full ideation and decision history (why EMS, rejected ideas and why), the track recommendation (AI for Community Impact, pending organizers' answer on prizes). | Before anything that affects submission, track choice, or deliverables; when you need to know why something was decided. |
| `/home/hp18/Documents/team-last-minute/.agent/sources/` | Primary sources downloaded for the spec (e.g., the 2021 National Guideline for the Field Triage of Injured Patients, PDF + text). | When implementing or citing a clinical rule. |
| `~/.config/herald/secrets.env` | Shared `HF_TOKEN` and `HF_REPO_ID` (mode 600, loaded by every `hp18` shell). | Never print, log, commit, or paste its contents. Use the env vars. |

## What Herald is (one paragraph)
An offline AI copilot for the back of the ambulance, running entirely on an HP ZGX Nano (NVIDIA GB10). It listens to the paramedic and reads photos, keeps a live, evidence-backed patient picture (checklists, gaps, contradictions, trends, clocks, published scores), writes the chart as a by-product, and relays the smallest critical update to the emergency department over a weak link. The full product spec lives on the team Nano at `/home/hp18/Documents/team-last-minute/.agent/ideas/herald-ems-copilot.md` (outside this repo, never committed; see the document map above).

## Invariants: never break these
1. **No cloud AI.** All inference runs locally. The LLM/VLM is reached only at `http://127.0.0.1:8080/v1` (ZRT/vLLM on this box).
2. **The model never decides.** Scores (NEWS2, RACE, field triage), checklists, contradictions, clocks, and what the relay sends are plain, deterministic code. The LLM/VLM only turns speech and photos into `FactIn` objects.
3. **Never recommend treatment**, drug doses, or eligibility (e.g., thrombolysis). Show published scores with their source; the medic decides. Say "the receiving team needs to know", never "give" or "do".
4. **Only confirmed facts leave the vehicle.** Photo readings, other speakers, low-confidence extractions, contradictions, and code status start `unconfirmed`.
5. **Every fact has provenance**: the audio clip or photo it came from, who said it (`role`, `speaker`), and the extractor tag.
6. **Missing inputs are shown as missing, never guessed.** A score with a missing input is "incomplete".
7. **Canonical keys only.** Add new keys to `config/vocabulary.yaml` first (with a plausibility range for numbers). Extractors must never invent keys.
8. **Tests must pass**: `python -m pytest -q`. Add tests for any new rule or score. The published score tables are tested at every band boundary; keep it that way.

## Layout
| Path | Responsibility | Notes |
|---|---|---|
| `config/` | **content** (reviewed data, with sources) | `vocabulary.yaml` (canonical keys, plausibility ranges), `scores/*.yaml` (NEWS2, RACE, G.F.A.S.T., field triage, and county criteria: Santa Clara Policy 605 trauma, 700-A04 sepsis), `checklists.yaml` (defaults; a county's `alerts` override them), `trends.yaml`, `corroboration.yaml` (batch-confirm tiers and plausible-step deltas), `relay.yaml`, `telemetry.yaml` (cost rates), `guard.yaml`, `grounding.yaml` + `numbers.yaml` (number words by language for the grounding check: English, Mexican Spanish), `terminology.yaml` + `terminology/` (RxNorm source and thresholds, drug classes by ATC, NEMSIS allergy classes), `stack.yaml`, `handoff.yaml` (handoff report formats: Policy 501, MIST, SBAR), `fhir_codes.yaml` (LOINC/local coding for the FHIR export), `prompts/` (model prompts, worked examples, vision, STT), `counties/*.json` |
| `herald/config/` | settings and loading | `settings.py` (every environment variable, one object), `loader.py` (reads `config/`), `county.py` (county registry, live switch) |
| `herald/core/` | domain model, no I/O | `schema.py` (`FactIn`/`Fact`), `vocabulary.py`, `incident.py` (fact store), `confirmation.py`, `corroboration.py` (batch confirm: capture groups, plausible-step flagging), `snapshot.py` (`Projector`: the single source for every screen), `trends.py`, `clock.py`, `ports.py` (interfaces) |
| `herald/scoring/` | published scores and county criteria | data-driven engines (`banded`, `item_sum`, `criteria`) + `registry`; criterion rule types in `rules.py`; a new score is a new YAML file |
| `herald/checklists/` | alert-ready checklists | engine over `config/checklists.yaml` + the active county's overrides for any alert (`alerts`) and its stroke checklist; `items.py` (record-field, score and alternative items) |
| `herald/extraction/` | speech → facts | `model.py` (the only speech extractor), `confidence.py` (per-fact token confidence), `grounding.py` + `numbers.py` (said-value checks), `guard.py` (injection containment), `profiles.py`. The old rules extractor and rules+model merge are evaluation baselines in `eval/baselines/` (with their own frozen word lists) |
| `herald/models/` | adapters to local model servers | `llm_client.py` (ZRT/vLLM, localhost only), `stt.py` (Whisper), `vision.py` (photo reading) |
| `herald/terminology/` | drug and allergen names → RxNorm; drug-class allergies → ICD-10-CM | `rxnorm.py` (`RxNormNormalizer`: exact → product name → combination → contained / fuzzy → phonetic; never guesses), `allergy.py` (NEMSIS eHistory.06 classes), `coding.py` (`MedicationCoder`: codes the keys in `config/terminology.yaml`, drug classes, holds non-exact matches for a tap), `factory.py` (`build_coder`, shared by the app and the benchmarks). The index is built by `scripts/build_rxnorm_index.py` into `data/terminology/` (not in git): pinned NLM release + RxNav brand supplement |
| `herald/relay/` | weak-link relay | `relay.py`, `tiers.py`, `netem.py` (Toxiproxy link emulation, demo only) |
| `herald/egress/` | egress policy (E1) | `policy.py` (`EgressPolicy`: ALLOW / QUEUE / DENY for every outbound URL, from `config/egress.yaml`); every outbound call (relay, protocol sync, local model requests) passes through it |
| `herald/reporting/` | the written handoff report and structured export | `handoff.py` (`HandoffBuilder`: MIST for trauma, SBAR for medical calls, from confirmed facts and computed scores), `lines.py` (line kinds), `view.py` (confirmed facts, provenance, wording), `text.py` (read-aloud text), `config.py` (loads and checks `config/handoff.yaml`), `fhir.py` (`FhirExport`: confirmed-only FHIR R4 resources, `config/fhir_codes.yaml`), `fhir_document.py` (`FhirDocument`: the handoff as a FHIR document, Composition sections = the report's sections). No model writes report text |
| `herald/telemetry/` | tokens, power, cost | `collector.py`, `prometheus.py` |
| `herald/api/` | HTTP + WebSocket only | `app.py` (factory), `context.py` (**composition root**), `capture.py`, `trace.py`, `contract.py`, `hub.py`, `routes/` |
| `herald/app.py` | ASGI entry point | `uvicorn herald.app:app` |
| `ed_receiver/` | relay/frontend | mock ED service + screen (plain HTTP, no AI) |
| `web/` | frontend (classic, served at `/classic/`) | NOW screen, phone capture page |
| `eval/` | data + eval | gold sets, `bench_extract.py`, `adversarial_bench.py`, dumps |
| `scenarios/`, `scripts/replay.py` | pitch | rehearsal replays |
| `tests/` | everyone | `fakes.py` holds test doubles for the interfaces in `herald/core/ports.py` |

## Run
```bash
PY=~/miniforge3/envs/zgx/bin/python                       # torch 2.14 + CUDA 13 env
scripts/link.sh start 127.0.0.1:8200                       # Toxiproxy: :9000 -> ED receiver
$PY -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port 8200 &
HERALD_ED_URL=http://127.0.0.1:9000 PORT=8101 scripts/run_dev.sh   # your own port: 8101..8104; 8100 = demo
# models: HERALD_LLM_MODEL = extraction (ems-e-v2-fp8, the fine-tuned extractor), HERALD_VISION_MODEL = photos (qwen3vl-fp8)
# every setting: herald/config/settings.py; content (scores, checklists, prompts, county rules): config/
# run_dev.sh binds 127.0.0.1 by default (B7). A tablet on the LAN needs HERALD_BIND_HOST=0.0.0.0 *and*
# HERALD_DEVICE_TOKEN=<shared secret> (every mutating /api/* call must send it back as X-Herald-Token; open the
# tablet's page once as .../?token=<the same secret>, ui/src/lib/authToken.ts remembers it) -- open the port with
# no token and any other device on that Wi-Fi can read and write patient state. /api/egress (herald/egress/) is
# the one place to see what left this box, was queued, or was refused, and why.
$PY scripts/replay.py scenarios/stroke_demo.json --url http://localhost:8101 --no-llm
$PY eval/bench_extract.py --extractor rules                # or: --extractor llm --model omni
$PY scripts/build_rxnorm_index.py                          # once per clone: RxNorm index -> data/terminology/ (~10 min first time: RxNav)
$PY -m pytest -q
# EVERY job that loads a model or a lot of data (training, merges, benchmarks, Whisper/TTS batches) goes through run_job:
scripts/run_job.py --name train-f --priority critical --gpu --need-gib 80 -- $PY scripts/train_vlm_lora.py …   # MEMORY_SAFETY §4
scripts/memguard.sh status                                 # the memory guard (systemd --user service, always on)
scripts/demo_mode.sh on && scripts/run_demo.sh             # the demo: no --reload, Whisper preloaded, jobs refused
```
Presenter link hotkeys on the NOW screen: Shift+G good, Shift+W weak, Shift+D down.

## Pitfalls already hit on this box (don't rediscover them)
- **Every model-loading job goes through `scripts/run_job.py`** (training, merges, benchmarks, Whisper/TTS jobs,
  anything that loads a model or tens of GB of data). On 2026-09-24 the box ran out of memory and froze until a
  manual reboot, because several model loads started in parallel next to three vLLM services, and the kernel OOM killer
  only killed small session daemons. `run_job.py` refuses in demo mode, queues GPU-heavy jobs (one at a time), waits
  for memory, caps host memory in a systemd scope, and caps torch's CUDA allocator at `--need-gib`. The memory guard
  (`herald-memguard.service`, always running) kills normal guarded jobs first when memory is short, and
  `--priority critical` jobs (the training run) last. While a critical job runs, other `--gpu` jobs are refused, and so
  is any job needing more than 4 GiB. Never stop the guard
  during a demo. Details: `docs/MEMORY_SAFETY.md`.
- **"CPU-only" is not safe next to a training run.** On 2026-09-25 at 05:13 the box hard-froze because a 4B model
  merge started with `--need-gib 12` and no `--gpu` was admitted alongside the critical 30B run: `run_job` refused only
  `--gpu` jobs. GPU and CPU share one 121.6 GiB pool here, so a critical job now blocks any job over
  `run_job.critical_coexist_gib` (4 GiB) regardless of `--gpu`; use `--wait` to queue behind it.
- **GB10 unified memory: CUDA allocations are NOT charged to cgroups** (measured: a 4 GiB torch CUDA allocation
  succeeded inside `systemd-run --user --scope -p MemoryMax=2G`), but they **do** lower `MemAvailable`. A cgroup cap
  alone can't stop a GPU job, which is why `run_job.py` also sets `torch.cuda.set_per_process_memory_fraction`. The
  cgroup memory controller is delegated to `hp18`, so `systemd-run --user --scope -p MemoryMax=…` works without sudo.
- **ZRT needs the `zrt` group**: run via `sg zrt -c "zrt …"` in old shells. The API is `127.0.0.1:8080/v1`, with auth and TLS off, localhost only.
- **`zrt serve` runs in the FOREGROUND. Launch it detached:** `setsid nohup env MAX_JOBS=3 NVCC_THREADS=1 sg zrt -c "zrt serve …" > runs/serve/<label>.log 2>&1 < /dev/null &`. `zrt status` lists a PID, which makes the service look like a daemon, but it is a child of the shell that started it: on 2026-09-25 a healthy `qwen3vl-fp8` (Ready, 40 GB) was killed at 01:04:53 when the agent's background terminal was torn down. Piping to `tail` also hides the output until EOF, so the log looks empty while the model loads.
- **A stale `/opt/hp/zrt/run/proxy.pid` blocks every serve, and the PID in it can lie.** After a reboot `zrt serve` reported `timed out after 30s waiting for proxy at …/healthz` with nothing listening on 8080 and `proxy.log` silent for hours. The pidfile held a pre-reboot PID that had been **recycled as a thread of another process** (a VS Code server), so `kill -0` succeeded and ZRT believed the proxy was alive. `ps -p <pid>` shows nothing for a thread id: check `/proc/*/task/<pid>` before trusting a pidfile. Move the file aside (`mv /opt/hp/zrt/run/proxy.pid /tmp/…`) and the next `zrt serve` prints "Cleaning up stale proxy state files" and starts normally.
- **`from_pretrained` transiently needs ~2x the checkpoint here; stream the load instead.** Unified memory makes the mmapped safetensors GPU-addressable, so `nvidia-smi` counts the whole checkpoint the moment it is mapped while the host fills with resident pages: two 30B loads died at ~50% with MemAvailable falling 114 → 8 GiB and the guard killing the critical job. `posix_fadvise(DONTNEED)` cannot help, because it will not evict pages held by a live mapping. Use `lora_common.load_model` (shard-by-shard onto the GPU, one shard held at a time); `--no-stream-load` is the old path. Note the on-disk MoE experts are **transposed** relative to the model, so a loader must swap the last two dims (`lora_common._fit_to_target`, checked by shape, never by name).
- **`--need-gib` on a *normal* `run_job` job is also its hard torch CUDA cap.** Run F's 4B training was started with `--need-gib 40` and died with `torch.OutOfMemoryError … 40.00 GiB allowed` while 63.8 GiB of the box was free. A `--priority critical` job is no longer capped by `--need-gib` (only by an explicit `--gpu-max-gib`); for normal jobs, size `--need-gib` to the real peak, not to what you hope it uses.
- **vLLM kernel JIT needs Python headers.** `python3.12-dev` is now installed system-wide (2026-09-23), which fixes it. The older workaround (`C_INCLUDE_PATH=CPLUS_INCLUDE_PATH=~/miniforge3/envs/zgx/include/python3.12` before `zrt serve`) is harmless if you see it in scripts.
- **The JIT compile can OOM the box** (one `cicc` per core, about 4.5 GB each). Export `MAX_JOBS=3 NVCC_THREADS=1` before `zrt serve`.
- **ZRT counts only *free* memory, not reclaimable file cache.** After reading large weight files, `zrt serve` can refuse ("Free memory is less than desired fraction") while `MemAvailable` is ample. Without root, drop the cache of files you own with `posix_fadvise(DONTNEED)`: a 20-line script reads each large file and advises it away (freed 37 GB on 2026-09-23; running models are unaffected).
- **Always cap vLLM memory**: `--gpu-memory-fraction 0.35` or lower. Whisper and the app share the same 121 GiB.
- **One GPU-heavy job at a time.** Fine-tuning and model swaps get announced to the team. `run_job.py --gpu` enforces it with `~/.cache/herald-gpu.lock`.
- **Never `pkill -f uvicorn…`**: it matches your own shell. Kill by anchored `pgrep -f "^/home/hp18/miniforge3/envs/zgx/bin/python -m uvicorn herald.app"`.
- **The same self-match breaks wait loops and cleanup.** `until ! pgrep -f "bench_extract … ems"` never ends, because the loop's own command line contains the pattern, and `kill $(pgrep -f "<pattern>")` can kill the shell running it. Anchor the pattern to the interpreter path (`^/home/hp18/miniforge3/envs/zgx/bin/python eval/…`), wait on an output file instead, or kill by the PID you recorded.
- **Browser mic needs a secure context**: open the NOW screen via `http://localhost:<port>` (port forward), not the LAN IP. The phone camera page works over plain HTTP.
- **Nemotron-Omni is a reasoning model**: send `chat_template_kwargs: {"enable_thinking": false}` and strip `<think>` (already in `llm.py`).
- **Omni's first start takes ~23 min** (kernel compile, cached in `~/.cache/flashinfer`, `~/.cache/vllm`). Don't restart it casually. Check `zrt status` before touching it; it serves everyone.
- **Structured output must be typed and bounded.** An unbounded value type made the model ramble to `max_tokens` and truncate JSON. Keep the schema in `extract_llm.py` tight; `llm._salvage` keeps complete facts if it happens.
- **Temperature 0 is not deterministic here** (FP4 kernels, batching). Benchmark with 3 runs and report the spread.
- **ZRT's proxy routes by service label only.** A vLLM `--lora-modules` name shows up in `/v1/models` but a request for it returns 404 ("unknown model name"). Merge the adapter (`scripts/merge_lora.py`), push it to a private HF repo, and `zrt serve hf:<repo> --label <name>`.
- **A strict JSON schema can fight a fine-tuned model's learned tokenization.** With the extractor schema, the fine-tuned model appended an optional "?" to every fact. Fine-tuned models decode in JSON mode, and their output is validated against `KEYS` afterwards (`extract_llm.prompt_for`).
- **Never edit a script while a background job is running it.** Python re-reads nothing, but a job that starts later in the same loop picks up the half-edited file (two benchmark runs crashed this way on 2026-09-23).
- **Extraction fixes go into the model, not into rules** (team lead, 2026-09-23). Don't add lookup tables or phrase regexes to make a gold item pass. The scorer's normalization is measurement, and published score tables and safety validators stay deterministic by design.

## Git
- Your own clone under `~/work/<name>/`, repo-local `git config user.name/email`, and your own GitHub auth (see `CONTRIBUTING.md`).
- Branch `feat/<area>`; small PRs; `main` always runs the demo.
- Never commit `/home/hp18/Documents/team-last-minute/.agent/` (or any copy of it), `data/audio/*`, `data/photos/*`, `~/.config/herald/secrets.env`, tokens, or the device password.
- Commit messages: imperative, what and why.
