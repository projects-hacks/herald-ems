"""Pieces shared by the LoRA trainers and merge scripts (scripts/train_lora.py, train_vlm_lora.py, merge_*.py).

Training-only helpers: nothing here runs in the product. Secrets are read from the environment (or the shared
~/.config/herald/secrets.env, mode 600) and never printed.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SECRETS = Path.home() / ".config" / "herald" / "secrets.env"


def system_prompt(profile_prefix: str) -> str:
    """The prompt the served extractor will use for this label (config/extraction.yaml): train and serve alike."""
    from herald.extraction.profiles import default_profiles

    profile = default_profiles().for_label(profile_prefix)
    if profile is None:
        raise SystemExit(f"no fine-tuned profile matches {profile_prefix!r} in config/extraction.yaml")
    return profile.prompt


def reclaim_unified_memory(gib: float) -> None:
    """On the GB10, CPU and GPU share memory and the kernel's page cache counts as used until something allocates.
    Allocating (then freeing) `gib` makes the kernel drop clean cache, so the loader sees the real headroom."""
    import torch

    before, _ = torch.cuda.mem_get_info()
    x = torch.empty(int(gib * 2**30), dtype=torch.uint8, device="cuda")
    x.fill_(0)
    del x
    torch.cuda.empty_cache()
    after, _ = torch.cuda.mem_get_info()
    print(json.dumps({"reclaimed_gib": round((after - before) / 2**30, 1), "free_gib": round(after / 2**30, 1)}))


def mem_available_gib() -> float:
    """MemAvailable from /proc/meminfo (free + reclaimable cache): the number `free -g` shows as "available"."""
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 2**20
    return 0.0


def drop_file_cache(paths: Iterable[Path]) -> float:
    """Advise the kernel to drop the page cache of files we just read (posix_fadvise DONTNEED; no root needed for
    files we own). On the GB10 cached weight files count against the memory ZRT and the trainer see as free
    (AGENTS.md pitfalls). Returns the GiB of file size advised away."""
    total = 0
    for p in paths:
        try:
            fd = os.open(p, os.O_RDONLY)
        except OSError:
            continue
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            total += os.fstat(fd).st_size
        finally:
            os.close(fd)
    return total / 2**30


def load_secrets(path: Path = SECRETS) -> None:
    """Fill HF_TOKEN / HF_REPO_ID from the shared secrets file when the shell didn't export them. Never prints."""
    if os.environ.get("HF_TOKEN") and os.environ.get("HF_REPO_ID"):
        return
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def repo_id(suffix: str) -> str:
    """The private HF repo for a merged model: <HF_REPO_ID><suffix> (e.g. -merged-f)."""
    load_secrets()
    base = os.environ.get("HF_REPO_ID")
    if not base:
        raise SystemExit("HF_REPO_ID is not set (CONTRIBUTING.md: shared secrets)")
    return f"{base}{suffix}"


def push_private(folder: Path, repo: str, message: str) -> None:
    """Upload a folder to a private HF repo (created if missing). The token comes from the environment only."""
    from huggingface_hub import HfApi

    load_secrets()
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is not set (CONTRIBUTING.md: shared secrets)")
    api = HfApi(token=token)
    api.create_repo(repo, private=True, exist_ok=True)
    api.upload_folder(folder_path=str(folder), repo_id=repo, commit_message=message)
    print(f"pushed to {repo} (private)")


def hf_snapshot(model_id: str) -> Optional[Path]:
    """The local snapshot directory of a model already in the HF cache (never downloads), or None."""
    p = Path(model_id)
    if p.is_dir():
        return p
    try:
        from huggingface_hub import snapshot_download

        return Path(snapshot_download(model_id, local_files_only=True))
    except Exception:
        return None


# --------------------------------------------------------------------------------------------------------------
# Streaming weight load (GB10). `from_pretrained` transiently needs about twice the checkpoint here: safetensors
# mmaps every shard, and on unified memory those pages are GPU-addressable, so nvidia-smi counts the whole 57.9 GB
# checkpoint the moment it is mapped while the host side fills as the pages become resident. Two 30B smokes died
# during the load on 2026-09-25 (MemAvailable 114 -> 8 GiB, the memory guard killed the critical job at 50% of the
# load). posix_fadvise cannot help: it will not evict pages held by a live mapping.
#
# This loader never holds more than one shard. The skeleton is built on the meta device, then each shard is opened
# straight onto the GPU and assigned into the model (assign=True replaces the meta parameter with the tensor, so
# there is no second copy), and the shard's page cache is dropped before the next one is opened.
# --------------------------------------------------------------------------------------------------------------

EXPERT_HINT = "the checkpoint stores fused MoE experts transposed (conversion_mapping.py, qwen3_vl_moe)"


def _shard_files(snap: Path) -> list[Path]:
    """The checkpoint's shards, in index order (a single-file checkpoint is one shard)."""
    index = snap / "model.safetensors.index.json"
    if index.exists():
        weight_map = json.loads(index.read_text())["weight_map"]
        return [snap / name for name in sorted(set(weight_map.values()))]
    single = snap / "model.safetensors"
    if single.exists():
        return [single]
    shards = sorted(snap.glob("model-*.safetensors"))
    if not shards:
        raise SystemExit(f"no safetensors checkpoint in {snap}")
    return shards


def _fit_to_target(name: str, tensor, target):
    """The on-disk tensor as the model's parameter expects it.

    Qwen3-VL-MoE stores each layer's fused experts transposed on disk: `experts.gate_up_proj` is
    (128, 2048, 1536) in the file and (128, 1536, 2048) in the model, and `experts.down_proj` is (128, 768, 2048)
    against (128, 2048, 768). transformers does this swap while loading; a streaming loader has to do it too, or it
    installs silently wrong weights. The swap is decided by comparing shapes, not by matching parameter names, so an
    unexpected layout raises instead of being guessed at.
    """
    if target is None or tuple(tensor.shape) == tuple(target.shape):
        return tensor
    if tensor.dim() >= 2 and tuple(tensor.transpose(-2, -1).shape) == tuple(target.shape):
        return tensor.transpose(-2, -1).contiguous()
    raise RuntimeError(f"{name}: checkpoint shape {tuple(tensor.shape)} does not fit the model's "
                       f"{tuple(target.shape)} ({EXPERT_HINT})")


def stream_load_model(base: str, device: str = "cuda:0", dtype=None, attn_implementation: str = "sdpa",
                      drop_cache: bool = True, progress: bool = True):
    """Load a checkpoint shard by shard straight onto `device`, holding one shard at a time.

    Equivalent to `from_pretrained(base, dtype=dtype, device_map={"": device})` but with a flat memory profile.
    `device="cpu"` is supported so the equality test can run without a GPU.
    """
    import torch
    from accelerate import init_empty_weights
    from safetensors import safe_open
    from transformers import AutoConfig, AutoModelForImageTextToText

    snap = hf_snapshot(base)
    if snap is None:
        raise SystemExit(f"{base} is not in the local HF cache; fetch it with `hf download {base}`")
    config = AutoConfig.from_pretrained(base)
    # include_buffers=False keeps non-persistent buffers (rotary inv_freq and friends) real and tiny on the CPU;
    # only parameters go to meta. With them on meta they would never be filled by the checkpoint and would stay meta.
    with init_empty_weights(include_buffers=False):
        model = AutoModelForImageTextToText.from_config(config, dtype=dtype,
                                                        attn_implementation=attn_implementation)
    model.tie_weights()          # make tied parameters share storage before anything is assigned

    targets = dict(model.named_parameters())
    targets.update(model.named_buffers())
    shards = _shard_files(snap)
    seen: set[str] = set()
    t0 = time.time()
    for i, path in enumerate(shards, 1):
        part = {}
        with safe_open(path, framework="pt", device=device) as f:
            for name in f.keys():
                t = f.get_tensor(name)
                if dtype is not None and t.is_floating_point() and t.dtype != dtype:
                    t = t.to(dtype)
                part[name] = _fit_to_target(name, t, targets.get(name))
        model.load_state_dict(part, strict=False, assign=True)
        seen |= set(part)
        del part
        if device.startswith("cuda"):
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
        if drop_cache:
            drop_file_cache([path])
        if progress:
            print(json.dumps({"shard": f"{i}/{len(shards)}", "file": path.name,
                              "mem_available_gib": round(mem_available_gib(), 1),
                              "torch_allocated_gib": round(torch.cuda.memory_allocated() / 2**30, 1)
                              if device.startswith("cuda") else None}), flush=True)

    model.tie_weights()          # re-tie: assign=True replaced the tensors the first tie pointed at
    missing = [n for n in targets if n not in seen]
    still_meta = [n for n, t in list(model.named_parameters()) + list(model.named_buffers())
                  if t.device.type == "meta"]
    if still_meta:
        raise RuntimeError(f"{len(still_meta)} tensors were never filled by the checkpoint, first few: "
                           f"{still_meta[:5]} (missing from the file: {[m for m in missing][:5]})")
    if device.startswith("cuda"):          # buffers were built on the CPU by init_empty_weights(include_buffers=False)
        model.to(device)
    print(json.dumps({"streamed_load_s": round(time.time() - t0, 1), "shards": len(shards),
                      "tensors": len(seen), "unfilled": len(still_meta)}), flush=True)
    return model


def load_model(base: str, stream: bool = True, device: str = "cuda:0", dtype=None,
               attn_implementation: str = "sdpa"):
    """The streaming loader by default; `stream=False` is the original `from_pretrained` path, kept as a fallback."""
    import torch
    from transformers import AutoModelForImageTextToText

    if dtype is None:
        dtype = torch.bfloat16
    if stream:
        return stream_load_model(base, device=device, dtype=dtype, attn_implementation=attn_implementation)
    return AutoModelForImageTextToText.from_pretrained(base, dtype=dtype, attn_implementation=attn_implementation,
                                                      device_map={"": 0 if device.startswith("cuda") else device})


class MemorySampler:
    """Background record of memory while a job runs, so a freeze leaves evidence on disk.

    Three of the GB10's lockups on 2026-09-24/25 left nothing behind: no OOM record, no Xid, and no memory-guard
    warning, because the box stopped before anything could be written. This samples MemAvailable and torch's own
    allocated/reserved figures at `hz` and flushes to `<out>/mem.jsonl` once a second, so the last line before a
    freeze is at most a second old. Start it as a daemon thread; `close()` writes a final line.
    """

    def __init__(self, path: Path, hz: float = 10.0, flush_every_s: float = 1.0):
        self.path = Path(path)
        self.interval = 1.0 / hz
        self.flush_every_s = flush_every_s
        self._stop = None
        self._thread = None

    def _sample(self, torch) -> dict:
        row = {"t": round(time.time(), 2), "mem_available_gib": round(mem_available_gib(), 2)}
        if torch is not None and torch.cuda.is_available():
            row["torch_allocated_gib"] = round(torch.cuda.memory_allocated() / 2**30, 2)
            row["torch_reserved_gib"] = round(torch.cuda.memory_reserved() / 2**30, 2)
            row["torch_max_allocated_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
        return row

    def start(self) -> "MemorySampler":
        import threading

        try:
            import torch
        except Exception:
            torch = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stop = threading.Event()

        def loop() -> None:
            last_flush = 0.0
            with open(self.path, "a") as fh:
                while True:
                    fh.write(json.dumps(self._sample(torch)) + "\n")
                    now = time.time()
                    if now - last_flush >= self.flush_every_s:
                        fh.flush()
                        os.fsync(fh.fileno())      # a freeze must not lose the last second
                        last_flush = now
                    if self._stop.wait(self.interval):
                        fh.write(json.dumps({**self._sample(torch), "final": True}) + "\n")
                        fh.flush()
                        os.fsync(fh.fileno())
                        return

        self._thread = threading.Thread(target=loop, name="mem-sampler", daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> "MemorySampler":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


def summarize_memory(path: Path) -> dict:
    """The numbers the ladder rungs report: the low-water mark of MemAvailable and torch's peak."""
    rows = []
    for line in open(path):
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue                      # a torn last line after a hard stop
    if not rows:
        return {}
    avail = [r["mem_available_gib"] for r in rows if "mem_available_gib" in r]
    alloc = [r.get("torch_max_allocated_gib", 0) for r in rows]
    return {"samples": len(rows), "seconds": round(rows[-1]["t"] - rows[0]["t"], 1),
            "min_mem_available_gib": min(avail) if avail else None,
            "max_mem_available_gib": max(avail) if avail else None,
            "torch_max_allocated_gib": max(alloc) if alloc else None}
