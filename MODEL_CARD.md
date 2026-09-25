# Model card: Herald's fine-tuned extractors ("run F")

This card covers the two fine-tuned models Herald trained on the ZGX Nano for turning ambulance speech
and photos into typed clinical facts: **herald-f** (30B) and **herald-f4b-fp8** (4B, text-only fallback).
It does not cover the untuned models Herald also serves (Whisper large-v3-turbo, bge-base-en-v1.5, and
`qwen3vl-fp8`), which keep their publishers' own model cards.

**Not a medical device.** Herald never recommends treatment, a drug dose, or transport eligibility. These
models only turn speech, photos, and document images into structured facts; a paramedic decides everything.
See `README.md` and `AGENTS.md` invariant 3.

**Status.** herald-f finished training and passed most of its own held-out speech and photo gates, but it
**failed the protocol-reranking kept-ability gate** and its confirmation threshold has not been recalibrated
for it. It has not shipped as Herald's extractor. Herald's default configuration keeps serving the
previous run (`ems-e-v2-fp8`, Qwen3-4B-Instruct-2507 + LoRA) or the documented split-stack/4B-fallback
options; see `docs/RUNBOOK.md` and `config/stack.yaml`. Every number below is from `eval/results.jsonl`
(or, where noted, `docs/RUN_F_REPORT.md` for the training run itself) and was current as of 2026-09-25.

## herald-f (30B)

| | |
|---|---|
| Base model | `Qwen/Qwen3-VL-30B-A3B-Instruct` (Apache-2.0) |
| Fine-tuning method | LoRA, rank 16, alpha 32, dropout 0 |
| Target modules | `q,k,v,o,gate,up,down_proj` under `language_model` (attention + MLP projections), plus **every MoE expert** (`mlp.experts.gate_up_proj`, `mlp.experts.down_proj`). The router stays frozen and the vision tower is untouched, so the served vision tower is identical to the benchmarked base model. |
| Trainable parameters | **642,514,944** (attention/MLP projections 13,369,344 + experts 629,145,600) |
| License | Apache-2.0 (same as the base model; Herald's adapter weights are Herald team work, also Apache-2.0) |

### Training data

17,112 rows in one fixed training plan (976 micro-batches, 5,428,833 padded tokens / 5,289,700 real,
0 rows dropped for length; 150 text, 60 image, 40 replay rows held out):

| kind | rows | notes |
|---|---:|---|
| speech → facts (text) | 13,880 | includes **1,019 ASR-derived rows**: text spoken by 8 Piper TTS voices, mixed with cabin noise, and transcribed through Herald's own production speech path (`WhisperSTT`, Whisper large-v3-turbo, the real priming prompt) rather than typed as clean text — so the model sees its own upstream transcription errors during training. |
| photos (monitors, forms, labels) | 2,400 | rendered monitor layouts, camera-on-screen renders, and rendered/photographed forms including the California POLST. |
| replay (protocol reranking, figure transcription, EN↔ES translation) | 832 | kept-ability data: the tasks the base model could already do, included so fine-tuning does not erase them. |

**Data statement.** All training and evaluation data is synthetic and AI-assisted: utterances, labels, and
rendered photos are generated and labeled by the team's own tooling (`docs/MODEL_PLAN.md`,
`docs/TRAINING_PLAN.md`, `docs/LABELING_GUIDE.md`), not collected from real incidents. Gold evaluation sets
are labeled independently by two annotators per set, with measured inter-annotator agreement (e.g. gold v2
fact F1 0.979) and a documented adjudication pass — but **no gold set or training set has been reviewed by
a clinician**, and agreement between two annotators of the same kind is an upper bound on label quality, not
proof of clinical correctness. **No real patient audio or photos were used in training or evaluation**;
`data/audio/` and `data/photos/` are excluded from version control and from every training run.

### Training run

Merged from the run-F training job (`docs/RUN_F_REPORT.md`): 2 epochs, 488 optimizer steps (244/epoch), on
one HP ZGX Nano (NVIDIA GB10, aarch64). Finished 2026-09-25 09:22 UTC, wall clock 5h05m including 2 reboots
and 3 deliberate restarts; peak GPU memory 78.5 GiB of 121.6; both epoch checkpoints verified by sha256
against independent backups. Epoch 2 improved on all three dev splits over epoch 1 (text loss 0.0899 →
0.0819, image 0.2292 → 0.2042, replay 0.1393 → 0.1322) and was the one merged, served, and gated; epoch 1
was never served or gated (`docs/RUN_F_REPORT.md` §1, §6b).

Epoch 2 is merged into the BF16 base (13 shards, **57.9 GiB**) and served through HP Z Runtime (ZRT/vLLM)
quantized to **FP8**, block-128 on the language model with the vision tower left in BF16
(`--quantization=fp8_per_block`, `--quantization-config='{"ignore":["re:.*visual.*"]}'`;
`scripts/serve_models.sh`).

### Evaluation (all numbers from `eval/results.jsonl`; single runs unless noted)

**Speech → facts**, extractor `llm:herald-f`, scorer v2:

| gold set | n | F1 | precision | recall | role acc |
|---|---:|---:|---:|---:|---:|
| `gold_v2` (held-out) | 100 | 0.956 | 0.969 | 0.943 | 0.964 |
| `gold_v3` (every call type) | 100 | 0.942 | — | — | 0.989 |
| `gold_ctx` (dispatch-context rule) | 60 | 0.938 | — | — | 0.989 |
| `gold_es_v1` (Spanish speech → facts) | 60 | 0.931 | — | — | 0.993 |
| `gold_newkeys_v1` | 84 | 0.935 | — | — | 0.980 |

G.F.A.S.T. F1 on `gold_v2` was **0.947** on this run — **below the 0.95 kept/shipping bar**, and measured
once; a same-day rerun of the same gold set (also in `eval/results.jsonl`) scored G.F.A.S.T. F1 0.919, so
this number has not been shown stable across repeats and should not be read as a pass.

Adversarial speech (`eval/results.jsonl`, one run each): seen set 20/25 passed, unseen set 27/40 passed.

Confirmation calibration at the 0.8 threshold, held-out: **206 facts auto-confirmed, 11 wrong** (precision
0.947). The shipping bar for herald-f is auto-confirmed wrong ≤ 1 (`docs/TRAINING_PLAN.md` §6); at 11 wrong
this is **not** recalibrated for shipping — see Known limits.

**Photos**, `eval/results.jsonl` `bench: vision:photos`, model `herald-f`:
- Camera-on-screen synthetic set (`eval/photos/camera_screen`, n=8): F1 1.000, exact-image accuracy 1.000.
- Rendered forms including POLST (`photos_forms_polst`): F1 **0.578**, 3 invented facts — weak. Herald does
  **not** claim reliable POLST `code_status` reading from this model; see the "Claims" section of
  `README.md`.
- Real (non-rendered) photos (`photos_real`): F1 **0.727**, 18 invented facts — weak, and the gap between
  this and the synthetic/rendered numbers above is the clearest sign that the synthetic training and gold
  data do not fully generalize to real photos.

**Kept abilities (protocol reranking, all 59 questions, `bench: vision:rerank`, model `herald-f`):**

| metric | herald-f | required (untuned `qwen3vl-fp8` baseline) |
|---|---:|---:|
| right passage first (top1) | 0.731 (38/52) | ≥ 0.788 (41/52) |
| top 3 | 0.788 (41/52) | ≥ 0.827 (43/52) |
| out-of-scope questions correctly refused | 0.571 (4/7) | ≥ 0.571 (4/7) |

**This gate failed** on top1 and top3: herald-f's protocol reranking is measurably worse than the untuned
model it would replace. Refusal correctness met the bar exactly but did not improve on it. Figure
transcription (700-A13, `bench: vision:flowchart`) matched the untuned baseline exactly (node recall 0.875,
edge recall 0.857, 0 added words) and is not the blocker.

### Known limits

- **Failed the protocol-rerank kept-ability gate** (right passage first 0.731 vs the required ≥0.788;
  top 3 0.788 vs ≥0.827). This is why Herald does not serve herald-f for protocol reranking, figure
  transcription, or translation in its default configuration — see `config/stack.yaml` and
  `docs/RUNBOOK.md` for the split-stack and 4B-fallback options this leaves in place.
- **Calibration refit is pending.** At the inherited 0.8 auto-confirm threshold, 11 of 206 held-out
  auto-confirmed facts were wrong, against a ≤ 1 bar. herald-f must not be served with `ems-e-v2-fp8`'s
  confirmation thresholds; `config/confirmation.yaml` needs herald-f-specific thresholds from a refit that
  has not yet been done.
- **G.F.A.S.T. F1 0.947 on one `gold_v2` run**, against a 0.95 bar, with a same-day rerun at 0.919 — not
  yet shown to pass reliably (see above).
- **Photo reading on real (non-rendered) photos and on POLST forms is measurably weaker** than on the
  rendered/synthetic training distribution (F1 0.727 and 0.578 respectively, vs 1.000 on the synthetic
  camera-on-screen set). Treat any photo-derived fact, and POLST `code_status` in particular, as needing the
  medic's confirmation, which Herald already requires for every photo-derived fact (invariant 4).
- **No end-to-end (microphone-to-facts) evaluation exists for herald-f.** All speech numbers above are
  extraction from gold *text* transcripts (`eval/bench_extract.py`), not from audio through Whisper; see
  "Claims" in `README.md`.
- Training and evaluation data is entirely synthetic/AI-assisted and not clinician-reviewed (see Data
  statement above); accuracy on real speech and real photos is expected to be lower than these numbers.

## herald-f4b-fp8 (4B, text-only fallback)

| | |
|---|---|
| Base model | `Qwen/Qwen3-4B-Instruct-2507` (Apache-2.0) |
| Fine-tuning method | LoRA merged into the base, same run-F training recipe and data as herald-f's text rows; text-only (no vision tower) |
| License | Apache-2.0 |
| Role | The fallback extractor when the 30B stack is not used (`docs/TRAINING_PLAN.md` §7); paired with the untuned `qwen3vl-fp8` for photos, reranking, figures and translation. |

Evaluation (`eval/results.jsonl`, extractor `llm:herald-f4b-fp8`, scorer v2, one run each):

| gold set | n | F1 | role acc |
|---|---:|---:|---:|
| `gold_v2` (held-out) | 100 | 0.914 | 0.967 |
| `gold_v3` (every call type) | 100 | 0.907 | 0.940 |
| `gold_ctx` | 60 | 0.898 | 0.892 |
| `gold_es_v1` (Spanish) | 60 | 0.908 | 0.992 |
| `gold_newkeys_v1` | 84 | 0.741 | 0.950 |

G.F.A.S.T. F1 on `gold_v2` is **0.519** — well below both the 0.95 bar and herald-f's number; the 4B model
is a materially weaker stroke-screen extractor. Adversarial: seen 16/25, unseen 19/40 (both below herald-f's
and below `ems-e-v2-fp8`'s live numbers). Calibration at 0.8, held-out: 161 auto-confirmed, 10 wrong
(precision 0.938) — also not recalibrated for shipping.

Use herald-f4b-fp8 only as the documented fallback (`docs/RUNBOOK.md`), paired with the untuned
`qwen3vl-fp8` for everything vision- and language-adjacent; it has not been evaluated or intended as a
stroke-screen-critical primary extractor given the G.F.A.S.T. number above.

## What "private" means here, and how to get the weights

`herald-extractor-lora-merged-f` (and `-f4b`) are pushed to a private Hugging Face repo under the account
that trained them; `scripts/serve_models.sh` reads the repo id from `~/.config/herald/secrets.env`
(`HF_REPO_ID`), which is not in this repository. To reproduce or reuse these adapters:
1. Fine-tune your own adapter with `scripts/train_vlm_lora.py` (30B) or `scripts/train_lora.py` (4B) against
   the base models above, using `requirements-train.txt` (see `README.md`); the training data recipe is
   documented in `docs/TRAINING_PLAN.md` and `docs/MODEL_PLAN.md`, though the specific rendered/synthesized
   training rows are not committed to this repository.
2. Or ask the repo owner for read access to the existing private Hugging Face repo and point
   `HF_REPO_ID`/`HF_TOKEN` at it.

A Hugging-Face-formatted copy of this card, for the adapter repo itself, is at
[`docs/hf/README_herald-f.md`](docs/hf/README_herald-f.md).
