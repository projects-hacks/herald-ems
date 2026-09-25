---
license: apache-2.0
base_model: Qwen/Qwen3-VL-30B-A3B-Instruct
tags:
  - lora
  - qwen3-vl
  - moe
  - ems
  - information-extraction
language:
  - en
  - es
pipeline_tag: image-text-to-text
---

# herald-f

A LoRA adapter (merged into the base weights) for `Qwen/Qwen3-VL-30B-A3B-Instruct`, fine-tuned to turn
ambulance speech transcripts and photographs (patient monitors, medication labels, glucometers, and forms
such as the California POLST) into typed clinical facts for **Herald**, an offline EMS copilot built for the
HP Edge AI SJSU Hackathon (2026). Full project: https://github.com/projects-hacks/herald-ems (public).

**Not a medical device. Not clinician-reviewed. Has not shipped in the Herald product** — see Known
limitations below before using this adapter for anything beyond experimentation. This card is a copy of
[`MODEL_CARD.md`](https://github.com/projects-hacks/herald-ems/blob/main/MODEL_CARD.md) in the source
repository, formatted for a Hugging Face model card; that file is the source of truth if the two diverge.

## Model details

- **Base model:** `Qwen/Qwen3-VL-30B-A3B-Instruct` (Apache-2.0)
- **Method:** LoRA, rank 16, alpha 32, dropout 0
- **Target modules:** attention and MLP projections (`q,k,v,o,gate,up,down_proj`) under `language_model`,
  plus every MoE expert (`mlp.experts.gate_up_proj`, `mlp.experts.down_proj`). The router is frozen and the
  vision tower is untouched.
- **Trainable parameters:** 642,514,944 (13,369,344 attention/MLP + 629,145,600 experts)
- **Training:** 2 epochs, 488 steps, 17,112 rows, 5,428,833 padded tokens, on one NVIDIA GB10 (aarch64).
  Epoch 2 (of 2) is the checkpoint merged here.
- **Merged checkpoint:** BF16, 13 shards, 57.9 GiB. Typically served quantized to FP8 (block-128 on the
  language model, vision tower left in BF16) via vLLM/HP Z Runtime.
- **License:** Apache-2.0 (inherited from the base model)

## Training data

17,112 rows: 13,880 speech→facts rows (including 1,019 rows run through the production Whisper
large-v3-turbo path from Piper TTS speech mixed with cabin noise, so the model sees realistic ASR error
patterns), 2,400 photo-reading rows, and 832 "kept-ability" rows (protocol-passage reranking, protocol
figure transcription, EN↔ES translation) included so fine-tuning would not erase those base-model skills.

**All data is synthetic and AI-assisted**: generated and labeled by the project's own tooling, not collected
from real incidents. Held-out gold sets are labeled independently by two annotators with measured
inter-annotator agreement, then adjudicated — but **no data in this pipeline has been reviewed by a
clinician**. No real patient audio or photographs were used anywhere in training or evaluation.

## Evaluation

All numbers below are from the source repository's `eval/results.jsonl`, single runs unless noted; see
`MODEL_CARD.md` for the full tables, including the 4B fallback variant (`herald-f4b-fp8`).

| task | gold set | score |
|---|---|---|
| speech → facts, F1 | `gold_v2` (held-out, n=100) | 0.956 |
| speech → facts, F1 | `gold_v3` (every call type, n=100) | 0.942 |
| speech → facts, F1 | `gold_es_v1` (Spanish, n=60) | 0.931 |
| G.F.A.S.T. (stroke screen) F1 | `gold_v2` | 0.947 (one saved run); model owner's 3-run mean 0.924 — below the project's 0.95 shipping bar either way |
| photo reading, F1 (this adapter only, not the source project's shipped vision model) | synthetic camera-on-screen set (n=8) | 1.000 |
| photo reading, F1 (this adapter only) | real (non-rendered) photos | 0.727 (18 invented facts) |
| photo reading, F1 (this adapter only) | rendered forms incl. POLST | 0.578 (weak — POLST `code_status` reading is not claimed reliable) |
| protocol reranking, right passage first | all 59 questions | 0.731 (38/52) vs a required ≥0.788 (41/52) — **failed** |
| protocol reranking, top 3 | all 59 questions | 0.788 (41/52) vs a required ≥0.827 (43/52) — **failed** |
| confirmation calibration, wrong facts | 0.8 threshold, held-out | 11 of 206 auto-confirmed vs a ≤1 bar — **not recalibrated for shipping** |

**Where it wins:** transcript → facts F1 ~0.964 (3-run mean) vs. the source project's shipped extractor at
0.948–0.952 on the same held-out set, and `infection.suspected` recall 0.889 vs. the shipped extractor's
0.111. The fine-tune is a real improvement on speech extraction; it just is not a safe drop-in replacement
for the whole stack yet, because of the gates below.

## Known limitations

- **Failed the project's protocol-reranking kept-ability gate.** This adapter is measurably worse than the
  untuned base model at finding the right protocol passage, so the source project does not use it for
  reranking, protocol-figure transcription, or translation.
- **Confirmation-threshold calibration is pending.** Do not reuse the base model's or a different run's
  auto-confirm thresholds with this adapter without recalibrating.
- **G.F.A.S.T. (stroke screen) extraction F1 was 0.947 on the one saved run in the source repository's
  eval log**, and a mean of 0.924 across the model owner's 3 runs — below the source project's 0.95 bar
  either way.
- **Refusal correctness on out-of-scope protocol questions is 4 of 7** in the source repository's saved
  runs, tying (not beating) the untuned baseline on the same question set; the model owner has separately
  described this as a regression from 7 of 7, which is not what the saved runs show for that baseline —
  an open discrepancy, noted rather than resolved one way.
- **Photo reading is materially weaker on real, non-rendered photos and on POLST forms** than on the
  synthetic/rendered training distribution, and these numbers are this adapter's own — not the source
  project's shipped vision model, which is evaluated separately.
- **No end-to-end audio-to-facts evaluation exists.** All speech numbers are extraction from gold text
  transcripts, not from raw audio.
- Every number here comes from synthetic, AI-assisted, non-clinician-reviewed data; accuracy on real speech
  and real photos is expected to be lower.

## Intended use

Research and further fine-tuning for EMS-adjacent structured extraction from speech and imagery. This
adapter **does not recommend treatment, dosing, or transport decisions**, and should not be deployed in any
setting where its output could influence patient care without a qualified human confirming every fact and
without addressing the limitations above (particularly the failed rerank gate, the pending calibration
refit, and the weak real-photo/POLST numbers).

## How to use

```python
# Merged weights (this repo) served with an OpenAI-compatible server, e.g. vLLM / HP Z Runtime:
#   vllm serve <this-repo> --quantization fp8  # or fp8_per_block with the vision tower excluded; see
#   the source repository's scripts/serve_models.sh for the exact serving flags used in evaluation.
```

## Citation

If you use this adapter, please cite the Herald project (HP Edge AI SJSU Hackathon, 2026):
https://github.com/projects-hacks/herald-ems
