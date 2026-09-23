#!/usr/bin/env python3
"""Merge a trained LoRA adapter into its base model and (optionally) push it to a private HF repo.

ZRT's proxy routes requests by service label only, so a LoRA module name (vLLM --lora-modules) is listed
in /v1/models but can't be called through it (verified 2026-09-23: "unknown model name: ems"). A merged
model is served like any other: zrt serve hf:<repo> --label ems. It also skips LoRA work at decode time.

  python scripts/merge_lora.py --adapter runs/qwen3-4b-lora-a --out runs/qwen3-4b-merged-a \
      --push "$HF_REPO_ID-merged-a"
Re-run the eval on the merged model before using it (MODEL_PLAN §4).
"""
import argparse
import json
import os
from pathlib import Path

import torch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--push", default=None, help="private HF repo id to upload the merged model to")
    a = ap.parse_args()
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base_id = json.loads((Path(a.adapter) / "adapter_config.json").read_text())["base_model_name_or_path"]
    base = AutoModelForCausalLM.from_pretrained(base_id, dtype=torch.bfloat16)
    merged = PeftModel.from_pretrained(base, a.adapter).merge_and_unload()
    merged.save_pretrained(a.out, safe_serialization=True)
    AutoTokenizer.from_pretrained(a.adapter).save_pretrained(a.out)
    print(f"merged {a.adapter} into {base_id} -> {a.out}")
    if a.push:
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ["HF_TOKEN"])
        api.create_repo(a.push, private=True, exist_ok=True)
        api.upload_folder(folder_path=a.out, repo_id=a.push,
                          commit_message=f"Merged {Path(a.adapter).name} into {base_id}")
        print(f"pushed to {a.push} (private)")


if __name__ == "__main__":
    main()
