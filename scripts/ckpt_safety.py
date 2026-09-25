"""Crash safety for run F (MODEL_PLAN §0l "Crash safety"): complete-checkpoint markers, resume selection, the plan
fingerprint, and atomic directory copies. Training-only; no model code here, so it is unit-tested on its own.

transformers 5.17 writes a checkpoint straight into `checkpoint-N` (no temp dir + rename) and `get_last_checkpoint`
picks the highest N whether or not it is complete. So after the Trainer finishes a save we flush it to disk and
write `herald_complete.json` (every file with its size) last; on resume only checkpoints whose marker matches the
files on disk count, and any other `checkpoint-N` is renamed aside (never deleted) before the Trainer looks.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Iterable, Optional

MARKER = "herald_complete.json"
_CKPT = re.compile(r"^checkpoint-(\d+)$")


def _fsync_file(p: Path) -> None:
    fd = os.open(p, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(p: Path) -> None:
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _files(d: Path) -> dict[str, int]:
    return {str(p.relative_to(d)): p.stat().st_size for p in sorted(d.rglob("*")) if p.is_file() and p.name != MARKER}


def mark_complete(ckpt: Path, extra: Optional[dict] = None) -> None:
    """Flush every file of a finished checkpoint to disk, then write the marker atomically (tmp + fsync + rename)."""
    files = _files(ckpt)
    for rel in files:
        _fsync_file(ckpt / rel)
    tmp = ckpt / (MARKER + ".tmp")
    tmp.write_text(json.dumps({"files": files, "t": round(time.time(), 1), **(extra or {})}, indent=1))
    _fsync_file(tmp)
    os.replace(tmp, ckpt / MARKER)
    _fsync_dir(ckpt)


def is_complete(ckpt: Path) -> bool:
    m = ckpt / MARKER
    if not m.is_file():
        return False
    try:
        files = json.loads(m.read_text())["files"]
    except (ValueError, KeyError):
        return False
    return bool(files) and all((ckpt / rel).is_file() and (ckpt / rel).stat().st_size == size
                               for rel, size in files.items())


def checkpoints(out: Path) -> list[tuple[int, Path]]:
    return sorted((int(m.group(1)), p) for p in out.glob("checkpoint-*") if p.is_dir() and (m := _CKPT.match(p.name)))


def prepare_resume(out: Path) -> Optional[Path]:
    """The newest complete checkpoint, after renaming every incomplete `checkpoint-N` to `incomplete-checkpoint-N-<t>`
    (kept for inspection; the Trainer's rotation and resume never see it)."""
    best = None
    for step, p in checkpoints(out):
        if is_complete(p):
            best = p
        else:
            p.rename(out / f"incomplete-{p.name}-{int(time.time())}")
    return best


def plan_fingerprint(rows: Iterable[tuple], batches: list[list[int]], settings: dict) -> str:
    """What a resume must match: every micro-batch's rows in order (kind, id, prompt and answer hashes) and the
    settings that shape the run. Resuming a different plan would skip the wrong rows silently."""
    rows = list(rows)
    h = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode())
    for b in batches:
        for i in b:
            h.update(json.dumps(rows[i], default=str).encode())
        h.update(b"|")
    return h.hexdigest()[:24]


def effective_batches(lines: Iterable[str]) -> list[dict]:
    """The micro-batches that count, from a batches.jsonl written across crashes: each attempt starts with a
    {"segment_start": step} line, and everything an earlier attempt logged at or after that step was redone."""
    out: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        r = json.loads(line)
        if "segment_start" in r:
            out = [b for b in out if b["step"] < r["segment_start"]]
        else:
            out.append(r)
    return out


def copy_dir_atomic(src: Path, dst: Path) -> None:
    """Copy a directory so `dst` is either the old copy or the complete new one (tmp copy + fsync + rename)."""
    tmp = dst.parent / f".{dst.name}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, tmp)
    for p in tmp.rglob("*"):
        if p.is_file():
            _fsync_file(p)
    old = dst.parent / f".{dst.name}.old"
    if dst.exists():
        if old.exists():
            shutil.rmtree(old)
        os.replace(dst, old)
    os.replace(tmp, dst)
    _fsync_dir(dst.parent)
    if old.exists():
        shutil.rmtree(old)


class MemSampler:
    """Samples MemAvailable and this process's RSS while a checkpoint is saved (the host-memory spike)."""

    def __init__(self, every: float = 0.2):
        import threading

        self.every, self.min_avail, self.max_rss = every, float("inf"), 0.0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def _read() -> tuple[float, float]:
        avail = next(int(x.split()[1]) for x in open("/proc/meminfo") if x.startswith("MemAvailable:")) / 2**20
        rss = next(int(x.split()[1]) for x in open("/proc/self/status") if x.startswith("VmRSS:")) / 2**20
        return avail, rss

    def _run(self):
        while not self._stop.is_set():
            a, r = self._read()
            self.min_avail, self.max_rss = min(self.min_avail, a), max(self.max_rss, r)
            self._stop.wait(self.every)

    def __enter__(self):
        self.start_avail, self.start_rss = self._read()
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()

    def report(self) -> dict:
        return {"mem_available_start_gib": round(self.start_avail, 2), "mem_available_min_gib": round(self.min_avail, 2),
                "host_spike_gib": round(self.start_avail - self.min_avail, 2),
                "rss_start_gib": round(self.start_rss, 2), "rss_max_gib": round(self.max_rss, 2)}
