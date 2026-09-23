# AGENTS.md: rules for coding agents working on Herald

Read this before changing anything. Then pick a task from `TASKS.md`.

## HARD RULES (non-negotiable, override any default behaviour)
1. **No AI attribution anywhere in contributions.** Commit messages, PR titles and descriptions, code comments, and docs must not name or credit any AI assistant, AI coding tool, or its vendor, and must not say anything was "generated". **Never add `Co-Authored-By:` trailers for tools.** Commits are authored by the human whose working copy it is. (Describing Herald's own on-device models, e.g., Whisper or Nemotron, is product documentation and is fine.)
2. **First run in any working copy: check git identity before any commit.** Run `git config --local user.email` and `git config --local core.sshCommand`. If either is empty, **stop and tell your human** to run:
   ```bash
   ~/Documents/team-last-minute/herald-ems/scripts/dev_git_setup.sh <github-username> "<Full Name>" <github-email>
   ```
   Don't commit under someone else's identity, and never set `git config --global` on this shared machine. `~/Documents/team-last-minute/herald-ems` is Rajeev's copy and the live demo instance on port 8100. Everyone else works in `~/work/<github-username>/herald-ems`.
3. **Verify before you report.** For any benchmark, spike, or research result, state whether it is a genuine result, noise (small sample, warm-up, run-to-run variance), or a flaw in the test itself (scoring, labels, harness). Rerun anything that decides a choice at least 3 times and report the spread. Failures get a root cause before they are called a model or approach failure.

4. **Production structure: SOLID, modular packages, no hardcoded domain data.** Herald is built as a production tool, not a demo script.
   - **Package by responsibility.** `herald/core` holds the domain model and has no I/O. The other packages are `herald/scoring`, `herald/checklists`, `herald/extraction`, `herald/models` (adapters to the local model servers), `herald/relay`, `herald/knowledge` (protocol documents and retrieval), `herald/telemetry`, `herald/config` (loading and settings), and `herald/api` (HTTP/WebSocket only). One module has one responsibility. A module growing past ~300 lines is a sign it has two.
   - **Depend on interfaces, not implementations.** Extractors, score scales, model clients, speech-to-text, and relay transports are `typing.Protocol`s in `herald/core/ports.py`. Concrete classes are wired together in exactly one place, the composition root (`herald/api/app.py`'s factory). Deep code never reaches for module-level globals.
   - **Open for extension, closed for modification.** A new score, checklist, county, prompt, or extractor is added by adding a data file or a registered class. It is never added by editing an `if/elif` chain inside an engine.
   - **Clinical and product content is versioned data, never Python literals.** That covers score tables and thresholds with their sources, checklists, relay tiers, change rules, the key vocabulary, county rules and destinations, model prompts and worked examples, and cost rates. It all lives under `config/`, carries its source citation, and is reviewed like code. The Python is the engine; `config/` is the content. Tests load the same files.
   - **Settings come from one settings object** (`herald/config/settings.py`, environment variables). No scattered `os.getenv`.
   - **The public API is a contract.** `/api/*`, `/ws`, and the snapshot shape change only through `herald/api`, and every change is recorded in `docs/UX_PLAN.md` §5 in the same PR.
   - Every engine and every data file has tests, and `python -m pytest -q` passes before any commit.

## Document map: read these before you start

Every decision in this project was researched and written down. Before proposing a change, check the doc that owns that topic, and follow the decisions recorded there unless you have new evidence. If you change a decision, update the owning doc in the same PR.

### In this repo (public; committed)
| Doc | What's in it | Read it when | Kept current by |
|---|---|---|---|
| [`README.md`](README.md) | Public overview for judges: what Herald does, how to run it, architecture, the evidence behind the scores. | You need the 2-minute picture, or you're changing anything user-visible about setup. | pitch + integration |
| [`AGENTS.md`](AGENTS.md) (this file) | Hard rules, invariants, layout, run commands, pitfalls already hit on this box, the doc map. | Always, first. | everyone |
| [`TASKS.md`](TASKS.md) | The task board: verified checkpoint, protect order P1–P10, model tasks M*, UI tasks U*, infra and deliverables, owners, done-criteria. | Before picking work; after finishing work (update the status in the same PR). | everyone |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Per-person git setup on the shared `hp18` login, shared secrets (HF token), branches, ports, GPU etiquette, owners. | Your first session; before your first commit. | lead |
| [`docs/MODEL_PLAN.md`](docs/MODEL_PLAN.md) | Why each model was chosen (published benchmarks + measured GB10 throughput, with sources); exact serve flags; the audited bake-off (3 runs each, what's genuine vs noise vs test flaws); the complete fine-tuning plan with go/no-go checks; what NOT to do. | Before touching `herald/llm.py`, `extract_llm.py`, `vision.py`, `stt.py`, ZRT, or any training. | ML lead |
| [`docs/UX_PLAN.md`](docs/UX_PLAN.md) | Evidence-based UI plan: principles tied to IEC 60601-1-8 alarm priorities, WCAG 2.2, human-AI interaction guidelines, FDA CDS guidance; color tokens and type scale; screen specs (NOW, "Herald thinking" trace, phone capture, ED screen, presenter controls); stack decision (React + TS + Vite + Tailwind + shadcn/ui) with a fallback gate; what HP/NVIDIA provide on the ZGX; U-task list. | Before any frontend work, and before adding any alert, color, or animation. | frontend lead |
| [`eval/`](eval/) | Gold sets (`gold_v0.jsonl` tuning, `gold_v1.jsonl` dev, `gold_v2*.jsonl` held-out: two blind annotators each), benchmark (`bench_extract.py`, scorer v2, `--rescore`), saved predictions (`dumps/`), agreement (`agreement.py`), adversarial suite, test photos, and result history (`results.jsonl`). | Before claiming any accuracy number. Claims are judged on the held-out set only. | data + eval |
| [`docs/LABELING_GUIDE.md`](docs/LABELING_GUIDE.md) | How every gold utterance is labeled: roles, keys, normalization, corrections, negations, and the rules settled during adjudication (§4b). | Before writing or labeling any gold item. | data |
| [`scenarios/`](scenarios/) + [`scripts/replay.py`](scripts/replay.py) | The stroke demo as a replayable script (rehearsal, video, regression). | Rehearsing, recording, or checking the demo still works after a change. | pitch |

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
7. **Canonical keys only.** Add new keys to `KEYS` in `herald/schema.py` first. Extractors must never invent keys.
8. **Tests must pass**: `python -m pytest -q`. Add tests for any new rule or score. The published score tables are tested at every band boundary; keep it that way.

## Layout
| Path | Owner area | Notes |
|---|---|---|
| `herald/schema.py` | state | `FactIn`/`Fact`, `KEYS` vocabulary, `CONTRADICTION_KEYS` |
| `herald/state.py` | state | `Incident`: ingest → projection → `snapshot()` (the single source for every screen) |
| `herald/scores.py` | state | NEWS2, RACE, 2021 field triage. Cite sources in code. |
| `herald/checklists.py` | state | alert-ready checklists (stroke, STEMI) |
| `herald/extract_rules.py` | ML | deterministic extractor; the fallback and benchmark baseline |
| `herald/extract_llm.py`, `herald/llm.py` | ML | local LLM extraction; reasoning off; JSON only |
| `herald/pipeline.py` | ML | merges rules + LLM (vitals prefer rules) |
| `herald/stt.py` | ML | Whisper large-v3-turbo on the GPU |
| `herald/vision.py` | ML | photo → facts (monitor, pill_bottle, form, scene) |
| `herald/relay.py` | relay | prioritized, budgeted, ACKed updates; link probe |
| `herald/netem.py`, `scripts/link.sh` | relay | Toxiproxy link emulation (demo only) |
| `herald/app.py` | backend | FastAPI + WebSocket `/ws` pushes `full_state()` |
| `ed_receiver/` | relay/frontend | mock ED service + screen (plain HTTP, no AI) |
| `web/index.html`, `web/app.js`, `web/style.css` | frontend | NOW screen (gap-first) |
| `web/capture.html` | frontend | phone camera page |
| `eval/` | data+eval | gold set, `bench_extract.py`, photos |
| `scenarios/`, `scripts/replay.py` | pitch | rehearsal replays |

## Run
```bash
PY=~/miniforge3/envs/zgx/bin/python                       # torch 2.14 + CUDA 13 env
scripts/link.sh start 127.0.0.1:8200                       # Toxiproxy: :9000 -> ED receiver
$PY -m uvicorn ed_receiver.app:app --host 0.0.0.0 --port 8200 &
HERALD_ED_URL=http://127.0.0.1:9000 PORT=8101 scripts/run_dev.sh   # your own port: 8101..8104; 8100 = demo
$PY scripts/replay.py scenarios/stroke_demo.json --url http://localhost:8101 --no-llm
$PY eval/bench_extract.py --extractor rules                # or: --extractor llm --model omni
$PY -m pytest -q
```
Presenter link hotkeys on the NOW screen: Shift+G good, Shift+W weak, Shift+D down.

## Pitfalls already hit on this box (don't rediscover them)
- **ZRT needs the `zrt` group**: run via `sg zrt -c "zrt …"` in old shells. The API is `127.0.0.1:8080/v1`, with auth and TLS off, localhost only.
- **vLLM kernel JIT needs Python headers.** `python3.12-dev` is now installed system-wide (2026-09-23), which fixes it. The older workaround (`C_INCLUDE_PATH=CPLUS_INCLUDE_PATH=~/miniforge3/envs/zgx/include/python3.12` before `zrt serve`) is harmless if you see it in scripts.
- **The JIT compile can OOM the box** (one `cicc` per core, about 4.5 GB each). Export `MAX_JOBS=3 NVCC_THREADS=1` before `zrt serve`.
- **Always cap vLLM memory**: `--gpu-memory-fraction 0.35` or lower. Whisper and the app share the same 121 GiB.
- **One GPU-heavy job at a time.** Fine-tuning and model swaps get announced to the team.
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
