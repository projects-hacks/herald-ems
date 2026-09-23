# AGENTS.md: rules for coding agents working on Herald

Read this before changing anything. Then pick a task from `TASKS.md`.

## What Herald is (one paragraph)
An offline AI copilot for the back of the ambulance, running entirely on an HP ZGX Nano (NVIDIA GB10). It listens to the paramedic and reads photos, keeps a live, evidence-backed patient picture (checklists, gaps, contradictions, trends, clocks, published scores), writes the chart as a by-product, and relays the smallest critical update to the emergency department over a weak link. The full product spec lives on the team Nano at `../.agent/ideas/herald-ems-copilot.md` (outside this repo, never committed).

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
- **vLLM kernel JIT needs Python headers** (`python3.12-dev` isn't installed). Export `C_INCLUDE_PATH=CPLUS_INCLUDE_PATH=~/miniforge3/envs/zgx/include/python3.12` before `zrt serve`.
- **The JIT compile can OOM the box** (one `cicc` per core, about 4.5 GB each). Export `MAX_JOBS=3 NVCC_THREADS=1` before `zrt serve`.
- **Always cap vLLM memory**: `--gpu-memory-fraction 0.35` or lower. Whisper and the app share the same 121 GiB.
- **One GPU-heavy job at a time.** Fine-tuning and model swaps get announced to the team.
- **Never `pkill -f uvicorn…`**: it matches your own shell. Kill by anchored `pgrep -f "^/home/hp18/miniforge3/envs/zgx/bin/python -m uvicorn herald.app"`.
- **Browser mic needs a secure context**: open the NOW screen via `http://localhost:<port>` (port forward), not the LAN IP. The phone camera page works over plain HTTP.
- **Nemotron-Omni is a reasoning model**: send `chat_template_kwargs: {"enable_thinking": false}` and strip `<think>` (already in `llm.py`).

## Git
- Your own clone under `~/work/<name>/`, repo-local `git config user.name/email`, and your own GitHub auth (see `CONTRIBUTING.md`).
- Branch `feat/<area>`; small PRs; `main` always runs the demo.
- Never commit `../.agent/`, `data/audio/*`, `data/photos/*`, tokens, or the device password.
- Commit messages: imperative, what and why.
