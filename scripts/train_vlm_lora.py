#!/usr/bin/env python3
"""Run F: LoRA fine-tune of Qwen3-VL-30B-A3B-Instruct as ONE model for speech -> facts, photo -> facts, and (replay
slice) the base model's own protocol reranking, figure transcription and translation. BF16, gradient checkpointing,
vision tower frozen, loss on answer tokens only. Settings: config/training.yaml `herald-f`; design: MODEL_PLAN §0l.

  # CPU only: load the data, render prompts, count tokens, plan the mix and the steps (no model load)
  python scripts/train_vlm_lora.py --dry-run
  # smoke on the real 30B: 20 optimizer steps, reports memory, tokens/s and the projected full-run time
  python scripts/train_vlm_lora.py --reclaim-gib 60 --max-steps 20 --out runs/herald-f-smoke
  # real run (resumable: rerun the same command with --resume)
  python scripts/train_vlm_lora.py --reclaim-gib 60

Keeps the adapter at the end of every epoch in <out>/epoch-<k> (never rotated away) plus periodic checkpoints.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lora_common import (ROOT, MemorySampler, drop_file_cache, hf_snapshot, load_model,  # noqa: E402
                         mem_available_gib, summarize_memory,
                         reclaim_unified_memory)
import ckpt_safety  # noqa: E402
from vlm_data import Encoder, collate, load_rows, mix_epochs, plan_batches, prompt_drift, steps_for  # noqa: E402


EXIT_PLAN_CHANGED = 3        # permanent: the supervisor does not retry it


def load_cfg(key: str = "herald-f") -> dict:
    from herald.config import load_yaml

    return load_yaml("training.yaml")[key]


def expected_prompts(cfg: dict) -> tuple[dict, dict]:
    """What the app sends today: the extraction profile for the served label, and the photo prompts per mode."""
    from herald.config import load_yaml
    from herald.extraction.profiles import default_profiles

    vision = load_yaml("prompts/vision.yaml")
    profile = default_profiles().for_label(cfg["label"])
    exp = {"system:image": {vision["system"]}, **{f"user:{m}": {t} for m, t in vision["modes"].items()}}
    if profile is not None:
        exp["system:text"] = {profile.prompt}
    return exp, vision


def load_data(cfg: dict, split: str, limit: int | None = None) -> dict[str, list]:
    _, vision = expected_prompts(cfg)
    from herald.extraction.profiles import default_profiles

    profile = default_profiles().for_label(cfg["label"])
    d = cfg["data"]
    return {"text": load_rows(ROOT / d["text"] / f"{split}.jsonl", "text", profile.prompt if profile else None,
                              limit=limit),
            "image": load_rows(ROOT / d["image"] / f"{split}.jsonl", "image", vision_prompts=vision, limit=limit),
            "replay": load_rows(ROOT / d["replay"] / f"{split}.jsonl", "replay", limit=limit)}


class Plan:
    """The whole run laid out up front: rows, their token counts, micro-batches, and where each epoch ends."""

    def __init__(self, cfg: dict, enc: Encoder, train: dict[str, list], max_steps: int | None = None):
        b = cfg["batching"]
        self.accum = int(b["accum"])
        rng = random.Random(cfg["mix"].get("seed", 13))
        self.rows, self.batches, per_epoch, self.dropped = [], [], [], 0
        for epoch_rows in mix_epochs(train["text"], train["image"], train["replay"], cfg["mix"]):
            lengths = [enc.length(ex) for ex in epoch_rows]
            keep = [i for i, n in enumerate(lengths) if n <= cfg["max_length"]]
            self.dropped += len(epoch_rows) - len(keep)
            offset = len(self.rows)
            self.rows += [epoch_rows[i] for i in keep]
            self.lengths = getattr(self, "lengths", []) + [lengths[i] for i in keep]
            bs = plan_batches([lengths[i] for i in keep], int(b["max_tokens"]), int(b["max_rows"]), self.accum, rng)
            self.batches += [[offset + i for i in batch] for batch in bs]
            per_epoch.append(len(bs))
        self.epoch_end_steps = steps_for(per_epoch, self.accum)
        self.total_steps = self.epoch_end_steps[-1] if self.epoch_end_steps else 0
        self.steps = min(max_steps, self.total_steps) if max_steps else self.total_steps

    def tokens(self, steps: int | None = None) -> int:
        """Padded tokens the first `steps` optimizer steps process (what the GPU actually computes)."""
        n = (steps or self.total_steps) * self.accum
        return sum(len(bt) * max(self.lengths[i] for i in bt) for bt in self.batches[:n])

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for ex in self.rows:
            kinds[ex.kind] = kinds.get(ex.kind, 0) + 1
        return {"rows": len(self.rows), "by_kind": kinds, "dropped_over_max_length": self.dropped,
                "micro_batches": len(self.batches), "optimizer_steps": self.total_steps,
                "epoch_end_steps": self.epoch_end_steps, "padded_tokens": self.tokens(),
                "real_tokens": sum(self.lengths)}


class RowDataset:
    def __init__(self, rows, enc: Encoder):
        self.rows, self.enc = rows, enc

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return {**self.enc.encode(self.rows[i]), "_row": i}


def row_key(ex) -> tuple:
    """A row's identity for the plan fingerprint and the batch log."""
    h = lambda t: ckpt_safety.hashlib.sha256(t.encode()).hexdigest()[:10]
    return ex.kind, ex.id, h(ex.system + ex.user), h(ex.assistant), str(ex.image or "")


def collate_rows(features: list[dict], pad_id: int) -> dict:
    import torch

    rows = [f.pop("_row") for f in features]
    return {**collate(features, pad_id), "_row_ids": torch.tensor(rows)}


def make_trainer_class():
    import torch
    from torch.utils.data import DataLoader
    from transformers import Trainer

    class HeraldTrainer(Trainer):
        """Token-budget micro-batches in a fixed order (epoch boundaries on optimizer steps), and the loss computed
        only where there are labels: lm_head runs on answer positions, not on every image and prompt token."""
        plan_batches: list = []
        out_dir: Path = Path(".")
        kill_in_save_at: int | None = None      # test hook: SIGKILL in the middle of this step's save

        def _save_checkpoint(self, model, trial):
            """The Trainer's save, measured, then flushed and marked complete (ckpt_safety)."""
            with ckpt_safety.MemSampler() as mem:
                super()._save_checkpoint(model, trial)
            ckpt = Path(self._get_output_dir(trial=trial)) / f"checkpoint-{self.state.global_step}"
            t0 = time.time()
            ckpt_safety.mark_complete(ckpt, {"step": self.state.global_step, **mem.report()})
            print(json.dumps({"checkpoint": ckpt.name, "flush_s": round(time.time() - t0, 1), **mem.report()}), flush=True)

        def _save_optimizer_and_scheduler(self, output_dir):
            if self.kill_in_save_at == self.state.global_step:
                import os
                import signal

                print(json.dumps({"test_kill_in_save": self.state.global_step}), flush=True)
                os.kill(os.getpid(), signal.SIGKILL)
            return super()._save_optimizer_and_scheduler(output_dir)

        def get_train_dataloader(self):
            dl = DataLoader(self.train_dataset, batch_sampler=self.plan_batches, collate_fn=self.data_collator,
                            num_workers=self.args.dataloader_num_workers, pin_memory=False)
            return self.accelerator.prepare(dl)

        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            rows = inputs.pop("_row_ids", None)
            if model.training and rows is not None:          # exactly what is trained, in order (resume proof)
                with open(self.out_dir / "batches.jsonl", "a") as f:
                    f.write(json.dumps({"step": self.state.global_step, "rows": rows.tolist(),
                                        "lr": self.lr_scheduler.get_last_lr()[0] if self.lr_scheduler else None}) + "\n")
            labels = inputs.pop("labels")
            targets = labels[:, 1:]
            keep = targets.ne(-100).any(0).nonzero().squeeze(-1)          # positions whose next token is an answer
            out = model(**inputs, use_cache=False, logits_to_keep=keep)
            logits = out.logits.float()
            tgt = targets[:, keep]
            loss = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), tgt.reshape(-1),
                                                     ignore_index=-100, reduction="sum")
            denom = num_items_in_batch if num_items_in_batch is not None else tgt.ne(-100).sum()
            loss = loss / denom.to(loss.device) if torch.is_tensor(denom) else loss / denom
            return (loss, out) if return_outputs else loss

    return HeraldTrainer


def make_callbacks(out: Path, epoch_end_steps: list[int], backup: Path, dev_passes: int = 1):
    from transformers import TrainerCallback

    class JsonlLog(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kw):
            with open(out / "log.jsonl", "a") as f:
                f.write(json.dumps({"step": state.global_step, "t": round(time.time(), 1), **(logs or {})}) + "\n")

    class CadenceFromArgs(TrainerCallback):
        """Re-apply the configured save/eval cadence after a resume, so `config/training.yaml` stays the source of truth.

        transformers' `DefaultFlowCallback` decides when to save and evaluate from `state.save_steps` and
        `state.eval_steps`, not from `args`. `Trainer._init_training_state` calls `state.compute_steps(args, ...)` and
        then, when resuming, **replaces the whole TrainerState** with the one stored in the checkpoint -- which carries
        the cadence the run started with. So a changed `checkpoint_steps` / `eval_steps` is written into the new
        `training_args.bin` and silently ignored by the control flow.

        Hit for real on 2026-09-25: run F's cadence was raised to 20 / 122 mid-run, the resumed process reported
        `save_steps: 20` in its args, and still saved at step 90 and evaluated every 50. `on_train_begin` runs after
        the restore, so re-applying args here is what actually makes the change take effect.
        """

        def on_train_begin(self, args, state, control, **kw):
            state.compute_steps(args, state.max_steps)          # transformers' own logic (handles ratios < 1)
            print(json.dumps({"cadence": {"save_steps": state.save_steps, "eval_steps": state.eval_steps,
                                          "logging_steps": state.logging_steps, "max_steps": state.max_steps}}),
                  flush=True)

    class EpochAdapters(TrainerCallback):
        """Save the adapter at the end of each epoch into <out>/epoch-<k> (both are evaluated, one is picked), written
        to a temp dir and renamed, then copied the same way to the backup dir so a bad cleanup can't lose it.

        The dev losses in `herald_epoch.json` must be the ones measured on the adapter's OWN step, which takes two
        hooks. transformers evaluates *after* `on_step_end`: the training loop calls `on_step_end`
        (trainer.py:1882) and then `_maybe_log_save_evaluate` (:1883), which runs the dev passes (:2196) and only
        afterwards saves and fires `on_save` (:2202-2204); each `Trainer.evaluate` logs its metrics into
        `state.log_history`, stamped with the step it ran on (:2776 -> `log` :4049-4050), and fires `on_evaluate`
        (:2781). Writing the whole file from `on_step_end` therefore
        recorded the PREVIOUS dev pass: on the real run `runs/herald-f-lora/epoch-1/herald_epoch.json` says
        `"step": 244` but carries eval rows tagged `"step": 122`, and epoch-2 says 488 with rows from 366.
        TRAINING_PLAN §4.3 picks the better epoch out of this file, so the comparison was made on stale numbers.

        So the weights are snapshotted in `on_step_end` (they are this step's weights; evaluation does not change
        them) and the directory is finished off once this step's dev passes have landed. `eval_dataset` is a dict, so
        `Trainer.evaluate` recurses once per dev set (trainer.py:2734-2743) and `on_evaluate` fires once per set:
        `dev_passes` is how many to wait for. A snapshot still pending when training moves on or ends is finished
        anyway, so a missing or renamed dev set can never cost us the adapter.
        """

        def __init__(self):
            self.pending: tuple[int, int, Path] | None = None       # (epoch, step, temp dir) not finished yet
            self.seen = 0                                           # dev passes landed for the pending step

        def _snapshot(self, state, model) -> None:
            k = epoch_end_steps.index(state.global_step) + 1
            tmp = out / f".epoch-{k}.writing"
            if tmp.exists():
                shutil.rmtree(tmp)
            model.save_pretrained(tmp)
            self.pending, self.seen = (k, state.global_step, tmp), 0

        def _finish(self, state) -> None:
            k, step, tmp = self.pending
            self.pending, self.seen = None, 0
            (tmp / "herald_epoch.json").write_text(json.dumps(
                {"epoch": k, "step": step,
                 "eval": [h for h in state.log_history
                          if h.get("step") == step and any(x.startswith("eval_") for x in h)]}, indent=1))
            ckpt_safety.mark_complete(tmp, {"epoch": k, "step": step})
            if (out / f"epoch-{k}").exists():
                shutil.rmtree(out / f"epoch-{k}")
            tmp.rename(out / f"epoch-{k}")
            ckpt_safety.copy_dir_atomic(out / f"epoch-{k}", backup / f"epoch-{k}")
            print(json.dumps({"saved_epoch_adapter": str(out / f'epoch-{k}'), "backup": str(backup / f'epoch-{k}'),
                              "step": step}), flush=True)

        def on_step_end(self, args, state, control, model=None, **kw):
            if self.pending and self.pending[1] != state.global_step:
                self._finish(state)                     # its dev pass never came: keep the adapter regardless
            if state.global_step in epoch_end_steps:
                self._snapshot(state, model)

        def on_evaluate(self, args, state, control, **kw):
            if self.pending and self.pending[1] == state.global_step:
                self.seen += 1
                if self.seen >= dev_passes:
                    self._finish(state)

        def on_train_end(self, args, state, control, **kw):
            if self.pending:
                self._finish(state)

    return [CadenceFromArgs(), JsonlLog(), EpochAdapters()]


def lora_config(cfg: dict, model):
    from peft import LoraConfig

    lc = cfg["lora"]
    names = [n for n, _ in model.named_parameters()]
    wanted = list(lc.get("target_parameters") or [])
    found = [t for t in wanted if any(n.endswith(t) for n in names)]
    if wanted and not found and any(".experts." in n for n in names):
        raise SystemExit(f"target_parameters {wanted} match nothing in this MoE model")
    if set(wanted) - set(found):
        print(json.dumps({"note": "target_parameters absent in this model (dense?)", "skipped": sorted(set(wanted) - set(found))}))
    return LoraConfig(r=lc["r"], lora_alpha=lc["alpha"], lora_dropout=lc["dropout"], target_modules=lc["target_modules"],
                      target_parameters=found or None, task_type="CAUSAL_LM")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="herald-f", help="block in config/training.yaml")
    ap.add_argument("--base", default=None, help="override the base model (e.g. Qwen/Qwen3-VL-2B-Instruct for a pipeline smoke)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-steps", type=int, default=None, help="stop after this many optimizer steps (smoke)")
    ap.add_argument("--limit-rows", type=int, default=None, help="read at most this many rows per source file")
    ap.add_argument("--save-steps", type=int, default=None, help="override checkpoint_steps")
    ap.add_argument("--eval-steps", type=int, default=None, help="override eval_steps")
    ap.add_argument("--max-tokens", type=int, default=None, help="override batching.max_tokens")
    for k in ("text", "image", "replay"):
        ap.add_argument(f"--{k}-dir", default=None, help=f"override data.{k} (a dir with train.jsonl / dev.jsonl)")
    ap.add_argument("--dry-run", action="store_true", help="data, prompts, token counts and the step plan only (CPU)")
    ap.add_argument("--resume", action="store_true",
                    help="continue from the newest COMPLETE checkpoint in --out (incomplete ones are renamed aside); "
                         "exits 0 at once if the run already finished")
    ap.add_argument("--backup-dir", default=None, help="second copy of the epoch adapters (default: config)")
    ap.add_argument("--test-kill-in-save", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--reclaim-gib", type=float, default=0.0,
                    help="GB10 unified memory: touch this much GPU memory first so the page cache is reclaimed")
    ap.add_argument("--gpu-cap-gib", type=float, default=None,
                    help="hard cap on this process's GPU memory: it fails with a CUDA OOM instead of squeezing live models")
    ap.add_argument("--min-free-gib", type=float, default=None, help="override min_free_gib (0 = no check)")
    ap.add_argument("--no-stream-load", action="store_true",
                    help="load with from_pretrained instead of the shard-by-shard streaming loader (the fallback "
                         "path: from_pretrained transiently needs ~2x the checkpoint on the GB10)")
    ap.add_argument("--allow-prompt-drift", action="store_true",
                    help="train even if rows' prompts differ from what the app sends today (not for real runs)")
    a = ap.parse_args()

    cfg = load_cfg(a.config)
    base = a.base or cfg["base"]
    out = ROOT / (a.out or cfg["out"])
    if a.max_tokens:
        cfg["batching"]["max_tokens"] = a.max_tokens
    cfg["checkpoint_steps"] = a.save_steps or cfg["checkpoint_steps"]
    cfg["eval_steps"] = a.eval_steps or cfg["eval_steps"]
    for k in ("text", "image", "replay"):
        if getattr(a, f"{k}_dir"):
            cfg["data"][k] = getattr(a, f"{k}_dir")
    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(base)
    enc = Encoder(processor, cfg["image"]["max_pixels"], cfg["image"]["min_pixels"])

    train, dev = load_data(cfg, "train", a.limit_rows), load_data(cfg, "dev", a.limit_rows)
    expected, _ = expected_prompts(cfg)
    drift = prompt_drift([ex for rows in train.values() for ex in rows], expected)
    if "system:text" not in expected:
        print(json.dumps({"warning": f"config/extraction.yaml has no profile for {cfg['label']!r}: the app would "
                                     "call herald-f as a general model; add the profile before serving"}))
    if drift and not a.allow_prompt_drift:
        raise SystemExit(f"rows whose prompt differs from what the app sends today: {drift} (MODEL_PLAN §0l)")
    plan = Plan(cfg, enc, train, a.max_steps)
    dev_sets = {k: rows[: cfg["dev_rows"].get(k, len(rows))] for k, rows in dev.items() if rows}
    info = {"base": base, "out": str(out), "prompt_drift": drift, "plan": plan.summary(),
            "dev_rows": {k: len(v) for k, v in dev_sets.items()},
            "train_rows_available": {k: len(v) for k, v in train.items()},
            "projected_hours_at_reference_speed": round(plan.tokens() / cfg["reference_tokens_per_s"] / 3600, 2)}
    print(json.dumps(info, indent=1))
    if a.dry_run:
        ex = next((r for r in plan.rows if r.image is not None), plan.rows[0] if plan.rows else None)
        if ex is not None:
            print("--- first photo/figure row as the model sees it ---\n" + enc.prompt_text(ex) + ex.assistant + "<|im_end|>")
        return
    if not plan.rows:
        raise SystemExit("no training rows")
    if a.resume and (out / "DONE").exists():
        print(json.dumps({"done": str(out / "DONE"), "note": "run already finished; nothing to resume"}))
        return
    fingerprint = ckpt_safety.plan_fingerprint(
        [row_key(ex) for ex in plan.rows], plan.batches[: plan.steps * plan.accum],
        {"base": base, "steps": plan.steps, "accum": plan.accum, "lora": cfg["lora"], "optim": cfg["optim"]})
    fp_file = out / "plan_fingerprint.json"
    if a.resume and fp_file.exists() and json.loads(fp_file.read_text())["fingerprint"] != fingerprint:
        print(json.dumps({"error": "plan changed since the run started (data, config or --max-steps); resuming would "
                                   "skip the wrong rows", "was": json.loads(fp_file.read_text())["fingerprint"],
                          "now": fingerprint}))
        sys.exit(EXIT_PLAN_CHANGED)

    import torch
    from peft import get_peft_model
    from transformers import AutoModelForImageTextToText, TrainingArguments

    if a.reclaim_gib:
        reclaim_unified_memory(a.reclaim_gib)
    if a.gpu_cap_gib:
        torch.cuda.set_per_process_memory_fraction(a.gpu_cap_gib * 2**30 / torch.cuda.get_device_properties(0).total_memory)
    free = torch.cuda.mem_get_info()[0] / 2**30
    need = cfg["min_free_gib"] if a.min_free_gib is None else a.min_free_gib
    print(json.dumps({"gpu_free_gib": round(free, 1), "mem_available_gib": round(mem_available_gib(), 1), "need_gib": need}))
    if free < need:
        raise SystemExit(f"only {free:.1f} GiB free, need {need} (unload models or pass --reclaim-gib); not loading")
    out.mkdir(parents=True, exist_ok=True)
    resume_from = ckpt_safety.prepare_resume(out) if a.resume else None
    if resume_from is None:
        if not a.resume and (any(out.glob("checkpoint-*")) or (out / "batches.jsonl").exists()):
            raise SystemExit(f"{out} holds an earlier run; pass --resume or use a new --out")
        (out / "run_config.json").write_text(json.dumps({"config": cfg, **info}, indent=1, default=str))
        fp_file.write_text(json.dumps({"fingerprint": fingerprint}))
    with open(out / "batches.jsonl", "a") as f:        # segment marker: ckpt_safety.effective_batches reads it
        f.write(json.dumps({"segment_start": int(resume_from.name.split("-")[1]) if resume_from else 0,
                            "t": round(time.time(), 1)}) + "\n")
    print(json.dumps({"resume_from": str(resume_from) if resume_from else None, "plan_fingerprint": fingerprint}),
          flush=True)

    from transformers import set_seed

    set_seed(cfg["mix"]["seed"])            # LoRA init is reproducible (runs compare; resume loads it from the checkpoint)
    # From here on, memory is recorded to <out>/mem.jsonl at 10 Hz and flushed every second: the load and the first
    # steps are where the 30B died, and three lockups on this box left no evidence at all behind.
    # The sampler is held as a context manager so its thread is stopped and its `"final": true` line written on the
    # way out of every exit: a normal finish, a SystemExit from one of the guards above, or a torch OOM mid-run. It
    # used to be started and never closed -- the sampler thread and the missing final marker only went away with the
    # process, so a run that ended on an exception left a mem.jsonl that looked truncated, exactly like the freezes
    # this file exists to document. Wiring it was deferred while run F was training, because the supervisor relaunches
    # this script and would have re-read a half-edited file (AGENTS.md pitfalls); the run has since finished.
    with MemorySampler(out / "mem.jsonl"):
        model = load_model(base, stream=not a.no_stream_load)
        print(json.dumps({"after_load": summarize_memory(out / "mem.jsonl")}), flush=True)
        snap = hf_snapshot(base)
        if snap:
            print(json.dumps({"dropped_weight_file_cache_gib": round(drop_file_cache(snap.glob("*.safetensors")), 1)}))
        model.config.use_cache = False
        model = get_peft_model(model, lora_config(cfg, model))
        model.print_trainable_parameters()

        o = cfg["optim"]
        args = TrainingArguments(
            output_dir=str(out), max_steps=plan.steps, per_device_train_batch_size=1, per_device_eval_batch_size=4,
            gradient_accumulation_steps=plan.accum, learning_rate=o["lr"], lr_scheduler_type=o["scheduler"],
            warmup_steps=o["warmup_ratio"], weight_decay=o["weight_decay"], max_grad_norm=o["max_grad_norm"],
            bf16=True, logging_steps=1, eval_strategy="steps", eval_steps=cfg["eval_steps"], save_strategy="steps",
            save_steps=cfg["checkpoint_steps"], save_total_limit=cfg["keep_checkpoints"], report_to=[],
            remove_unused_columns=False, prediction_loss_only=True, gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False}, dataloader_num_workers=2, seed=cfg["mix"]["seed"])
        HeraldTrainer = make_trainer_class()
        HeraldTrainer.plan_batches = plan.batches[: plan.steps * plan.accum]
        HeraldTrainer.out_dir, HeraldTrainer.kill_in_save_at = out, a.test_kill_in_save
        backup = ROOT / (a.backup_dir or cfg["adapter_backup_dir"])
        trainer = HeraldTrainer(model=model, args=args, train_dataset=RowDataset(plan.rows, enc),
                                eval_dataset={k: RowDataset(v, enc) for k, v in dev_sets.items()},
                                data_collator=lambda f: collate_rows(f, enc.pad_id),
                                callbacks=make_callbacks(out, [s for s in plan.epoch_end_steps if s <= plan.steps],
                                                         backup, dev_passes=max(1, len(dev_sets))))
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        start = int(resume_from.name.split("-")[1]) if resume_from else 0
        trainer.train(resume_from_checkpoint=str(resume_from) if resume_from else None)
        dt = time.time() - t0
        trainer.save_model(str(out / "final"))
        hist = trainer.state.log_history
        losses = [h["loss"] for h in hist if "loss" in h]
        toks = plan.tokens(plan.steps) - (plan.tokens(start) if start else 0)      # this invocation only
        tps = toks / dt if dt else 0.0
        report = {"steps": trainer.state.global_step, "seconds": round(dt, 1), "loss_first": losses[:3],
                  "loss_last": losses[-3:], "nan": any(x != x for x in losses),
                  "eval": [{k: v for k, v in h.items() if k.startswith("eval_") and k.endswith("loss")}
                           | {"step": h["step"]}
                           for h in hist if any(k.endswith("_loss") and k.startswith("eval_") for k in h)],
                  "peak_gpu_mem_gib": round(torch.cuda.max_memory_allocated() / 2**30, 1),
                  "padded_tokens": toks, "tokens_per_s": round(tps, 1),
                  "projected_full_run_hours": round(plan.tokens() / tps / 3600, 2) if tps else None,
                  "epoch_adapters": sorted(str(p) for p in out.glob("epoch-*"))}
        (out / "report.json").write_text(json.dumps(report, indent=1))
        (out / "DONE").write_text(json.dumps({"step": trainer.state.global_step, "t": round(time.time(), 1)}))
        print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
