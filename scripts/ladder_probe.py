#!/usr/bin/env python3
"""Memory ladder for the 30B run: prove each stage fits before committing to a ~6 h training run.

The 30B died twice during `from_pretrained` on 2026-09-25 (MemAvailable 114 -> 8 GiB, the guard killed the critical
job). The streaming loader in lora_common fixes the load; these rungs measure that claim and the stages after it, one
at a time, with the box exclusive. Every rung records MemAvailable at 10 Hz to <out>/mem.jsonl and prints its
low-water mark, so a rung that fails leaves evidence.

  scripts/run_job.py --name rung1 --priority critical --gpu --need-gib 80 -- \
      python scripts/ladder_probe.py --rung 1 --out runs/ladder/rung1

Rung 1  load only, then greedy-generate on 3 prompts. The 2B equality test has no MoE, so the expert path is first
        exercised here: a wrong expert layout produces gibberish (and, at rung 3, a loss near 10 instead of < 3).
Rung 2  + PEFT (attention + every expert) + the optimizer state.
Rungs 3-5 are the trainer itself (--max-steps / --save-steps / --resume), not this script.

PASS for every rung: min MemAvailable >= 20 GiB.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lora_common import (MemorySampler, load_model, mem_available_gib,  # noqa: E402
                         summarize_memory, system_prompt)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS_MIN_AVAIL_GIB = 20.0
GEN_TOKENS = 24
PASS_FIRST_LOSS = 3.0        # a wrong expert layout gives gibberish and a loss near 10+, not a pretrained-range loss


def param_group(name: str) -> str:
    """Which part of the model a trainable tensor belongs to.

    PEFT reaches the fused MoE experts through `target_parameters` (§0l), which is newer code than `target_modules`.
    If it silently did nothing, only attention would be trainable: the run would still train and the loss would still
    fall, while the experts — where almost all of the per-token computation lives — learned nothing. So the groups are
    counted separately and the run refuses to continue if the experts are empty.
    """
    if ".visual." in name or name.startswith("visual."):
        return "vision_tower"
    # PEFT's `target_parameters` names an expert LoRA after the *wrapper*, not after the target parameter:
    #   layers.N.mlp.experts.base_layer.lora_{A,B}.default.weight   (one target)
    #   layers.N.mlp.experts.lora_{A,B}.default.weight              (the other)
    # so matching "experts.gate_up_proj" / "experts.down_proj" finds nothing even when the attachment worked.
    # Checked first, because "experts.down_proj" also contains "down_proj".
    if ".mlp.experts." in name or "experts.gate_up_proj" in name or "experts.down_proj" in name:
        return "experts"
    if any(f".{p}." in name or name.endswith(f".{p}") for p in ("q_proj", "k_proj", "v_proj", "o_proj")):
        return "attention"
    if ".mlp.gate." in name:                 # the router; must stay frozen
        return "router"
    if any(f".{p}." in name for p in ("gate_proj", "up_proj", "down_proj")):
        return "dense_mlp"                   # matches nothing in this MoE; present for a dense Qwen3-VL
    return "other"


def trainable_breakdown(model) -> dict:
    """Trainable parameter counts per group, plus a few names per group so the attachment is visible."""
    groups: dict[str, dict] = {}
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        g = param_group(name)
        d = groups.setdefault(g, {"params": 0, "tensors": 0, "examples": []})
        d["params"] += p.numel()
        d["tensors"] += 1
        if len(d["examples"]) < 3:
            d["examples"].append(f"{name} {tuple(p.shape)}")
    # every group that exists in the model at all, so a 0 is explicit rather than a missing key
    for g in ("attention", "experts", "router", "vision_tower", "dense_mlp", "other"):
        groups.setdefault(g, {"params": 0, "tensors": 0, "examples": []})
    groups["TOTAL"] = {"params": sum(v["params"] for k, v in groups.items() if k != "TOTAL"),
                       "tensors": sum(v["tensors"] for k, v in groups.items() if k != "TOTAL"),
                       "examples": []}
    return groups


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rung", type=int, required=True, choices=(1, 2, 3))
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default="herald-f")
    ap.add_argument("--base", default=None, help="override the base model (a 2B for a dry check)")
    ap.add_argument("--no-stream-load", action="store_true", help="use from_pretrained (the path that failed)")
    ap.add_argument("--no-generate", action="store_true", help="skip the generation check in rung 1")
    return ap.parse_args()


def _generation_cases(cfg: dict) -> list[dict]:
    """Three prompts: plain knowledge, the real extraction prompt, and a real photo row with its own prompt."""
    cases = [{"name": "plain", "system": None, "user": "The capital of France is", "image": None}]
    try:
        cases.append({"name": "extraction", "system": system_prompt(cfg["label"]),
                      "user": "BP 158 over 92, heart rate 104, she takes Eliquis", "image": None})
    except SystemExit as e:
        cases.append({"name": "extraction", "skipped": str(e)})
    dev = ROOT / cfg["data"]["image"] / "dev.jsonl"
    if dev.exists():
        row = json.loads(dev.read_text().splitlines()[0])
        img = ROOT / row["image"]
        if img.exists():
            cases.append({"name": f"photo:{row['mode']}", "system": row["system"], "user": row["user"],
                          "image": str(img), "target": row.get("target")})
    return cases


def generate(model, processor, cases: list[dict]) -> list[dict]:
    """Greedy generation, prompts built exactly as the trainer/app render them."""
    import torch
    from PIL import Image

    out = []
    for c in cases:
        if c.get("skipped"):
            out.append(c)
            continue
        content = [{"type": "text", "text": c["user"]}]
        images = None
        if c.get("image"):
            content.append({"type": "image"})
            images = [Image.open(c["image"]).convert("RGB")]
        messages = ([{"role": "system", "content": c["system"]}] if c.get("system") else []) + \
                   [{"role": "user", "content": content}]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=images, return_tensors="pt").to(model.device)
        t0 = time.time()
        with torch.no_grad():
            ids = model.generate(**inputs, max_new_tokens=GEN_TOKENS, do_sample=False,
                                 pad_token_id=processor.tokenizer.eos_token_id)
        new = ids[0][inputs["input_ids"].shape[1]:]
        text_out = processor.tokenizer.decode(new, skip_special_tokens=True)
        rec = {"case": c["name"], "generated": text_out, "seconds": round(time.time() - t0, 1)}
        if c["name"].startswith("photo") or c["name"] == "extraction":
            try:
                json.loads(text_out)
                rec["valid_json"] = True
            except ValueError:
                rec["valid_json"] = False        # 24 tokens may simply truncate; read the text before judging
        if c.get("target"):
            rec["gold_target"] = c["target"]
        out.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    return out


def grad_norms(model) -> dict:
    """Gradient norm per group after a backward, with the experts' lora_A and lora_B separated.

    Standard LoRA initialises A from a normal distribution and **B to zeros**, so on the very first step
    `grad(A) = Bᵀ · dL/dy · xᵀ` is exactly zero by construction while `grad(B) = dL/dy · (Ax)ᵀ` is not. So only
    **B's** norm is diagnostic on step 1: if the expert lora_B norm is zero, the fused MoE forward is not routing
    through the wrapped parameter and the experts would never learn, however many parameters `requires_grad`.
    """
    import torch

    acc: dict[str, list] = {}
    for name, p in model.named_parameters():
        if not p.requires_grad or p.grad is None:
            continue
        g = param_group(name)
        which = "lora_A" if ".lora_A" in name else ("lora_B" if ".lora_B" in name else "other")
        acc.setdefault(f"{g}.{which}", []).append(p.grad.detach().float().pow(2).sum())
    return {k: round(float(torch.stack(v).sum().sqrt()), 6) for k, v in sorted(acc.items())}


def forward_backward(model, cfg: dict, out: Path) -> dict:
    """One optimizer step's worth of micro-batches, exactly as the trainer computes it.

    Uses the real plan (same seed, same token budget), and deliberately picks the **largest** micro-batches that
    contain image rows, because those are the run's memory worst case.
    """
    import torch

    from train_vlm_lora import Plan, RowDataset, collate_rows, load_data
    from vlm_data import Encoder
    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(cfg["base"])
    enc = Encoder(processor, cfg["image"]["max_pixels"], cfg["image"]["min_pixels"])
    train = load_data(cfg, "train", None)
    plan = Plan(cfg, enc, train)
    ds = RowDataset(plan.rows, enc)

    # the worst case: the micro-batches with the most padded tokens that include an image row
    def padded(bt):
        return len(bt) * max(plan.lengths[i] for i in bt)

    with_image = [bt for bt in plan.batches if any(plan.rows[i].kind == "image" for i in bt)]
    chosen = sorted(with_image or plan.batches, key=padded, reverse=True)[:plan.accum]
    info = {"micro_batches": [{"rows": len(bt), "padded_tokens": padded(bt),
                               "kinds": sorted({plan.rows[i].kind for i in bt})} for bt in chosen]}
    print(json.dumps({"chosen_micro_batches": info["micro_batches"]}), flush=True)

    model.train()
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    torch.cuda.reset_peak_memory_stats()
    losses, answer_tokens, logits_bytes = [], 0, 0
    t0 = time.time()
    for bt in chosen:
        batch = collate_rows([ds[i] for i in bt], enc.pad_id)
        batch.pop("_row_ids", None)
        batch = {k: (v.to(model.device) if hasattr(v, "to") else v) for k, v in batch.items()}
        labels = batch.pop("labels")
        targets = labels[:, 1:]
        keep = targets.ne(-100).any(0).nonzero().squeeze(-1)
        res = model(**batch, use_cache=False, logits_to_keep=keep)
        logits = res.logits.float()                       # the trainer upcasts; measure what that costs
        logits_bytes = max(logits_bytes, logits.numel() * logits.element_size())
        tgt = targets[:, keep]
        n = int(tgt.ne(-100).sum())
        loss = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), tgt.reshape(-1),
                                                 ignore_index=-100, reduction="sum") / max(n, 1)
        (loss / len(chosen)).backward()
        losses.append(float(loss)); answer_tokens += n
        del res, logits, loss
    seconds = time.time() - t0

    norms = grad_norms(model)
    padded_tokens = sum(padded(bt) for bt in chosen)
    first_loss = sum(losses) / len(losses)
    problems = []
    if norms.get("experts.lora_B", 0) <= 0:
        problems.append("expert lora_B gradient is zero: the fused MoE forward is not routing through the wrapped "
                        "parameter, so the experts would never learn")
    if norms.get("attention.lora_B", 0) <= 0:
        problems.append("attention lora_B gradient is zero")
    if not (first_loss < PASS_FIRST_LOSS):
        problems.append(f"first-step loss {first_loss:.3f} is not < {PASS_FIRST_LOSS} — a wrong expert layout gives "
                        "gibberish and a loss near 10")
    res = {"first_loss": round(first_loss, 4), "per_micro_batch_loss": [round(x, 4) for x in losses],
           "grad_norm_by_group": norms, "gradient_problems": problems,
           "answer_tokens": answer_tokens, "padded_tokens_in_step": padded_tokens,
           "seconds_per_optimizer_step": round(seconds, 2),
           "padded_tokens_per_s": round(padded_tokens / seconds, 1),
           "logits_upcast_to_fp32": True, "logits_fp32_gib": round(logits_bytes / 2**30, 2),
           "torch_peak_gib_in_step": round(torch.cuda.max_memory_allocated() / 2**30, 2),
           **{"after_backward": summarize_memory(out / "mem.jsonl")}, **info}
    print(json.dumps({k: v for k, v in res.items() if k != "after_backward"}, indent=1), flush=True)
    for p_ in problems:
        print(json.dumps({"PROBLEM": p_}), flush=True)
    return res


def main() -> None:
    a = parse_args()
    from herald.config import load_yaml

    cfg = load_yaml("training.yaml")[a.config]
    base = a.base or cfg["base"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    start_avail = mem_available_gib()
    print(json.dumps({"rung": a.rung, "base": base, "start_mem_available_gib": round(start_avail, 1),
                      "stream": not a.no_stream_load}), flush=True)

    sampler = MemorySampler(out / "mem.jsonl").start()
    report: dict = {"rung": a.rung, "base": base, "stream": not a.no_stream_load,
                    "start_mem_available_gib": round(start_avail, 1)}
    try:
        import torch

        t0 = time.time()
        model = load_model(base, stream=not a.no_stream_load)
        report["load_seconds"] = round(time.time() - t0, 1)
        report["after_load"] = summarize_memory(out / "mem.jsonl")
        print(json.dumps({"loaded": report["load_seconds"], **report["after_load"]}), flush=True)

        if a.rung == 1 and not a.no_generate:
            from transformers import AutoProcessor

            processor = AutoProcessor.from_pretrained(base)
            model.eval()
            report["generations"] = generate(model, processor, _generation_cases(cfg))

        if a.rung >= 2:
            from peft import get_peft_model

            from train_vlm_lora import lora_config

            model.config.use_cache = False
            model = get_peft_model(model, lora_config(cfg, model))
            groups = trainable_breakdown(model)
            report["trainable"] = groups
            print(json.dumps({"trainable_by_group":
                              {k: v["params"] for k, v in groups.items()}}, indent=1), flush=True)
            for g in ("attention", "experts"):
                print(json.dumps({g: groups[g]["examples"]}, indent=1), flush=True)
            # The checks that make a silent attention-only fallback impossible to miss.
            problems = []
            n_layers = len(getattr(model.base_model.model.model, "language_model").layers)
            want_expert_tensors = 4 * n_layers          # 2 target parameters x lora_A + lora_B, per layer
            if groups["experts"]["params"] == 0:
                problems.append("PEFT attached no LoRA to the fused experts (target_parameters did nothing): the "
                                "run would train attention only")
            elif groups["experts"]["tensors"] != want_expert_tensors:
                # a partial attachment (only gate_up_proj, say) would still be non-zero and still look fine
                problems.append(f"expert LoRA has {groups['experts']['tensors']} tensors, expected "
                                f"{want_expert_tensors} (2 target parameters x A/B x {n_layers} layers)")
            if groups["attention"]["params"] == 0:
                problems.append("no LoRA on attention")
            if groups["other"]["params"]:
                problems.append(f"{groups['other']['params']} trainable params are unclassified: {groups['other']['examples']}")
            report["n_layers"] = n_layers
            report["expert_tensors_expected"] = want_expert_tensors
            if groups["router"]["params"]:
                problems.append(f"the router is trainable ({groups['router']['params']} params); it must stay frozen")
            if groups["vision_tower"]["params"]:
                problems.append(f"the vision tower is trainable ({groups['vision_tower']['params']} params); it must "
                                "stay frozen")
            report["attachment_problems"] = problems
            for p_ in problems:
                print(json.dumps({"PROBLEM": p_}), flush=True)
            report["after_peft"] = summarize_memory(out / "mem.jsonl")

            # Materialise the optimizer state the way the Trainer will: AdamW keeps two fp32 moments per parameter.
            opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=cfg["optim"]["lr"])
            for p in (p for p in model.parameters() if p.requires_grad):
                p.grad = torch.zeros_like(p)
            opt.step()
            opt.zero_grad(set_to_none=True)
            report["after_optimizer"] = summarize_memory(out / "mem.jsonl")
            print(json.dumps({"after_peft": report["after_peft"],
                              "after_optimizer": report["after_optimizer"]}), flush=True)
            if problems:
                report["pass"] = False

        if a.rung == 3:
            report.update(forward_backward(model, cfg, out))
    finally:
        sampler.close()

    mem = summarize_memory(out / "mem.jsonl")
    report["memory"] = mem
    memory_ok = bool(mem.get("min_mem_available_gib") is not None
                     and mem["min_mem_available_gib"] >= PASS_MIN_AVAIL_GIB)
    report["memory_pass"] = memory_ok
    report["pass"] = memory_ok and not report.get("attachment_problems") and not report.get("gradient_problems")
    report["pass_bar_gib"] = PASS_MIN_AVAIL_GIB
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    verdict = {"RUNG": a.rung, "min_mem_available_gib": mem.get("min_mem_available_gib"),
               "torch_max_allocated_gib": mem.get("torch_max_allocated_gib"),
               "load_seconds": report.get("load_seconds"), "memory_pass": memory_ok,
               "bar_gib": PASS_MIN_AVAIL_GIB, "pass": report["pass"]}
    if "trainable" in report:
        verdict["trainable_by_group"] = {k: v["params"] for k, v in report["trainable"].items()}
    for k in ("attachment_problems", "gradient_problems", "first_loss", "grad_norm_by_group"):
        if report.get(k):
            verdict[k] = report[k]
    print(json.dumps(verdict, indent=1), flush=True)
    sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
