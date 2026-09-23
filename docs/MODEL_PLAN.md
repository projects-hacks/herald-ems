# Model plan (evidence first, then measured on this box)

Status: **DRAFT.** All three research reports are in. Bake-off (M2) runs as soon as the first model serves; the text-model choice locks on its numbers.
Rule: published benchmarks pick the candidates; our own benchmark on `eval/gold_v0.jsonl` picks the winner. Nothing is locked without a number from this box.

## Facts about this box that drive every choice
- GB10 memory bandwidth is **273 GB/s** (NVIDIA). Decode speed is bandwidth-bound, so **active parameters per token decide latency**. MoE models with about 3B active parameters (30B-A3B) in 4-bit decode at 50–75 tok/s; dense 27B models at 15–25 tok/s.
- **Output length dominates latency**: each 10 JSON tokens costs about 150 ms. Our extractor therefore emits compact arrays (`{"f":[[key,value,who]]}`), only keys that are present, under a strict JSON schema, with `max_tokens` capped at 256.
- Runtime: HP Z Runtime (ZRT) wraps **vLLM 0.26.0**. vLLM flags must go after `--` or in `--extra`. The organizers' example command fails as written (`unknown flag: --tensor-parallel-size`).

## 1. Text model (live extraction)
| Rank | Model | Active | Decode on GB10 (measured by others) | 150-tok latency (est.) | Instruction-following evidence | vLLM 0.26 status |
|---|---|---|---|---|---|---|
| **Primary** | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4` | 3.5B | 67 tok/s, TTFT 52 ms; 74.75 with a patched vLLM | ~2.3 s | IFBench 71.5, BFCL-v4 53.8 | OK. NVFP4 instability reports: use Marlin, soak test |
| **Fallback** | `Qwen/Qwen3-30B-A3B-Instruct-2507-FP8` | 3.3B | ~52 (FP8) | ~2.9 s | IFEval 84.7, BFCL-v3 65.1; no thinking mode | mature |
| Also in the bake-off | `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4` | ~3B | 57–62, TTFT 309 ms at a 2k prompt | ~2.6 s | none published for text | OK (loading now). **One model could serve both text and vision** |
| Upgrade later | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` | 3B | 81; 124 with speculative decoding | 1.2–1.9 s | IFBench 72.9 | **needs vLLM ≥ 0.27.1; not available in ZRT** |
| No | `Inferact/Qwen3.8-27B-NVFP4` (the organizers' example) | 27B dense | 15–25 | 6–10 s | thinks by default | too slow for a live loop; fine for offline summaries |
| No | `openai/gpt-oss-20b` | 3.6B | 50–83 | — | reasoning cannot be switched off | — |
| No | dense 4B/8B in BF16 | — | 20–24 | 3–7 s | — | about 3× slower than an A3B MoE in 4-bit |

**Serve flags (primary):**
```bash
export C_INCLUDE_PATH=$HOME/miniforge3/envs/zgx/include/python3.12 CPLUS_INCLUDE_PATH=$C_INCLUDE_PATH MAX_JOBS=3 NVCC_THREADS=1
sg zrt -c "zrt serve hf:nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4 --label extractor --gpu-memory-fraction 0.25 -- \
  --trust-remote-code --max-model-len 8192 --max-num-seqs 4 --kv-cache-dtype fp8 --moe-backend marlin \
  --enable-prefix-caching --default-chat-template-kwargs '{\"enable_thinking\": false}'"
```
**Every request:** `response_format=json_schema (strict)`, `temperature=0`, `max_tokens=256`, `chat_template_kwargs={"enable_thinking": false}`; no reasoning parser on the extractor.

**Pitfalls to watch:**
- NVFP4 MoE on sm_121: confirm MARLIN in the startup log; run a 30-minute soak test.
- JSON-schema whitespace runaway: always cap `max_tokens`.
- Thinking + structured output can emit thousands of `{`: keep thinking off.
- earlyoom can kill the engine silently: set `--gpu-memory-fraction` per service.

**Pithy finding for the deck (once we reproduce it):** "A 30B-A3B NVFP4 MoE decodes about 3.5× faster than the dense 27B NVFP4 in the organizers' example (67 vs 15–19 tok/s)."

## 2. Vision (photo reading)
| Rank | Model | Active | OCRBench / DocVQA | Latency per photo on Spark | Notes |
|---|---|---|---|---|---|
| **Primary** | `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4` | 3B | 88.3 / 93.3 (thinking off) | **0.67–2.04 s measured** (108-token JSON), decode 57–60 tok/s | NVFP4 loses < 1 point vs BF16. RefCOCO box grounding 80.6. **Also a text-model candidate: one model for both saves ~20 GB and a process.** |
| **Fallback** | `nvidia/Qwen3.6-35B-A3B-NVFP4` | 3B | OCRBench-v2 EN 65.5; RefCOCO 92.0 | ~1.5–2 s (est.) | switch if digit accuracy or boxes fall short on our photos |
| No | dense 7–9B VLMs (Qwen3-VL-8B, Qwen2.5-VL-7B) | 7–9B | 864–896 / 95–96 | 5–8 s (est.) | over the 3 s budget on 273 GB/s |
| No | Gemma 4 31B | 31B dense | — | 9.78 s measured on the same test | too slow |

**Reality check (MeasureBench):** on real photos of digital displays such as pulse oximeters, open models read 49–65% correctly and the best model 80%. So every photo reading is validated in code (SpO2 50–100, HR 20–250, SBP > DBP), shown as unconfirmed, and confirmed by the medic. A failed validation or a null triggers a retry on a crop, then "ask the medic". Photo-reading accuracy on our own prop photos (P5.4) is a deck metric.

**Serve command (primary, with the fixes from this box):**
```bash
export C_INCLUDE_PATH=$HOME/miniforge3/envs/zgx/include/python3.12 CPLUS_INCLUDE_PATH=$C_INCLUDE_PATH MAX_JOBS=3 NVCC_THREADS=1
sg zrt -c "zrt serve hf:nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4 --label omni --gpu-memory-fraction 0.35 --   --trust-remote-code --max-model-len 16384 --max-num-seqs 8 --limit-mm-per-prompt '{"image":2,"video":0,"audio":0}'   --kv-cache-dtype fp8 --mamba-ssm-cache-dtype float32 --reasoning-parser nemotron_v3   --default-chat-template-kwargs '{"enable_thinking":false}' --mm-processor-cache-gb 0"
```
If output is garbage or UNK tokens: `VLLM_NVFP4_GEMM_BACKEND=marlin VLLM_USE_FLASHINFER_MOE_FP4=0 VLLM_MARLIN_USE_ATOMIC_ADD=1` and/or `--moe-backend marlin`.

**Prompt rules:**
- Per field: `{raw_text, value|null, legible, bbox}`.
- "Copy digits exactly; never infer; null if unclear."
- Say where each label sits.
- Check Omni's box coordinate convention on one image (Qwen3 VL uses 0–1000).
- EXIF-rotate the image and resize the long side to about 1600 px.
- Warm up before the demo: the first request compiles.

## 3. Speech-to-text and TTS
| Model | Open ASR avg WER | Speed (RTFx) | Spanish | On this box |
|---|---|---|---|---|
| **whisper-large-v3-turbo (keep)** | 7.83 | 200 | yes (CV es 6.91%) | **measured here: 10.4 s clip in 0.31 s, 1.7 GiB** |
| parakeet-tdt-0.6b-v3 (optional upgrade) | 6.32 | 3330 | 25 languages; noisy speech 4.82% at 0 dB | `ParakeetForTDT` is in the installed transformers 5.17; no NeMo needed |
| canary-1b-v2 | 7.15 | 749 | yes + En↔Es translation | in transformers 5.17 |
| NeMo-only models (canary-1b-flash, canary-qwen-2.5b) | — | — | — | avoid on aarch64 |

**Decision:** keep Whisper (fast enough, auto-detects Spanish, no integration risk). Try Parakeet-v3 only if P1–P6 are green, on ~10 of our own EMS clips; switch only if numbers and drug names improve. **Don't denoise before ASR** (worse in 40/40 medical settings); trim silence instead, since Whisper's ~1% hallucinations cluster around pauses.
**TTS (optional interpreter):** Kokoro-82M (Apache-2.0; Spanish voices ef_dora, em_alex; runs on DGX Spark); Piper as fallback.

## 4. Fine-tuning plan (P10: bonus, never on the critical path; hard stop Thu 6 PM)
**Task:** LoRA SFT, paramedic utterance → compact triples `[["vitals.spo2",94,"medic"],…]`, the same format the live extractor emits.

| Decision | Choice | Why (evidence) |
|---|---|---|
| Base | **Qwen3-4B-Instruct-2507** (run A); **Qwen3-1.7B** (run B, latency backup) | Dense, no thinking mode, IFEval 83.4 (≈ Qwen3-30B-A3B's 83.7). vLLM LoRA support. NVIDIA's LLaMA-Factory Spark playbook fine-tunes Qwen3-4B. Rejected: hybrid Mamba/DeltaNet models (kernel builds on sm_121), Llama 3.2 3B (IFEval 77.4), 12B (≈11 tok/s: too slow live). |
| Framework | **HF PEFT 0.21 + TRL 1.13 SFTTrainer** in the `zgx` env (`pip install --no-deps peft==0.21.0 trl==1.13.0`) | Unsloth/NeMo are container-only on Spark with older pins. torchtune 0.6.1 has no Qwen3 and is discontinued. |
| Precision | **BF16 LoRA, not QLoRA** | 4B = ~8 GB of 121 GiB. QLoRA adds bitsandbytes risk on GB10. |
| Hyperparameters | r=16, α=32, dropout 0.05, all-linear; lr 2e-4 cosine, 5% warmup; effective batch 16; **2 epochs** (max 3); max_length 512; eval every ½ epoch, keep the best dev F1 | LoRA best lr ≈ 10× full FT; all-linear beats attention-only; r16 = vLLM default max rank |
| sm_121 settings | `attn_implementation="sdpa"`; packing **off**; no torch.compile; `gradient_checkpointing=False`; load in BF16 (TRL defaults to fp32) | flash-attn has no sm121 kernels; the Triton ptxas sm_121a error |
| Data | 2,000 synthetic, **reverse-generated**: code samples a fact bundle + phenomena (shorthand, spoken numbers, negation, self-correction, attribution). Omni writes 5 utterances per bundle. **The label is the bundle, never the LLM.** Reject utterances where a gold value isn't findable. ≥40 templates; 10–15% with no facts; ASR noise on ~50%. **Split by template.** | SynthIE; diversity > volume; random splits overstate |
| Time | Data gen 25–70 min; train 4–50 min per run (1.5M tokens); budget 1.5 h per run | measured Spark LoRA throughput 700–7,000 tok/s |
| Expected | Base 4B ≈ 0.6–0.8 F1 → **LoRA 0.90–0.96** on held-out templates; a few points lower on real speech | merchant-extraction LoRA paper: +0.21 to +0.92 F1, Qwen 4B 0.758 → 0.966; EMSLlama LoRA 8B beat GPT-4o on noisy EMS transcripts (0.89 vs 0.57 exact match) |
| Latency (est.) | 4B BF16 ≈ 20 tok/s (≈3 s for 60 tokens: **misses 2 s**); 4B FP8 or 1.7B BF16 ≈ 40 tok/s (≈1.5 s) | bandwidth-bound decode |
| Serving | **ZRT only serves `hf:` / `azureml:` / `mlflow:`**, so push the adapter or merged model to a **private HF repo** (`HF_TOKEN`, `HF_REPO_ID`, as the organizers' handout says) and serve with `--enable-lora --lora-modules ems=<hf repo>`, or merge and serve the merged repo. Fallback: run `vllm serve <local path>` from the ZRT venv directly. | Re-run the eval after any merge or quantization. Check outputs differ from base (silent no-op adapter bug). **No LoRA on NVFP4 bases.** |

**Go/no-go (first 30 minutes, before committing the day):**
1. `pip check` passes; torch still 2.14.0+cu130.
2. Smoke train on 64 examples, 10 steps: loss falls, no NaN, memory < 40 GB, projected run < 90 min.
3. The adapter covers 7 projection layers.
4. The adapter loads in ZRT/vLLM; outputs differ from base; JSON parses.
5. 20 requests: p50 vs 2 s; `nvidia-smi --query-gpu=power.draw`.

Any failure → ship rules + Omni, and present the fine-tune as a slide with whatever numbers exist.

**Thursday timeline:**

| Time | Step |
|---|---|
| 08:30 | Go/no-go |
| 09:00 | Data frozen; base-model evals |
| 09:30 | Train run A |
| 11:00 | Evaluate A |
| 11:30 | Train run B (1.7B) |
| 13:00 | Latency: LoRA vs merged vs FP8 |
| 14:30 | Integrate |
| 16:00 | Final table: F1, exact match, JSON validity, role accuracy, p50/p95, joules per utterance |
| 17:30 | Freeze |

**Don't:** Unsloth or NeMo containers · QLoRA · build flash-attn or xformers · packing or torch.compile · hybrid Mamba models for the fine-tune · a 12B model in the live path · random splits · labels written by the LLM · > 3 epochs · thinking on · LoRA on NVFP4 · merge + FP8 without a re-eval · training while a teammate swaps models.

## 5. Bake-off protocol (M2), same for every candidate
1. Serve the candidate with the flags above; check `/v1/models`.
2. `python eval/bench_extract.py --extractor llm --model <label> --verbose` on the gold set → F1, role accuracy, JSON-invalid count, p50/p95 latency, output tokens, decode tok/s.
3. Run the rules baseline on the same set (F1 0.852 at `gold_v0`).
4. Pick the model with the best F1 at p95 latency ≤ 2 s. Tie → prefer the model that also reads photos (one model, less memory).
5. Record results below and in `eval/results.jsonl`.

| Extractor | F1 | Role acc | JSON invalid | p50 / p95 ms | Out tokens | tok/s |
|---|---|---|---|---|---|---|
| rules (baseline) | 0.852 | 0.942 | 0 | 0 / 0 | — | — |
