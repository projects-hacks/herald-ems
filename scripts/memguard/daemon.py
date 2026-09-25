"""The watchdog loop: read memory and pressure every tick, classify processes, terminate one victim at a time."""
from __future__ import annotations

import collections
import ctypes
import os
import signal
import time
from typing import Optional

from . import policy, probe
from .actions import Terminator
from .config import GuardConfig
from .state import DemoFlag, EventLog, JobRegistry, iso, write_json_atomic


def lock_memory(log) -> None:
    """mlockall so the guard's own pages are never evicted when it is needed most."""
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        if libc.mlockall(1 | 2) != 0:                      # MCL_CURRENT | MCL_FUTURE
            log("note", msg=f"mlockall failed (errno {ctypes.get_errno()}); running unlocked")
    except OSError as e:
        log("note", msg=f"mlockall unavailable: {e}")


class Guard:
    def __init__(self, cfg: GuardConfig, log: Optional[EventLog] = None, dry_run: bool = False):
        self.cfg, self.dry_run = cfg, dry_run
        self.log = log or EventLog(cfg.paths.log_file)
        self.demo = DemoFlag(cfg.paths.demo_flag)
        self.jobs = JobRegistry(cfg.paths.jobs_dir)
        self.gpu = probe.GpuProbe(cfg.gpu_poll_s)
        self.term = Terminator(cfg.term_grace_s, cfg.zrt_stop_timeout_s, self.log,
                               critical_grace_s=cfg.critical_term_grace_s)
        self._samples: collections.deque = collections.deque()      # (monotonic t, policy.sizes(...))
        self.uid, self.pid = os.getuid(), os.getpid()
        self.level = "ok"
        self._procs: dict = {}
        self._cls = policy.Classification()
        self._proc_at = -1e9
        self._warn_at = -1e9
        self._settle_until = 0.0
        self._no_victim_at = -1e9
        self._mode = None
        self._stop = False

    def refresh(self, now: float, gpu: dict) -> None:
        self._procs = probe.processes()
        mine = [p for p, pr in self._procs.items() if pr.uid == self.uid]
        owners = probe.port_owners(self.cfg.protected.ports, mine)
        self._cls = policy.classify(self._procs, gpu, self.cfg, uid=self.uid, self_pid=self.pid,
                                    port_owner_pids=owners, job_priority=self.job_priorities())
        self._proc_at = now
        self._samples.append((now, policy.sizes(self._procs, gpu)))
        while len(self._samples) > 2 and now - self._samples[1][0] >= self.cfg.growth_window_s:
            self._samples.popleft()

    def job_priorities(self) -> dict[str, str]:
        """Registry first; a job scope missing from it is read from its HERALD_JOB_PRIORITY environment."""
        pri = self.jobs.priorities()
        for unit, pid in policy.job_scopes(self._procs, self.cfg.run_job.unit_prefix).items():
            if unit not in pri:
                pri[unit] = probe.environ_var(pid, "HERALD_JOB_PRIORITY") or "normal"
        return pri

    def growth(self) -> list[dict]:
        if len(self._samples) < 2:
            return []
        return policy.growing(self._samples[0][1], self._samples[-1][1], self._procs, self._cls)

    def _kill(self, victim: policy.Victim, now: float, reason: str) -> None:
        if self.dry_run:
            self.log("would_kill", victim=victim.brief(), reason=reason)
            self._settle_until = now + 5.0
            return
        starts = {p: self._procs[p].start_epoch for p in victim.pids if p in self._procs}
        self.term.start(victim, now, starts, reason)

    def tick(self) -> dict:
        now = time.monotonic()
        avail, total = probe.available_gib()
        pressure = probe.psi()
        demo = self.demo.on()
        mode = "demo" if demo else "normal"
        if mode != self._mode:
            self.log("mode", mode=mode)
            self._mode = mode
        t = self.cfg.thresholds_for(demo)
        lvl = policy.evaluate(avail, pressure.get("full_avg10", 0.0), t)
        if lvl.name != self.level:
            self.log("level", level=lvl.name, was=self.level, reason=lvl.reason, available_gib=round(avail, 2))
            self.level = lvl.name
        gpu = self.gpu.get(now)
        if lvl.name != "ok" or demo or now - self._proc_at >= self.cfg.process_poll_s:
            self.refresh(now, gpu)
        if self.term.busy:
            if self.term.poll(now) == "gone":
                self._settle_until = now + self.cfg.settle_s
        elif now >= self._settle_until:
            strangers = []
            if demo and self.cfg.demo.kill_new_gpu_processes:
                strangers = policy.demo_strangers(self._cls, gpu, self._procs, self.cfg, self.demo.since() or 0.0)
            if strangers:
                self._kill(strangers[0], now, "demo mode: new non-protected GPU process")
            elif lvl.name == "kill":
                victim = policy.choose(self._cls, self.cfg)
                if victim:
                    self._kill(victim, now, lvl.reason)
                elif now - self._no_victim_at >= self.cfg.warn_log_every_s:
                    self._no_victim_at = now
                    self.log("no_victim", reason=lvl.reason, available_gib=round(avail, 2))
        critical = [v.label for v in self._cls.victims if v.klass == "critical_jobs"]
        every = self.cfg.critical_warn_log_every_s if critical else self.cfg.warn_log_every_s
        if lvl.name in ("warn", "kill") and now - self._warn_at >= every:
            self._warn_at = now
            top = policy.order(self._cls.victims, self.cfg)[:3]
            extra = {"critical_jobs": critical, "growing": self.growth()} if critical else {}
            self.log("warn", level=lvl.name, reason=lvl.reason, available_gib=round(avail, 2),
                     next_victims=[v.brief() for v in top], **extra)
        status = {"ts": round(time.time(), 3), "heartbeat": iso(), "pid": self.pid, "mode": mode, "level": lvl.name,
                  "reason": lvl.reason, "available_gib": round(avail, 2), "total_gib": round(total, 2),
                  "psi_full_avg10": pressure.get("full_avg10"), "psi_some_avg10": pressure.get("some_avg10"),
                  "thresholds": t.__dict__, "dry_run": self.dry_run,
                  "protected_pids": sorted(self._cls.protected),
                  "jobs": [{"unit": j.get("unit"), "priority": j.get("priority", "normal")} for j in self.jobs.all()],
                  "killing": self.term.victim.brief() if self.term.victim else None,
                  "last_action": self.log.last}
        write_json_atomic(self.cfg.paths.status_file, status)
        return status

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_stop", True))
        self.log("start", pid=self.pid, dry_run=self.dry_run, thresholds=self.cfg.thresholds.__dict__,
                 demo_thresholds=self.cfg.demo.thresholds.__dict__, keep=sorted(self.cfg.protected.vllm_keep))
        lock_memory(self.log)
        period = 1.0 / self.cfg.poll_hz
        last_prune = 0.0
        while not self._stop:
            t0 = time.monotonic()
            try:
                self.tick()
                if t0 - last_prune > 30:
                    self.jobs.prune()
                    last_prune = t0
            except Exception as e:                        # the guard must outlive any single bad reading
                self.log("error", msg=f"{type(e).__name__}: {e}")
            time.sleep(max(0.05, period - (time.monotonic() - t0)))
        self.log("stop", pid=self.pid)
