#!/usr/bin/env bash
# Serve the local models through HP Z Runtime (ZRT, a vLLM wrapper). One GPU, so one heavy job at a time.
# API: http://127.0.0.1:8080/v1 (OpenAI-compatible, localhost only). Needs membership in the `zrt` group.
set -euo pipefail
MODEL="${HERALD_VLM:-hf:nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4}"
sg zrt -c "zrt serve $MODEL --label omni --gpu-memory-fraction 0.35 --extra '--max-model-len=16384' --extra '--trust-remote-code'"
