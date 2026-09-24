#!/usr/bin/env python3
"""LoRA fine-tune of the extractor (P10) with HF PEFT + TRL, BF16, on the GB10.

  # go/no-go smoke test (10 steps on 64 rows): loss must fall, no NaN, memory < 40 GB
  python scripts/train_lora.py --smoke
  # real run
  python scripts/train_lora.py --base Qwen/Qwen3-4B-Instruct-2507 --epochs 2 --out runs/qwen3-4b-lora

The fine-tuned model is trained on a SHORT prompt (no key list, no worked examples): that removes
~1,200 prompt tokens per call versus the base-model extractor. Inference must use SHORT_SYSTEM too.
Settings follow docs/MODEL_PLAN.md §4 (sdpa attention, no packing, no torch.compile, BF16 load).
"""
import argparse
import json
import os
import time
from pathlib import Path

import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from herald.extraction.profiles import default_profiles  # noqa: E402


def system_prompt(profile_prefix: str) -> str:
    """The prompt the served extractor will use for this label (config/extraction.yaml): train and serve alike."""
    profile = default_profiles().for_label(profile_prefix)
    if profile is None:
        raise SystemExit(f"no fine-tuned profile matches {profile_prefix!r} in config/extraction.yaml")
    return profile.prompt


def rows(path, system: str, limit=None):
    out = []
    for line in open(path):
        r = json.loads(line)
        out.append({"prompt": [{"role": "system", "content": system}, {"role": "user", "content": r["text"]}],
                    "completion": [{"role": "assistant", "content": r["completion"]}]})
        if limit and len(out) >= limit:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--data", default="data/synth")
    ap.add_argument("--out", default="runs/smoke")
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--accum", type=int, default=2)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--profile", default="ems", help="served-label prefix whose prompt to train with (ems-d for run D)")
    a = ap.parse_args()

    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    limit = 64 if a.smoke else None
    system = system_prompt(a.profile)
    train = Dataset.from_list(rows(Path(a.data) / "train.jsonl", system, limit))
    dev = Dataset.from_list(rows(Path(a.data) / "dev.jsonl", system, 32 if a.smoke else None))
    tok = AutoTokenizer.from_pretrained(a.base)
    cfg = SFTConfig(
        output_dir=a.out, num_train_epochs=a.epochs, max_steps=10 if a.smoke else -1,
        per_device_train_batch_size=a.batch, gradient_accumulation_steps=a.accum,
        per_device_eval_batch_size=a.batch, learning_rate=a.lr, lr_scheduler_type="cosine", warmup_steps=0.05,   # transformers 5: a fraction <1 is a ratio
        bf16=True, logging_steps=1 if a.smoke else 10, eval_strategy="steps",
        eval_steps=5 if a.smoke else max(1, int(len(train) / (a.batch * a.accum) / 2)),
        save_strategy="no" if a.smoke else "steps", save_steps=max(1, int(len(train) / (a.batch * a.accum) / 2)),
        load_best_model_at_end=not a.smoke, metric_for_best_model="eval_loss",
        max_length=512, packing=False, gradient_checkpointing=False, report_to=[],
        model_init_kwargs={"dtype": torch.bfloat16, "attn_implementation": "sdpa"},
    )
    lora = LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM")
    trainer = SFTTrainer(model=a.base, args=cfg, train_dataset=train, eval_dataset=dev, processing_class=tok, peft_config=lora)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    res = trainer.train()
    dt = time.time() - t0
    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h]
    evals = [h["eval_loss"] for h in trainer.state.log_history if "eval_loss" in h]
    toks = sum(len(tok.apply_chat_template(r["prompt"] + r["completion"], tokenize=True)) for r in rows(Path(a.data) / "train.jsonl", system, limit))
    steps = trainer.state.global_step
    report = {"steps": steps, "seconds": round(dt, 1), "loss_first": losses[:1], "loss_last": losses[-1:],
              "eval_loss": evals, "nan": any(x != x for x in losses),
              "peak_gpu_mem_gib": round(torch.cuda.max_memory_allocated() / 2**30, 1),
              "train_tokens_per_epoch": toks,
              "est_tokens_per_s": round(toks * (steps * a.batch * a.accum / max(1, len(train))) / dt, 1)}
    trainer.save_model(a.out)
    print(json.dumps(report, indent=1))
    adapter = Path(a.out) / "adapter_config.json"
    if adapter.exists():
        c = json.load(open(adapter))
        print("adapter target modules:", sorted(c.get("target_modules") or []))


if __name__ == "__main__":
    main()
