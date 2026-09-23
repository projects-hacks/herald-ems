# Herald

**The patient's story arrives before the doors open.**

Herald is an offline AI copilot for the back of the ambulance. While the paramedic works, it listens to the call and reads what the medic points the phone at, and it keeps a live, evidence-backed picture of the patient: what's known, what changed, what's still missing, which clock is running, and whether a stroke or heart-attack pre-alert is ready. The chart writes itself, and the emergency department gets the smallest critical update the connection can carry. Every model runs on an HP ZGX Nano (NVIDIA GB10). No cloud AI.

> Status: hackathon prototype (HP Edge AI SJSUHack, Sept 2026). Not a medical device. It never recommends treatment.

## What it does today

| | |
|---|---|
| **Gap-first screen** | The pre-alert checklist starts at 0 of 6, and the gaps close as the medic talks |
| **Speech → facts** | Whisper large-v3-turbo on the GPU (a 10 s clip transcribes in ~0.3 s). The rules extractor always runs; the local LLM adds nuance when it is served |
| **Who said it** | Every fact records who it came from ("husband says…" → family) and links back to the audio |
| **Published scores** | NEWS2, the RACE stroke scale, and the 2021 national trauma field-triage criteria, computed by plain code from confirmed facts, with every input and source shown |
| **Contradictions and trends** | Sources that disagree require the medic's confirmation; significant vital-sign changes and NEWS2 rises are flagged |
| **Clocks** | Last known well, scene time, ETA, and reassessment due |

Coming next: photo reading (monitor, pill bottles, POLST), ED relay over a weak link, and the ED screen.

## Run it

```bash
# on the ZGX Nano, in the `zgx` conda env (torch 2.14 + CUDA 13 already installed)
pip install -r requirements.txt
scripts/serve_models.sh          # optional: local LLM/VLM via HP Z Runtime (ZRT) on :8080
PORT=8100 scripts/run_dev.sh     # Herald server + NOW screen
```

Open `http://localhost:8100`. Browsers only allow the microphone on `localhost` or HTTPS, so from a laptop forward the port first (VS Code does this automatically, or run `ssh -L 8100:localhost:8100 <user>@<nano>`). Hold **Space** to talk as the medic, and **F** as a patient or family member.

Tests: `python -m pytest -q` (every published score is checked at every band boundary).

## Architecture

```
CAPTURE                      STATE (deterministic)                 OUTPUTS
push-to-talk speech  ─┐      append-only facts with provenance     NOW screen (gap-first)
phone photos (next)  ─┼──►   checklists · gaps · contradictions ─► ePCR fields
simulated monitor    ─┘      trends · clocks · NEWS2 · RACE        ED relay (next)
        │
  Whisper (GPU) → rules extractor + local LLM (ZRT/vLLM) → typed facts
```

The language model only turns speech and photos into facts. Checklists, scores, contradictions, clocks, and what gets sent are all plain code.

| Path | What |
|---|---|
| `herald/schema.py` | Fact model and the canonical key vocabulary |
| `herald/state.py` | Patient state engine: projection, checklists, gaps, contradictions, trends, clocks |
| `herald/scores.py` | NEWS2, RACE, 2021 field-triage criteria (published tables, unit-tested) |
| `herald/checklists.py` | Alert-ready checklists (stroke, STEMI) |
| `herald/extract_rules.py` | Deterministic extractor (fallback and benchmark baseline) |
| `herald/extract_llm.py`, `herald/llm.py` | Local LLM extractor (OpenAI-compatible endpoint on this box) |
| `herald/pipeline.py` | Merges rules and LLM output |
| `herald/stt.py` | Local Whisper |
| `herald/app.py` | FastAPI server + WebSocket |
| `web/` | NOW screen |
| `tests/` | Score and state tests |

## Evidence behind the scores

- NEWS2: pooled across 30 studies and 185,835 patients, AUC 0.88 for 2-day mortality (prehospital and ED combined).
- RACE ≥ 5: sensitivity 0.85, specificity 0.68 for large-vessel occlusion (Pérez de la Ossa et al., *Stroke* 2014).
- Field triage: National Guideline for the Field Triage of Injured Patients (2021).
