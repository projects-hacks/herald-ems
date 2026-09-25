#!/usr/bin/env python3
"""The ONE launcher for any job that loads a model or a lot of data (training, benchmarks, Whisper/TTS jobs, merges).

  scripts/run_job.py --name X --need-gib N [--gpu] [--priority normal|critical] [--host-max-gib M] [--gpu-max-gib G]
                     [--wait S] -- <cmd ...>

Refuses in demo mode; with --gpu queues on ~/.cache/herald-gpu.lock (one GPU-heavy job at a time); waits until
MemAvailable - reserve >= N; runs the command in `systemd-run --user --scope` with MemoryMax (host memory) and
oom_score_adj 1000, and caps torch's CUDA allocator at the GPU budget (N unless --gpu-max-gib). The memory guard
(scripts/memguard.py) kills guarded jobs first. Exit code: the command's, or 75 if refused / timed out.
Details: docs/MEMORY_SAFETY.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memguard import config as mgconfig  # noqa: E402
from memguard.launcher import EX_TEMPFAIL, JobSpec, Refused, run  # noqa: E402


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--need-gib", type=float, required=True, help="memory the job needs (host + GPU), GiB")
    ap.add_argument("--gpu", action="store_true", help="GPU-heavy: take the exclusive GPU lock (queued)")
    ap.add_argument("--host-max-gib", type=float, help="cgroup MemoryMax (default: need + host margin)")
    ap.add_argument("--gpu-max-gib", type=float, help="torch CUDA allocator cap (default: --need-gib)")
    ap.add_argument("--priority", choices=["normal", "critical"], default="normal",
                    help="critical: the guard kills it last, with a long SIGTERM grace; other --gpu jobs are refused "
                         "while it runs")
    ap.add_argument("--wait", type=float, help="seconds to wait for memory / the GPU lock / a running critical job "
                                                "(default: config; without it a --gpu job is refused while a "
                                                "critical job runs)")
    ap.add_argument("--config", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="print the systemd-run command and exit")
    a = ap.parse_args(argv)
    try:
        spec = JobSpec(a.name, a.need_gib, tuple(cmd), a.gpu, a.host_max_gib, a.gpu_max_gib, a.priority)
    except ValueError as e:
        ap.error(str(e))
    try:
        return run(spec, mgconfig.load(a.config), wait_s=a.wait, dry_run=a.dry_run)
    except Refused as e:
        print(f"[run_job] refused: {e}", file=sys.stderr)
        return EX_TEMPFAIL


if __name__ == "__main__":
    sys.exit(main())
