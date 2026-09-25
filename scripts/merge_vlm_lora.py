#!/usr/bin/env python3
"""Merge a run F LoRA adapter into the BF16 base checkpoint, shard by shard, and push it to the private HF repo.

Streaming merge: each base safetensors shard is read, the LoRA deltas that belong to its tensors are added (in float32,
stored back in BF16), and the shard is written under the same name. Peak memory is about one shard plus one expert
stack (~10 GB), not the 62 GB model, so it runs next to the live models. The output keeps the base checkpoint's exact
tensor names, shapes and layout (vLLM loads it like the base), plus every non-weight file of the base (config,
tokenizer, chat_template.json, processor configs). The image-size bound used in training is written into
preprocessor_config.json, so every server of this model resizes photos exactly as training did.

  python scripts/merge_vlm_lora.py --adapter runs/herald-f-lora/epoch-1 --out runs/herald-f-merged-e1 --push
  python scripts/merge_vlm_lora.py --adapter runs/herald-f-lora/epoch-2 --out runs/herald-f-merged-e2 \
      --push --repo-suffix -merged-f-e2
Re-run every gate on the merged model served in FP8 before using it (MODEL_PLAN §0l).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lora_common import ROOT, drop_file_cache, hf_snapshot, push_private, repo_id  # noqa: E402

PREFIX = "base_model.model."


def adapter_deltas(adapter_dir: Path) -> tuple[dict, dict]:
    """{base tensor name: (kind, A, B, scale)} from a PEFT adapter; kind is "linear" or "experts"."""
    from safetensors.torch import load_file

    cfg = json.loads((adapter_dir / "adapter_config.json").read_text())
    if cfg.get("rank_pattern") or cfg.get("alpha_pattern"):
        raise SystemExit("rank_pattern / alpha_pattern are not supported by the streaming merge")
    r, alpha = cfg["r"], cfg["lora_alpha"]
    scale = alpha / (r ** 0.5) if cfg.get("use_rslora") else alpha / r
    params = list(cfg.get("target_parameters") or [])
    sd = load_file(str(adapter_dir / "adapter_model.safetensors"))
    out: dict = {}
    for k in sd:
        if not k.endswith("lora_A.weight"):
            continue
        a, b = sd[k], sd[k.replace("lora_A.weight", "lora_B.weight")]
        mod = k[len(PREFIX):] if k.startswith(PREFIX) else k
        mod = mod[: -len(".lora_A.weight")]
        depth = mod.count(".base_layer")
        owner = mod.replace(".base_layer", "")
        leaf = owner.rsplit(".", 1)[-1]
        mine = [p for p in params if p.split(".")[-2] == leaf] if params else []
        if mine and any(owner.endswith(".".join(p.split(".")[:-1])) for p in mine):
            # nested ParamWrappers: the innermost wraps the first listed parameter of this module
            name = f"{owner}.{mine[len(mine) - 1 - depth].split('.')[-1]}"
            out[name] = ("experts", a, b, scale)
        else:
            out[f"{owner}.weight"] = ("linear", a, b, scale)
    return out, cfg


def delta_for(kind: str, a: torch.Tensor, b: torch.Tensor, scale: float, disk_shape: tuple) -> torch.Tensor:
    """The update in the checkpoint's own layout. PEFT's expert LoRA is per expert: A (r*E, in), B (out, r*E), the
    same formula as peft.tuners.lora.layer.ParamWrapper.get_delta_weight, giving (E, out, in); checkpoints may store
    experts as (E, in, out), so the layout is matched by shape and an ambiguous (square) case is refused."""
    a, b = a.float(), b.float()
    if kind == "linear":
        d = (b @ a) * scale
        if tuple(d.shape) != tuple(disk_shape):
            raise ValueError(f"linear delta {tuple(d.shape)} does not fit {disk_shape}")
        return d
    e = disk_shape[0]
    d = torch.einsum("ore,eri->eoi", b.reshape(b.shape[0], -1, e), a.reshape(e, -1, a.shape[-1])) * scale
    fits, fits_t = tuple(d.shape) == tuple(disk_shape), tuple(d.transpose(1, 2).shape) == tuple(disk_shape)
    if fits and fits_t:
        raise ValueError(f"square expert tensor {disk_shape}: layout is ambiguous")
    if fits:
        return d
    if fits_t:
        return d.transpose(1, 2)
    raise ValueError(f"expert delta {tuple(d.shape)} does not fit {disk_shape}")


def merge(base_dir: Path, adapter_dir: Path, out: Path, image_bounds: dict | None = None) -> dict:
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file

    deltas, _ = adapter_deltas(adapter_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = base_dir / "model.safetensors.index.json"
    shards = sorted(set(json.loads(index.read_text())["weight_map"].values())) if index.exists() else ["model.safetensors"]
    used, changed = set(), 0
    for shard in shards:
        src = base_dir / shard
        with safe_open(str(src), "pt") as f:
            meta = f.metadata() or {"format": "pt"}
        tensors = load_file(str(src))
        for name, t in tensors.items():
            if name in deltas:
                kind, a, b, scale = deltas[name]
                tensors[name] = (t.float() + delta_for(kind, a, b, scale, tuple(t.shape))).to(t.dtype)
                used.add(name)
                changed += 1
        save_file(tensors, str(out / shard), metadata=meta)
        del tensors
        drop_file_cache([src, out / shard])
        print(json.dumps({"shard": shard, "merged_so_far": changed}), flush=True)
    missing = sorted(set(deltas) - used)
    if missing:
        raise SystemExit(f"{len(missing)} adapter tensors matched no base tensor, e.g. {missing[:3]}")
    for p in base_dir.iterdir():                      # config, tokenizer, chat template, processor configs, index
        if p.suffix != ".safetensors" and p.is_file() and not p.name.startswith("."):
            shutil.copyfile(p, out / p.name)
    if image_bounds and (out / "preprocessor_config.json").exists():
        pc = json.loads((out / "preprocessor_config.json").read_text())
        pc["size"] = {"longest_edge": image_bounds["max_pixels"], "shortest_edge": image_bounds["min_pixels"]}
        (out / "preprocessor_config.json").write_text(json.dumps(pc, indent=2))
    return {"merged_tensors": changed, "shards": len(shards)}


def verify_layout(base_dir: Path, out: Path) -> None:
    """Every output tensor has the base's name, shape and dtype (what vLLM's loader expects)."""
    from safetensors import safe_open

    def header(d: Path) -> dict:
        h = {}
        for s in sorted(d.glob("*.safetensors")):
            with safe_open(str(s), "pt") as f:
                for k in f.keys():
                    sl = f.get_slice(k)
                    h[k] = (tuple(sl.get_shape()), sl.get_dtype())
        return h

    if header(base_dir) != header(out):
        raise SystemExit("merged checkpoint differs from the base in tensor names, shapes or dtypes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True, help="e.g. runs/herald-f-lora/epoch-1 or .../epoch-2")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default="herald-f")
    ap.add_argument("--push", action="store_true", help="upload to the private repo <HF_REPO_ID><repo-suffix>")
    ap.add_argument("--repo-suffix", default=None, help="default: merged_repo_suffix from config/training.yaml")
    a = ap.parse_args()
    from herald.config import load_yaml

    cfg = load_yaml("training.yaml")[a.config]
    adapter = ROOT / a.adapter if not Path(a.adapter).is_absolute() else Path(a.adapter)
    base_id = json.loads((adapter / "adapter_config.json").read_text())["base_model_name_or_path"]
    base_dir = hf_snapshot(base_id)
    if base_dir is None:
        raise SystemExit(f"{base_id} is not in the local HF cache")
    out = ROOT / a.out if not Path(a.out).is_absolute() else Path(a.out)
    info = merge(base_dir, adapter, out, cfg.get("image"))
    verify_layout(base_dir, out)
    (out / "herald_merge.json").write_text(json.dumps({"adapter": str(adapter), "base": base_id, **info}, indent=1))
    print(json.dumps({"merged": str(adapter), "into": base_id, "out": str(out), **info}))
    if a.push:
        repo = repo_id(a.repo_suffix or cfg["merged_repo_suffix"])
        push_private(out, repo, f"Merge {adapter.parent.name}/{adapter.name} into {base_id}")


if __name__ == "__main__":
    main()
