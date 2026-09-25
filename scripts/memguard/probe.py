"""Read the machine: memory, pressure, processes, listening ports, per-process GPU memory. I/O only, no decisions."""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

GIB = 1024 ** 3
CLK_TCK = os.sysconf("SC_CLK_TCK")


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    uid: int
    rss_kib: int
    start_epoch: float
    cmdline: str
    exe: str
    cgroup: str


def parse_meminfo(text: str) -> dict[str, int]:
    """MemTotal / MemAvailable / ... in bytes."""
    out = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        parts = v.split()
        if parts and parts[0].isdigit():
            out[k] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    return out


def meminfo(path: str = "/proc/meminfo") -> dict[str, int]:
    with open(path) as f:
        return parse_meminfo(f.read())


def available_gib(path: str = "/proc/meminfo") -> tuple[float, float]:
    m = meminfo(path)
    return m["MemAvailable"] / GIB, m["MemTotal"] / GIB


def parse_psi(text: str) -> dict[str, float]:
    """{'some_avg10': .., 'full_avg10': .., ...} from /proc/pressure/memory."""
    out = {}
    for line in text.splitlines():
        kind, *fields = line.split()
        for f in fields:
            k, _, v = f.partition("=")
            if k.startswith("avg"):
                out[f"{kind}_{k}"] = float(v)
    return out


def psi(path: str = "/proc/pressure/memory") -> dict[str, float]:
    try:
        with open(path) as f:
            return parse_psi(f.read())
    except OSError:
        return {}


def _boot_time() -> float:
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("btime"):
                return float(line.split()[1])
    return 0.0


_BTIME = _boot_time()


def read_proc(pid: int) -> Optional[Proc]:
    base = f"/proc/{pid}"
    try:
        with open(f"{base}/stat") as f:
            stat = f.read()
        rest = stat[stat.rindex(")") + 2:].split()
        ppid, start = int(rest[1]), int(rest[19])
        with open(f"{base}/status") as f:
            status = f.read()
        uid, rss = -1, 0
        for line in status.splitlines():
            if line.startswith("Uid:"):
                uid = int(line.split()[1])
            elif line.startswith("VmRSS:"):
                rss = int(line.split()[1])
        with open(f"{base}/cmdline", "rb") as f:
            cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
        try:
            exe = os.readlink(f"{base}/exe")
        except OSError:
            exe = ""
        try:
            with open(f"{base}/cgroup") as f:
                cg = f.read().strip().rpartition("::")[2]
        except OSError:
            cg = ""
    except (OSError, ValueError, IndexError):
        return None
    return Proc(pid, ppid, uid, rss, _BTIME + start / CLK_TCK, cmd, exe, cg)


def processes() -> dict[int, Proc]:
    out = {}
    for name in os.listdir("/proc"):
        if name.isdigit():
            p = read_proc(int(name))
            if p is not None and p.cmdline:          # kernel threads have an empty cmdline
                out[p.pid] = p
    return out


def listening_inodes(ports, files=("/proc/net/tcp", "/proc/net/tcp6")) -> set[str]:
    want = {int(p) for p in ports}
    inodes = set()
    for fn in files:
        try:
            with open(fn) as f:
                next(f)
                for line in f:
                    cols = line.split()
                    if cols[3] == "0A" and int(cols[1].rsplit(":", 1)[1], 16) in want:
                        inodes.add(cols[9])
        except (OSError, StopIteration):
            continue
    return inodes


def port_owners(ports, pids) -> set[int]:
    """PIDs (among `pids`, the ones we may read) holding a listening socket on one of `ports`."""
    inodes = listening_inodes(ports)
    if not inodes:
        return set()
    want = {f"socket:[{i}]" for i in inodes}
    owners = set()
    for pid in pids:
        try:
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError:
            continue
        for fd in fds:
            try:
                if os.readlink(f"/proc/{pid}/fd/{fd}") in want:
                    owners.add(pid)
                    break
            except OSError:
                continue
    return owners


def parse_nvidia_smi(text: str) -> dict[int, float]:
    """`pid, name, used_memory` CSV lines -> {pid: MiB}; unknown values ("[N/A]") are skipped."""
    out: dict[int, float] = {}
    for line in text.splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 3 or not cols[0].isdigit():
            continue
        mem = cols[-1].split()[0] if cols[-1] else ""
        try:
            out[int(cols[0])] = out.get(int(cols[0]), 0.0) + float(mem)
        except ValueError:
            continue
    return out


class GpuProbe:
    """Per-process GPU memory from nvidia-smi, re-read at most every `every_s` seconds (it costs ~0.1-0.3 s)."""

    def __init__(self, every_s: float, timeout_s: float = 5.0):
        self.every_s, self.timeout_s = every_s, timeout_s
        self._at, self._last = -1e9, {}

    def get(self, now: Optional[float] = None) -> dict[int, float]:
        now = time.monotonic() if now is None else now
        if now - self._at >= self.every_s:
            self._at = now
            try:
                r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                                    "--format=csv,noheader,nounits"], capture_output=True, text=True,
                                   timeout=self.timeout_s)
                if r.returncode == 0:
                    self._last = parse_nvidia_smi(r.stdout)
            except (OSError, subprocess.TimeoutExpired):
                pass                                    # keep the last reading
        return dict(self._last)


def cgroup_procs(cgroup: str, root: str = "/sys/fs/cgroup") -> list[int]:
    try:
        return [int(x) for x in Path(root, cgroup.lstrip("/"), "cgroup.procs").read_text().split()]
    except (OSError, ValueError):
        return []


def environ_var(pid: int, name: str) -> Optional[str]:
    """One variable from /proc/<pid>/environ (readable for our own processes)."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            for item in f.read().split(b"\0"):
                k, _, v = item.partition(b"=")
                if k.decode(errors="replace") == name:
                    return v.decode(errors="replace")
    except OSError:
        pass
    return None
