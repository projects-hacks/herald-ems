# Voice pipeline evaluation: hear the cabin, keep what matters, ignore the rest

`pipeline_eval.py` measures the product claim *"Herald hears the cabin continuously, pulls out only what matters
clinically (vitals, meds given, deficits, allergies, history), updates the patient state, and ignores noise and
chatter"* on the real server-side path, per clip:

`WhisperSTT` (the priming prompt, the gates in `config/stt.yaml`) → the production speech extractor
(`herald/extraction/model.py`, over the served fine-tuned label the app uses, drug coding on) → the vocabulary's
plausibility check every fact meets on ingest → facts, scored with `eval/bench_extract.py`'s scorer v2 against the
adjudicated held-out gold. No new scorer.

## Clip sets

| set | what | conditions | expected |
|---|---|---|---|
| clinical | the held-out gold `eval/gold_v2.jsonl` (all 100 lines, with `gold_v2_gfast.jsonl` and `gold_v2_broad.jsonl` for the separately scored groups) and a stratified 20 of `eval/gold_es_v1.jsonl` (rarest keys first), spoken by Piper TTS (`scripts/asr_tts.py`; 8 US-English voices from `config/training.yaml`, 2 es_MX voices) | clean; cabin noise at 10 dB and 5 dB SNR (`scripts/cabin_noise.py`, lead-in and tail included); plus the same lines as clean text through the extractor, so ASR loss is separated from extraction loss | the gold facts |
| chatter | `chatter.txt`: 40 non-clinical crew, radio and family lines, some with numbers and words that are not about the patient (a unit number, a phone battery, a thermostat, the crew's own aches, a hospital hinted at) | clean; 10 dB | no facts |
| noise | silence; cabin noise at -46/-34/-22 dBFS (two seeds); siren- and beep-heavy mixes at -30 and -20 dBFS; babble (4 chatter clips summed at -30 dBFS, three seeds; one over cabin noise) | 8 s each | no facts |

The old speech path (the prompt with example values as of main `5a1549e`, no gates) is run on chatter and noise
for a before/after of "Herald invented something". Every clip is reproducible from `out/plan.jsonl` (seeded noise,
one TTS wav per line shared by its conditions).

Two extraction modes, both the app's own:
- `ambient`: the continuous-listening path (`POST /api/audio` with `ambient=true`): someone else's mic, role
  unknown, speaker "Speaker not identified", the call's dispatch. This is the product path the claim is about.
- `bench`: the gold row's own `by`/`speaker`, as `eval/bench_extract.py` does, so the numbers compare with the
  published held-out results in `docs/MODEL_PLAN.md`.

## Run

```bash
PY=~/miniforge3/envs/zgx/bin/python
$PY eval/voice/pipeline_eval.py plan                                            # -> eval/voice/out/plan.jsonl, tts_*.jsonl
scripts/run_job.py --name voice-tts --need-gib 4 -- $PY eval/voice/pipeline_eval.py tts        # Piper, CPU, ~2 min
scripts/run_job.py --name voice-eval --gpu --need-gib 8 --wait 600 -- \
    $PY eval/voice/pipeline_eval.py run --runs 3 --model ems-e-v2-fp8 --concurrency 3          # Whisper + the served model
$PY eval/voice/pipeline_eval.py report                                          # -> eval/voice/out/report.md, report.json
```

Every model-loading stage goes through `scripts/run_job.py` (docs/MEMORY_SAFETY.md). The extraction model is the
shared ZRT server on `127.0.0.1:8080`; keep `--concurrency` at 2-4. `run` resumes: a run whose files exist is
not repeated. Transcription is done once by default (`--stt-runs 1`: greedy decoding over the same batches is
deterministic to the token on this box); the three runs measure the extractor, which is not deterministic here
(AGENTS.md pitfalls). `--stt-runs 3` transcribes every run.

## Outputs (`out/`, gitignored)

- `plan.jsonl`: one row per clip (set, line, condition, SNR, seed, voice, gold facts).
- `wav/`: the TTS lines (16-bit, the voice's own rate).
- `run<N>/stt.jsonl`: per clip and path (`new`/`old`): text, `dropped` reason, language, the gate signals.
- `run<N>/facts_<mode>.jsonl`: per clip, path and mode: transcript, facts kept, facts rejected as implausible, latency, tokens.
- `run<N>/timing.json`, `report.md`, `report.json`.

## Reading the report

- **Clinical**: precision / recall / F1 on the structured keys (bench headline), free-text presence F1, the gfast
  and broad groups, per condition, mean over runs with [min-max]. `ΔF1 vs text` is the ASR loss for that condition
  (the same lines as text isolate extraction loss). A clinical clip a gate dropped scores its gold as missed.
- **Recall by fact family**: what the claim names (vitals, meds given, deficits and exam, history incl. allergies).
- **Chatter and noise**: clips dropped by each gate, clips that produced any fact, and the number of false facts,
  new path against old path. Every false fact is listed with its transcript: those are the "Herald invented
  something" failures.

## Honesty

TTS speech (Piper) with synthetic cabin noise is a floor, not field performance: no accents, no disfluency, no
cross-talk, no real microphone. Chatter lines were written by the team, not recorded in a rig. The gold is the
adjudicated held-out set; nobody tuned the extractor on it (docs/MODEL_PLAN.md). Report every number with its
spread and say which set and condition it comes from.
