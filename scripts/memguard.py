#!/usr/bin/env python3
"""Herald memory guard (docs/MEMORY_SAFETY.md). Installed as a systemd --user service by scripts/memguard.sh.

  memguard.py run [--config X] [--dry-run]   the watchdog loop (what the service runs)
  memguard.py once [--config X]              one classification, printed: protected, victims in kill order
  memguard.py status [--config X]            the status file the running guard writes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memguard import config as mgconfig, policy, probe  # noqa: E402
from memguard.daemon import Guard  # noqa: E402
from memguard.state import read_json  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "once", "status"])
    ap.add_argument("--config", type=Path, default=None, help="default: config/memguard.yaml")
    ap.add_argument("--dry-run", action="store_true", help="log the victim it would pick, kill nothing")
    a = ap.parse_args(argv)
    cfg = mgconfig.load(a.config)
    if a.cmd == "run":
        Guard(cfg, dry_run=a.dry_run).run()
        return 0
    if a.cmd == "status":
        st = read_json(cfg.paths.status_file)
        if not st:
            print(f"no status file at {cfg.paths.status_file}: the guard is not running")
            return 1
        st["heartbeat_age_s"] = round(time.time() - st.get("ts", 0), 1)
        print(json.dumps(st, indent=1))
        return 0 if st["heartbeat_age_s"] < 5 else 1
    gpu = probe.GpuProbe(0).get()
    procs = probe.processes()
    mine = [p for p, pr in procs.items() if pr.uid == os.getuid()]
    c = policy.classify(procs, gpu, cfg, uid=os.getuid(), self_pid=os.getpid(),
                        port_owner_pids=probe.port_owners(cfg.protected.ports, mine))
    avail, total = probe.available_gib()
    print(f"MemAvailable {avail:.1f} / {total:.1f} GiB, PSI {probe.psi()}")
    print("protected:")
    for pid, why in sorted(c.protected.items()):
        rss = procs[pid].rss_kib / 1024 ** 2 + gpu.get(pid, 0) / 1024
        if rss >= 0.05:
            print(f"  {pid:>7} {rss:6.1f} GiB  {why:<22} {procs[pid].cmdline[:90]}")
    print(f"  (+{sum(1 for p in c.protected if procs[p].rss_kib < 50 * 1024)} small ones)")
    print("victims in kill order:")
    for v in policy.order(c.victims, cfg):
        print(f"  {v.klass:<15} {v.size_gib:6.1f} GiB (rss {v.rss_gib:.1f}, gpu {v.gpu_gib:.1f}) root {v.root} "
              f"x{len(v.pids)}  {v.label[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
