#!/usr/bin/env bash
# Serve Herald's local models through HP Z Runtime (ZRT, a vLLM wrapper) on http://127.0.0.1:8080/v1
# (OpenAI-compatible, localhost only). Needs the `zrt` group. One GPU: start them one at a time.
#   qwen3vl-fp8    Qwen3-VL-30B-A3B-Instruct FP8 (Apache-2.0): photo reading, protocol-figure transcription,
#                  passage reranking. Chosen over Nemotron-3-Nano-Omni in a level bake-off (MODEL_PLAN §2a);
#                  `omni` stays available. Untuned: this is the model Herald actually serves for reranking,
#                  figures and translation (see herald-f below).
#   ems-e-v2-fp8   the fine-tuned extractor, run E v2 (every call type + the call's dispatch) (Qwen3-4B +
#                  merged LoRA, public HF repo), FP8 weights: speech -> facts. Herald's default extraction
#                  model (README.md "Run it").
#   herald-f       run F (MODEL_PLAN §0l): ONE Qwen3-VL-30B-A3B + merged LoRA, trained on speech, photos,
#                  reranking, figures and translation. Merged, gated and confirmed servable on 2026-09-25
#                  (eval/results.jsonl), but it FAILED its own protocol-reranking kept-ability gate
#                  (MODEL_CARD.md) and its confirmation calibration is not yet refit, so it has not shipped
#                  as Herald's default extractor. Where it is used at all, it is for speech and photos ONLY,
#                  paired with the untuned qwen3vl-fp8 for reranking/figures/translation -- the split stack
#                  below. `herald-f-dry` prints the serve command without starting anything.
#   herald-f4b-fp8 run F's text-only 4B fallback (Qwen3-4B-Instruct-2507 + LoRA, public HF repo), paired
#                  with the untuned qwen3vl-fp8 for everything vision-adjacent. See MODEL_CARD.md: weaker
#                  than herald-f and than ems-e-v2-fp8 on every measured number, in particular G.F.A.S.T.
#                  F1 0.519 -- use it only when the 30B stack genuinely will not fit or will not start.
# None of these three fine-tuned/split-stack options is Herald's shipped default; see docs/RUNBOOK.md §7 and
# config/stack.yaml before switching HERALD_LLM_MODEL/HERALD_VISION_MODEL away from ems-e-v2-fp8/qwen3vl-fp8.
# Measured on the GB10: qwen3vl-fp8 ~3 min warm; omni cold start ~23 min (kernel compile, cached), warm ~3-8 min;
# ems-e-v2-fp8 ~3 min. ZRT checks *free* memory, so drop the page cache of big files first if it refuses
# (scripts: see AGENTS.md pitfalls).
set -euo pipefail
[ -f ~/.config/herald/secrets.env ] && set -a && . ~/.config/herald/secrets.env && set +a
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN   # every Herald model repo is public; a stale token makes downloads fail with 401
: "${HF_REPO_ID:=rajeev-chaurasia/herald-extractor-lora}"   # public repos: <id>-merged-e2, -merged-f, -merged-f4b
export MAX_JOBS=3 NVCC_THREADS=1          # the kernel JIT can otherwise OOM the box
what="${1:-all}"
if [ "$what" = all ] || [ "$what" = vision ]; then
  sg zrt -c "zrt serve hf:Qwen/Qwen3-VL-30B-A3B-Instruct-FP8 --label qwen3vl-fp8 --gpu-memory-fraction 0.35 \
    --extra '--max-model-len=16384' --extra '--limit-mm-per-prompt={\"image\":2,\"video\":0}'"
fi
if [ "$what" = omni ]; then                 # the previous vision model, for comparison or rollback
  sg zrt -c "zrt serve hf:nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4 --label omni --gpu-memory-fraction 0.35 \
    --extra '--max-model-len=16384' --extra '--trust-remote-code' --extra '--limit-mm-per-prompt={\"image\":2,\"video\":0,\"audio\":0}'"
fi
if [ "$what" = all ] || [ "$what" = ems ]; then
  sg zrt -c "${HF_TOKEN:+HF_TOKEN=$HF_TOKEN }zrt serve hf:${HF_REPO_ID}-merged-e2 --label ems-e-v2-fp8 --gpu-memory-fraction 0.12 \
    --extra '--max-model-len=4096' --extra '--quantization=fp8'"
fi
# Run F (MODEL_PLAN §0l). The merged checkpoint is BF16; vLLM quantizes it to FP8 while loading (layer by layer on the
# meta device, so loading needs the FP8 size, not the BF16 size). Block-128 FP8 on the language model with the vision
# tower left in BF16 mirrors the publisher's Qwen3-VL-30B-A3B-Instruct-FP8 that won the vision bake-off (§2a); the
# photo-size bound is baked into the merged preprocessor_config.json by scripts/merge_vlm_lora.py. Fallback if the
# block path fails to start on sm_121: replace the two quantization --extra's with --extra '--quantization=fp8'
# (per-tensor, the run E path; it also quantizes the vision tower, so re-run eval/vision_bench.py).
#
# herald-f IS THE SHIPPING VISION MODEL as of 2026-09-25: photos, the patient monitor, protocol-figure transcription
# AND protocol-passage reranking. It is NOT the extractor -- speech->facts stays on ems-e-v2-fp8, which wins the stroke
# screen (G.F.A.S.T. complete on 14 of 17 calls against 11-12), speaker roles (0.972 vs 0.950) and calibration (1
# wrong auto-confirm at the shipping threshold against 3). So: HERALD_VISION_MODEL=herald-f, HERALD_LLM_MODEL
# unchanged, and HERALD_KNOWLEDGE_MODEL UNSET so reranking follows the vision label onto herald-f.
#
# Yes, reranking on herald-f fails the kept-ability gate (38/52 top-1 against a 41/52 bar). It ships anyway, as a
# recorded exception: the untuned model is better at reranking by 3 questions but materially worse at real photos
# (f1 0.580 median against 0.727, monitors 0.536-0.577 against 0.713), and two resident 30B models do not fit. E v2
# was benched as the alternative reranker over 3 runs -- the task is text-only -- and scored worse still, 36/52.
# See docs/RUN_F_REPORT.md §9. An earlier version of this comment said never to point reranking at herald-f; that
# predates the vision measurements.
HERALD_F_REPO="${HF_REPO_ID}-merged-f"
# PER-TENSOR FP8, and it must stay that way: every published herald-f number (photos, camera renders, forms,
# reranking, figures, speech) was measured on this exact argument list. The fp8_per_block path described above has
# never been started on sm_121, so switching to it would invalidate the numbers rather than confirm them.
HERALD_F_ARGS="--label herald-f --gpu-memory-fraction 0.35 \
    --extra '--max-model-len=16384' --extra '--limit-mm-per-prompt={\"image\":2,\"video\":0}' \
    --extra '--quantization=fp8'"
if [ "$what" = herald-f-dry ]; then         # print exactly what would run (token elided), start nothing
  printf 'sg zrt -c %q\n' "HF_TOKEN=*** zrt serve hf:${HERALD_F_REPO} ${HERALD_F_ARGS}"   # copy-pasteable quoting
  echo "# the command sg runs (what zrt receives): HF_TOKEN=*** zrt serve hf:${HERALD_F_REPO} ${HERALD_F_ARGS}"
fi
if [ "$what" = herald-f ]; then
  sg zrt -c "${HF_TOKEN:+HF_TOKEN=$HF_TOKEN }zrt serve hf:${HERALD_F_REPO} ${HERALD_F_ARGS}"
fi

# herald-f's text-only 4B fallback (TRAINING_PLAN §7): serve with ems-e-v2-fp8's argument shape, per
# config/gates.yaml's f4b level. Pair with `scripts/serve_models.sh vision` (untuned qwen3vl-fp8), never with
# herald-f. Weaker than both ems-e-v2-fp8 and herald-f on every measured number (MODEL_CARD.md); use only when
# the 30B stack will not fit or will not start.
if [ "$what" = f4b ]; then
  sg zrt -c "${HF_TOKEN:+HF_TOKEN=$HF_TOKEN }zrt serve hf:${HF_REPO_ID}-merged-f4b --label herald-f4b-fp8 --gpu-memory-fraction 0.12 \
    --extra '--max-model-len=4096' --extra '--quantization=fp8'"
fi

# ---------------------------------------------------------------------------------------------------------------
# SPLIT STACK (TRAINING_PLAN §7a). Commented out on purpose: use it ONLY if both epoch adapters win speech and
# photos but fail the kept-ability gates (rerank 59q, 700-A13 figure, translation). Two resident 30B models.
#
#   herald-f       extraction + photo reading      (HERALD_LLM_MODEL=herald-f, HERALD_VISION_MODEL=herald-f)
#   qwen3vl-fp8    reranking, figures, translation (HERALD_KNOWLEDGE_MODEL=qwen3vl-fp8)
#
# Both labels answer on the same endpoint: ZRT's proxy routes by label on 127.0.0.1:8080 (proxy.json is one
# host/port with a `services` list), so the app needs no second URL.
#
# FULL PROCEDURE: docs/RUNBOOK.md §7 (when to use it, the fit check, verification, rollback). Read it first.
#
# MEMORY WARNING, read before uncommenting. At --gpu-memory-fraction 0.30 each model gets ~36 GiB of the 121.6 GiB.
# ~31 GiB of that is FP8 weights, leaving only ~5 GiB for the KV cache, and vLLM refuses to start if the cache
# cannot hold one --max-model-len sequence. So --max-model-len MUST come down from 16384 for both; 8192 clears the
# largest real job (figure transcription, ~2.7k tokens). The two together (~72 GiB) still have to coexist with the
# app, Whisper and the page cache. Measure first, with the app and Whisper already up (RUNBOOK §7.1):
#     scripts/memguard.sh status && grep MemAvailable /proc/meminfo
# and only then start them, one at a time. If it does not fit, prefer shipping epoch 1 (§6a rule 2) or the §7
# rollback. UNTESTED: this has never been started (the box was training when it was written).
# if [ "$what" = split ]; then
#   sg zrt -c "${HF_TOKEN:+HF_TOKEN=$HF_TOKEN }zrt serve hf:${HERALD_F_REPO} --label herald-f --gpu-memory-fraction 0.30 \
#     --extra '--max-model-len=8192' --extra '--limit-mm-per-prompt={\"image\":2,\"video\":0}' \
#     --extra '--quantization=fp8'"
#   # wait for Ready, then:
#   sg zrt -c "zrt serve hf:Qwen/Qwen3-VL-30B-A3B-Instruct-FP8 --label qwen3vl-fp8 --gpu-memory-fraction 0.30 \
#     --extra '--max-model-len=8192' --extra '--limit-mm-per-prompt={\"image\":2,\"video\":0}'"
# fi
