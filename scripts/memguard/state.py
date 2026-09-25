"""Files shared by the guard, the job launcher, demo_mode.sh and the Herald app: the status file, the JSON-lines log,
the demo-mode flag and the guarded-job registry."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc).isoformat(timespec="seconds")


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    os.replace(tmp, path)


def read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


ACTIONS = ("kill", "critical_kill", "sigkill", "escalate", "victim_gone", "no_victim", "would_kill")   # what `last_action` shows


class EventLog:
    """Append-only JSON lines (one event per line) plus a copy on stdout for journald."""

    def __init__(self, path: Path, echo: bool = True):
        self.path, self.echo = Path(path), echo
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.last: Optional[dict] = self._last_action()      # survives a guard restart

    def _last_action(self) -> Optional[dict]:
        try:
            with open(self.path, "rb") as f:
                f.seek(max(0, f.seek(0, 2) - 256 * 1024))
                lines = f.read().decode(errors="replace").splitlines()
        except OSError:
            return None
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") in ACTIONS:
                return rec
        return None

    def __call__(self, event: str, **fields) -> dict:
        rec = {"ts": round(time.time(), 3), "iso": iso(), "event": event, **fields}
        line = json.dumps(rec, default=str)
        with open(self.path, "a") as f:
            f.write(line + "\n")
        if self.echo:
            print(line, flush=True)
        if event in ACTIONS:
            self.last = rec
        return rec


class DemoFlag:
    def __init__(self, path: Path):
        self.path = Path(path)

    def on(self) -> bool:
        return self.path.exists()

    def since(self) -> Optional[float]:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None


class JobRegistry:
    """One JSON file per running guarded job (~/.local/state/herald/jobs/<unit>.json)."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def add(self, unit: str, **info) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        p = self.dir / f"{unit}.json"
        write_json_atomic(p, {"unit": unit, "started": iso(), **info})
        return p

    def remove(self, unit: str) -> None:
        try:
            (self.dir / f"{unit}.json").unlink()
        except OSError:
            pass

    def all(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        return [j for j in (read_json(p) for p in sorted(self.dir.glob("*.json"))) if j]

    def critical(self) -> list[dict]:
        """Live jobs started with --priority critical."""
        return [j for j in self.prune() if j.get("priority") == "critical"]

    def priorities(self) -> dict[str, str]:
        """{job scope name: priority} for the guard."""
        return {f"{j['unit']}.scope": j.get("priority", "normal") for j in self.all() if j.get("unit")}

    def prune(self, alive=lambda pid: Path(f"/proc/{pid}").exists()) -> list[dict]:
        """Drop entries whose launcher is gone (a crashed run_job); return the live ones."""
        live = []
        for j in self.all():
            if alive(j.get("launcher_pid", -1)) or alive(j.get("pid", -1)):
                live.append(j)
            else:
                self.remove(j["unit"])
        return live
