"""Pure decisions: the memory level, who is protected, the victim classes and their order. No I/O."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

from .config import GuardConfig, Thresholds
from .probe import Proc

GIB_MIB = 1024.0
_SERVED = re.compile(r"--served-model-name[ =](\S+)")
_VLLM = re.compile(r"(^|/)vllm serve ")


@dataclass(frozen=True)
class Level:
    name: str          # ok | warn | kill
    reason: str


def evaluate(avail_gib: float, psi_full_avg10: float, t: Thresholds) -> Level:
    if avail_gib < t.kill_below_gib:
        return Level("kill", f"MemAvailable {avail_gib:.1f} GiB < {t.kill_below_gib:g} GiB")
    if psi_full_avg10 > t.psi_full_avg10_kill:
        return Level("kill", f"PSI full avg10 {psi_full_avg10:.1f}% > {t.psi_full_avg10_kill:g}%")
    if avail_gib < t.warn_below_gib:
        return Level("warn", f"MemAvailable {avail_gib:.1f} GiB < {t.warn_below_gib:g} GiB")
    return Level("ok", "")


@dataclass
class Victim:
    klass: str                      # guarded_jobs | user_processes | vllm_services | critical_jobs
    label: str                      # job unit, command, or vLLM service label
    root: int
    pids: tuple[int, ...]
    rss_gib: float
    gpu_gib: float
    unit: Optional[str] = None      # systemd scope (guarded_jobs)
    cgroup: Optional[str] = None
    service: Optional[str] = None   # vLLM --served-model-name (vllm_services)
    newest_start: float = 0.0

    @property
    def size_gib(self) -> float:
        return self.rss_gib + self.gpu_gib

    def brief(self) -> dict:
        return {"class": self.klass, "label": self.label, "root": self.root, "pids": list(self.pids),
                "rss_gib": round(self.rss_gib, 2), "gpu_gib": round(self.gpu_gib, 2), "unit": self.unit,
                "service": self.service}


@dataclass
class Classification:
    protected: dict[int, str] = field(default_factory=dict)     # pid -> reason
    victims: list[Victim] = field(default_factory=list)         # every candidate group, unordered


def served_label(cmdline: str) -> Optional[str]:
    """The service label of a `vllm serve` root process, else None."""
    if not _VLLM.search(cmdline):
        return None
    m = _SERVED.search(cmdline)
    return m.group(1) if m else "?"


def _descendants(root: int, children: Mapping[int, list[int]]) -> list[int]:
    out, stack = [], [root]
    while stack:
        p = stack.pop()
        out.append(p)
        stack.extend(children.get(p, ()))
    return out


def job_unit(cgroup: str, prefix: str) -> Optional[str]:
    for part in cgroup.split("/"):
        if part.startswith(prefix) and part.endswith(".scope"):
            return part
    return None


def classify(procs: Mapping[int, Proc], gpu_mib: Mapping[int, float], cfg: GuardConfig, *, uid: int,
             self_pid: int, port_owner_pids: Iterable[int] = (),
             job_priority: Optional[Mapping[str, str]] = None) -> Classification:
    """Split this user's processes into protected ones and victim groups (one group = what one kill takes down).
    `job_priority` maps a job scope (herald-job-….scope) to "normal" or "critical"; critical jobs are class (d)."""
    job_priority = job_priority or {}
    children: dict[int, list[int]] = {}
    for p in procs.values():
        children.setdefault(p.ppid, []).append(p.pid)
    mine = {pid for pid, p in procs.items() if p.uid == uid}
    c = Classification()

    def protect(pids, reason):
        for pid in pids:
            if pid in mine:
                c.protected.setdefault(pid, reason)

    # the guard itself and its ancestors
    pid = self_pid
    while pid in procs and pid > 1:
        protect([pid], "memory guard")
        pid = procs[pid].ppid
    for pid in port_owner_pids:
        protect(_descendants(pid, children) if cfg.protected.port_descendants else [pid], "demo port")
    for p in procs.values():
        # a guarded job's scope is a victim as a whole, whatever it runs (e.g. `bash -c ...`)
        if p.pid in mine and not job_unit(p.cgroup, cfg.run_job.unit_prefix):
            for r in cfg.protected.rules:
                if r.pattern.search(p.cmdline):
                    protect([p.pid], r.name)
                    break

    def size(pids):
        return (sum(procs[x].rss_kib for x in pids) / 1024 ** 2,
                sum(gpu_mib.get(x, 0.0) for x in pids) / GIB_MIB)

    claimed: set[int] = set()
    # (c) and keep-listed vLLM service trees
    for p in procs.values():
        label = served_label(p.cmdline) if p.pid in mine else None
        if label is None:
            continue
        tree = [x for x in _descendants(p.pid, children) if x in mine]
        if label in cfg.protected.vllm_keep:
            protect(tree, f"vLLM keep-list: {label}")
            continue
        tree = [x for x in tree if x not in c.protected]
        if tree:
            rss, gpu = size(tree)
            c.victims.append(Victim("vllm_services", label, p.pid, tuple(tree), rss, gpu, service=label,
                                    newest_start=max(procs[x].start_epoch for x in tree)))
            claimed.update(tree)
    # (a) guarded jobs: every process inside a run_job scope, whatever its command
    units: dict[str, list[int]] = {}
    for pid in mine:
        u = job_unit(procs[pid].cgroup, cfg.run_job.unit_prefix)
        if u and pid not in c.protected and pid not in claimed:
            units.setdefault(u, []).append(pid)
    for u, pids in units.items():
        pids.sort(key=lambda x: procs[x].start_epoch)
        rss, gpu = size(pids)
        klass = "critical_jobs" if job_priority.get(u) == "critical" else "guarded_jobs"
        c.victims.append(Victim(klass, u, pids[0], tuple(pids), rss, gpu, unit=u,
                                cgroup=procs[pids[0]].cgroup,
                                newest_start=max(procs[x].start_epoch for x in pids)))
        claimed.update(pids)
    # (b) everything else of ours, grouped into same-executable trees (a worker pool dies with its parent)
    rest = {pid for pid in mine if pid not in c.protected and pid not in claimed}

    def root_of(pid):
        while True:
            par = procs[pid].ppid
            if par in rest and procs[par].exe and procs[par].exe == procs[pid].exe:
                pid = par
            else:
                return pid
    groups: dict[int, list[int]] = {}
    for pid in rest:
        groups.setdefault(root_of(pid), []).append(pid)
    for root, pids in groups.items():
        rss, gpu = size(pids)
        c.victims.append(Victim("user_processes", procs[root].cmdline[:120], root, tuple(sorted(pids)), rss, gpu,
                                newest_start=max(procs[x].start_epoch for x in pids)))
    return c


def order(victims: Iterable[Victim], cfg: GuardConfig) -> list[Victim]:
    """Kill order: class order from the config, then the largest (RSS + GPU) first; too-small groups dropped."""
    rank = {k: i for i, k in enumerate(cfg.victims)}
    ok = [v for v in victims if v.klass in rank and v.size_gib >= cfg.min_victim_gib]
    return sorted(ok, key=lambda v: (rank[v.klass], -v.size_gib, v.root))


def choose(c: Classification, cfg: GuardConfig) -> Optional[Victim]:
    ranked = order(c.victims, cfg)
    return ranked[0] if ranked else None


def demo_strangers(c: Classification, gpu_mib: Mapping[int, float], procs: Mapping[int, Proc], cfg: GuardConfig,
                   demo_since: float) -> list[Victim]:
    """Demo mode: non-protected groups holding GPU memory with a process started after demo mode went on."""
    out = []
    for v in c.victims:
        holders = [p for p in v.pids if gpu_mib.get(p, 0.0) >= cfg.demo.gpu_min_mib]
        if holders and any(procs[p].start_epoch >= demo_since for p in holders if p in procs):
            out.append(v)
    return sorted(out, key=lambda v: -v.size_gib)


def job_scopes(procs: Mapping[int, Proc], prefix: str) -> dict[str, int]:
    """{job scope: its oldest pid} for every run_job scope in the process table."""
    out: dict[str, int] = {}
    for p in sorted(procs.values(), key=lambda p: p.start_epoch):
        u = job_unit(p.cgroup, prefix)
        if u and u not in out:
            out[u] = p.pid
    return out


def sizes(procs: Mapping[int, Proc], gpu_mib: Mapping[int, float]) -> dict[int, tuple[float, float]]:
    """{pid: (start time, RSS + GPU GiB)}: one sample for the growth report."""
    return {pid: (p.start_epoch, p.rss_kib / 1024 ** 2 + gpu_mib.get(pid, 0.0) / GIB_MIB) for pid, p in procs.items()}


def growing(old: Mapping[int, tuple[float, float]], new: Mapping[int, tuple[float, float]],
            procs: Mapping[int, Proc], c: Classification, top: int = 5, min_gib: float = 0.25) -> list[dict]:
    """The processes that grew most between two samples (a process new since `old` counts in full), protected or not:
    who is eating into the memory a critical job needs."""
    out = []
    for pid, (start, now_gib) in new.items():
        was = old.get(pid)
        grew = now_gib - (was[1] if was and abs(was[0] - start) < 1.0 else 0.0)
        if grew >= min_gib and pid in procs:
            owner = (c.protected.get(pid) or next((v.klass for v in c.victims if pid in v.pids), None)
                     or f"uid {procs[pid].uid} (not ours)")
            out.append({"pid": pid, "grew_gib": round(grew, 2), "now_gib": round(now_gib, 2), "owner": owner,
                        "cmd": procs[pid].cmdline[:100]})
    return sorted(out, key=lambda d: -d["grew_gib"])[:top]
