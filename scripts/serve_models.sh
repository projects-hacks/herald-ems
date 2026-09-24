#!/usr/bin/env bash
# Serve Herald's two local models through HP Z Runtime (ZRT, a vLLM wrapper) on http://127.0.0.1:8080/v1
# (OpenAI-compatible, localhost only). Needs the `zrt` group. One GPU: start them one at a time.
#   omni       Nemotron-3-Nano-Omni NVFP4: photo reading (and protocol-figure transcription, passage choice)
#   ems-d-fp8  the fine-tuned extractor, run D (Qwen3-4B + merged LoRA, private HF repo), FP8 weights: speech -> facts
# Measured on the GB10: omni cold start ~23 min (kernel compile, cached afterwards), warm restart ~7.6 min;
# ems-d-fp8 ~3 min. ZRT checks *free* memory, so drop the page cache of big files first if it refuses
# (scripts: see AGENTS.md pitfalls).
set -euo pipefail
[ -f ~/.config/herald/secrets.env ] && set -a && . ~/.config/herald/secrets.env && set +a
: "${HF_REPO_ID:?set HF_REPO_ID (see CONTRIBUTING.md: shared secrets)}"
export MAX_JOBS=3 NVCC_THREADS=1          # the kernel JIT can otherwise OOM the box
what="${1:-all}"
if [ "$what" = all ] || [ "$what" = omni ]; then
  sg zrt -c "zrt serve hf:nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4 --label omni --gpu-memory-fraction 0.35 \
    --extra '--max-model-len=16384' --extra '--trust-remote-code' --extra '--limit-mm-per-prompt={\"image\":2,\"video\":0,\"audio\":0}'"
fi
if [ "$what" = all ] || [ "$what" = ems ]; then
  sg zrt -c "HF_TOKEN=$HF_TOKEN zrt serve hf:${HF_REPO_ID}-merged-d --label ems-d-fp8 --gpu-memory-fraction 0.12 \
    --extra '--max-model-len=4096' --extra '--quantization=fp8'"
fi
