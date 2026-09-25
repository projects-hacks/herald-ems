"""The one launcher for model-loading jobs (scripts/run_job.py): refuse in demo mode, queue for the GPU, wait for
memory, then run the command in a capped systemd --user scope that the kernel and the guard kill first."""
from __future__ import annotations

import fcntl
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .config import PRIORITIES, GuardConfig
from .state import DemoFlag, JobRegistry

GPUCAP_DIR = Path(__file__).resolve().parent / "gpucap"
EX_TEMPFAIL = 75                                  # refused or timed out: try again later


class Refused(Exception):
    pass


@dataclass(frozen=True)
class JobSpec:
    name: str
    need_gib: float
    cmd: tuple[str, ...]
    gpu: bool = False
    host_max_gib: Optional[float] = None
    gpu_max_gib: Optional[float] = None
    priority: str = "normal"                      # critical: killed last (class d); while it runs, --gpu jobs and
                                                  # jobs over run_job.critical_coexist_gib are refused

    def __post_init__(self):
        if self.priority not in PRIORITIES:
            raise ValueError(f"--priority must be one of {PRIORITIES}")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,40}", self.name):
            raise ValueError("--name: letters, digits, _ . - (max 41 chars)")
        if self.need_gib <= 0:
            raise ValueError("--need-gib must be > 0")
        if not self.cmd:
            raise ValueError("no command after --")


def host_cap_gib(spec: JobSpec, cfg: GuardConfig) -> float:
    return spec.host_max_gib if spec.host_max_gib else spec.need_gib + cfg.run_job.host_margin_gib


def unit_name(spec: JobSpec, cfg: GuardConfig, now: Optional[datetime] = None) -> str:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S")
    return f"{cfg.run_job.unit_prefix}{spec.name}-{ts}"


def scope_argv(spec: JobSpec, cfg: GuardConfig, unit: str) -> list[str]:
    cap_mib = int(host_cap_gib(spec, cfg) * 1024)
    return ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--unit", unit,
            "-p", f"MemoryMax={cap_mib}M", "-p", "MemorySwapMax=0", "--", *spec.cmd]


def gpu_cap_gib(spec: JobSpec) -> Optional[float]:
    """The torch CUDA cap for a job, or None for no cap.

    For a normal job `--need-gib` doubles as the cap: it is a declared budget, and failing inside its own process
    with a CUDA OOM is the wanted behaviour (MEMORY_SAFETY §4.3). For a **critical** job `--need-gib` is only the
    condition to start: the run is the thing we cannot lose, and it must be free to use the memory that is actually
    there. A critical job is capped only when `--gpu-max-gib` says so explicitly. Reason: on 2026-09-25 the run F
    4B job was started with `--need-gib 40`, which became a 40 GiB cap, and it died with
    `torch.OutOfMemoryError ... 40.00 GiB allowed` while 63.8 GiB of the box was free.
    """
    if spec.gpu_max_gib:
        return spec.gpu_max_gib
    return None if spec.priority == "critical" else spec.need_gib


def job_env(spec: JobSpec, base: dict) -> dict:
    env = dict(base)
    env["HERALD_JOB"] = spec.name
    env["HERALD_JOB_PRIORITY"] = spec.priority
    cap = gpu_cap_gib(spec)
    if cap is not None:
        env["HERALD_GPU_MAX_GIB"] = f"{cap:g}"
    else:
        env.pop("HERALD_GPU_MAX_GIB", None)      # the gpucap hook caps nothing when this is unset
    env["PYTHONPATH"] = os.pathsep.join([str(GPUCAP_DIR)] + ([base["PYTHONPATH"]] if base.get("PYTHONPATH") else []))
    return env


def wait_for_memory(need_gib: float, reserve_gib: float, timeout_s: float, available: Callable[[], float],
                    demo_on: Callable[[], bool], clock=time.monotonic, sleep=time.sleep,
                    say: Callable[[str], None] = print, every_s: float = 2.0) -> float:
    """Block until available() - reserve >= need; Refused on timeout or if demo mode goes on meanwhile."""
    start, last_say = clock(), -1e9
    while True:
        if demo_on():
            raise Refused("demo mode is on: no jobs until `scripts/demo_mode.sh off`")
        avail = available()
        if avail - reserve_gib >= need_gib:
            return avail
        now = clock()
        if now - start >= timeout_s:
            raise Refused(f"timed out after {timeout_s:.0f} s waiting for {need_gib:g} GiB "
                          f"(+{reserve_gib:g} reserve); MemAvailable is {avail:.1f} GiB")
        if now - last_say >= 30:
            say(f"[run_job] waiting for memory: need {need_gib:g} + reserve {reserve_gib:g} GiB, "
                f"MemAvailable {avail:.1f} GiB")
            last_say = now
        sleep(every_s)


def acquire_gpu_lock(path: Path, timeout_s: float, holder: str, clock=time.monotonic, sleep=time.sleep,
                     say: Callable[[str], None] = print) -> int:
    """Exclusive flock (one GPU-heavy job at a time); returns the fd, held until the job exits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o664)
    start, said = clock(), False
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.write(fd, holder.encode())
            return fd
        except BlockingIOError:
            if not said:
                try:
                    who = Path(path).read_text().strip()
                except OSError:
                    who = "?"
                say(f"[run_job] GPU busy ({who or 'unknown holder'}); queued")
                said = True
            if clock() - start >= timeout_s:
                os.close(fd)
                raise Refused(f"timed out after {timeout_s:.0f} s waiting for the GPU lock {path}")
            sleep(2.0)


def check_critical(spec: JobSpec, reg: JobRegistry, wait_s: Optional[float], coexist_gib: float,
                   clock=time.monotonic, sleep=time.sleep, say: Callable[[str], None] = print) -> None:
    """Next to a running critical job, a --gpu job never starts, and neither does any job needing more than
    `coexist_gib` (`run_job.critical_coexist_gib`). Without --wait it is refused at once (no silent queueing for
    hours); with --wait it waits up to that long for the critical job to end.

    Size, not only --gpu, because of 2026-09-25 05:13 UTC: the box hard-froze while a CPU-only 4B model merge
    (`--need-gib 12`, no `--gpu`) ran alongside the critical 30B training job. Only `--gpu` jobs were refused while
    a critical job ran, so the CPU job was admitted. On the GB10 the GPU and the CPU share one 121.6 GiB unified
    memory pool (MEMORY_SAFETY §2), so a "CPU-only" job still competes directly with a training run. Jobs at or
    below `coexist_gib` stay allowed so trivial tooling is not blocked.
    """
    if not spec.gpu and spec.need_gib <= coexist_gib:
        return
    start, said = clock(), False
    while True:
        crit = reg.critical()
        if not crit:
            return
        names = ", ".join(f"{j.get('name')} ({j.get('unit')})" for j in crit)
        if wait_s is None:
            why = ("GPU jobs are refused" if spec.gpu else
                   f"jobs needing more than {coexist_gib:g} GiB are refused")
            raise Refused(f"a critical job is running: {names}. {why} while it runs; pass --wait "
                          f"<seconds> to queue behind it")
        if not said:
            say(f"[run_job] critical job running ({names}); waiting up to {wait_s:g} s")
            said = True
        if clock() - start >= wait_s:
            raise Refused(f"timed out after {wait_s:g} s waiting for the critical job {names}")
        sleep(5.0)


def run(spec: JobSpec, cfg: GuardConfig, *, wait_s: Optional[float] = None, dry_run: bool = False,
        available: Optional[Callable[[], float]] = None) -> int:
    from .probe import available_gib
    demo = DemoFlag(cfg.paths.demo_flag)
    if demo.on():
        raise Refused("demo mode is on: run_job refuses every job until `scripts/demo_mode.sh off`")
    timeout = cfg.run_job.wait_timeout_s if wait_s is None else wait_s
    unit = unit_name(spec, cfg)
    argv = scope_argv(spec, cfg, unit)
    if dry_run:
        print(" ".join(argv))
        return 0
    reg = JobRegistry(cfg.paths.jobs_dir)
    check_critical(spec, reg, wait_s, cfg.run_job.critical_coexist_gib)
    lock_fd = None
    if spec.gpu:
        lock_fd = acquire_gpu_lock(cfg.paths.gpu_lock, timeout, f"{spec.name} pid {os.getpid()} unit {unit}")
    avail = wait_for_memory(spec.need_gib, cfg.run_job.reserve_gib, timeout,
                            available or (lambda: available_gib()[0]), demo.on)
    cap = gpu_cap_gib(spec)
    print(f"[run_job] {unit}: need {spec.need_gib:g} GiB, MemAvailable {avail:.1f} GiB, host cap "
          f"{host_cap_gib(spec, cfg):g} GiB, GPU cap {f'{cap:g} GiB' if cap is not None else 'none (critical)'}"
          f"{', GPU lock held' if spec.gpu else ''}, priority {spec.priority}", flush=True)
    adj = cfg.run_job.oom_score_adj

    def child_setup():
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write(str(adj))
    proc = subprocess.Popen(argv, env=job_env(spec, dict(os.environ)), preexec_fn=child_setup,
                            pass_fds=(lock_fd,) if lock_fd is not None else ())
    reg.add(unit, name=spec.name, priority=spec.priority, pid=proc.pid, launcher_pid=os.getpid(),
            need_gib=spec.need_gib, gpu=spec.gpu,
            host_max_gib=host_cap_gib(spec, cfg), cmd=list(spec.cmd))

    def forward(sig, _frame):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass
    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, forward)
    try:
        rc = proc.wait()
    finally:
        reg.remove(unit)
        if lock_fd is not None:
            os.close(lock_fd)
    if rc < 0:
        print(f"[run_job] {unit} killed by signal {-rc}", file=sys.stderr)
    return rc if rc >= 0 else 128 - rc
