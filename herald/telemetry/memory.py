"""Machine memory and the memory guard's state for /api/health (docs/MEMORY_SAFETY.md).

The guard (scripts/memguard.py, a systemd --user service) writes its status file about twice a second; the app only
reads it. A missing, stale or unreadable file means the guard is not running; this never raises.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

GIB = 1024 ** 3


def parse_meminfo(text: str) -> dict:
    """{'available_gib': .., 'total_gib': ..} from /proc/meminfo text (None when a field is missing)."""
    kib = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        if k in ("MemAvailable", "MemTotal") and v.split():
            kib[k] = int(v.split()[0])
    return {"available_gib": round(kib["MemAvailable"] * 1024 / GIB, 1) if "MemAvailable" in kib else None,
            "total_gib": round(kib["MemTotal"] * 1024 / GIB, 1) if "MemTotal" in kib else None}


def guard_state(status: Optional[dict], now: float, stale_s: float) -> dict:
    """{'running', 'mode', 'last_action'} from the guard's status file contents."""
    if not isinstance(status, dict):
        return {"running": False, "mode": None, "last_action": None}
    ts = status.get("ts")
    running = isinstance(ts, (int, float)) and 0 <= now - ts < stale_s
    return {"running": running, "mode": status.get("mode"), "last_action": status.get("last_action")}


def _read_status(path: Path) -> Optional[dict]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def memory_health(status_path: Path, stale_s: float, meminfo_path: str = "/proc/meminfo",
                  now: Optional[float] = None) -> dict:
    try:
        with open(meminfo_path) as f:
            mem = parse_meminfo(f.read())
    except OSError:
        mem = {"available_gib": None, "total_gib": None}
    return mem | {"guard": guard_state(_read_status(status_path), time.time() if now is None else now, stale_s)}
