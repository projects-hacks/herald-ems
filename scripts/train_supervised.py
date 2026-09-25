#!/usr/bin/env python3
"""Keep run F training until it finishes: run the trainer through the memory guard's launcher with --resume, and on
any failure wait (exponential backoff) and run it again, up to a retry cap. Every attempt is logged to
runs/herald-f-train.log. Installed as a systemd --user service (scripts/install_train_service.sh) so it also
continues after a reboot. MODEL_PLAN §0l "Crash safety".

  scripts/train_supervised.py                    # the real run (flags from config/training.yaml herald-f.supervisor)
  scripts/train_supervised.py --dry-run          # print the command it would run
  scripts/train_supervised.py -- --max-steps 20  # extra trainer flags after --

Exit codes: 0 finished; 3 the plan changed (never retried: rebuild or use a new --out); 1 retry cap reached.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
PERMANENT = {3}          # train_vlm_lora.EXIT_PLAN_CHANGED
TEMPFAIL = 75            # run_job.py: refused / timed out waiting for memory or the GPU lock


def backoff(attempt: int, base: float, cap: float) -> float:
    """Seconds to wait before attempt `attempt` (1-based; the first waits 0)."""
    return 0.0 if attempt <= 1 else min(cap, base * 2 ** (attempt - 2))


def command(sv: dict, extra: list[str], run_job_flags: set[str]) -> list[str]:
    job = [PY, str(ROOT / "scripts" / "run_job.py"), "--name", sv["job_name"], "--need-gib", str(sv["need_gib"]),
           "--gpu", "--wait", str(sv["wait_s"])]
    if "--priority" in run_job_flags:
        job += ["--priority", sv["priority"]]
    if sv.get("gpu_max_gib"):
        job += ["--gpu-max-gib", str(sv["gpu_max_gib"])]
    return job + ["--", PY, str(ROOT / "scripts" / "train_vlm_lora.py"), "--resume", *sv.get("train_args", []), *extra]


def supervise(cmd: list[str], sv: dict, log: Path, run: Callable[[list[str], Path], int],
              sleep: Callable[[float], None] = time.sleep) -> int:
    """Run until exit 0. A refused start (75: not enough memory yet, or the GPU is busy) is retried without using up
    the cap; a permanent failure stops at once."""
    failures, attempt = 0, 0
    while True:
        attempt += 1
        wait = backoff(failures + 1, sv["backoff_s"], sv["backoff_cap_s"])
        if wait:
            _log(log, {"event": "backoff", "seconds": wait, "failures": failures})
            sleep(wait)
        _log(log, {"event": "start", "attempt": attempt, "cmd": " ".join(cmd)})
        t0 = time.time()
        code = run(cmd, log)
        _log(log, {"event": "exit", "attempt": attempt, "code": code, "seconds": round(time.time() - t0)})
        if code == 0:
            return 0
        if code in PERMANENT:
            _log(log, {"event": "permanent_failure", "code": code})
            return code
        if code == TEMPFAIL:
            sleep(sv["tempfail_wait_s"])
            continue
        failures += 1
        if failures >= sv["max_failures"]:
            _log(log, {"event": "gave_up", "failures": failures})
            return 1


def _log(log: Path, rec: dict) -> None:
    line = json.dumps({"supervisor": True, "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **rec})
    with open(log, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _run(cmd: list[str], log: Path) -> int:
    with open(log, "a") as f:
        return subprocess.call(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)


def run_job_flags() -> set[str]:
    try:
        h = subprocess.run([PY, str(ROOT / "scripts" / "run_job.py"), "--help"], capture_output=True, text=True,
                           timeout=60).stdout
    except Exception:
        return set()
    return {w.strip(",") for w in h.split() if w.startswith("--")}


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    argv = argv[: argv.index("--")] if "--" in argv else argv
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="herald-f")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from herald.config import load_yaml

    sv = load_yaml("training.yaml")[a.config]["supervisor"]
    flags = run_job_flags()
    cmd = command(sv, extra, flags)
    if "--priority" not in flags:
        print(json.dumps({"warning": "run_job.py has no --priority yet; running without it"}))
    if a.dry_run:
        print(" ".join(cmd))
        return 0
    return supervise(cmd, sv, ROOT / sv["log"], _run)


if __name__ == "__main__":
    sys.exit(main())
