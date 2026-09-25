"""Carry out a kill decision: SIGTERM a victim group, wait the grace period, SIGKILL what is left; or stop a vLLM
service through ZRT (never kill -9 a model server). One victim at a time; PIDs are held as pidfds so a recycled PID
is never signalled."""
from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from .policy import Victim
from .probe import cgroup_procs, read_proc


_libc = ctypes.CDLL(None, use_errno=True)
_SYS_PIDFD_OPEN, _SYS_PIDFD_SEND_SIGNAL = 434, 424       # same numbers on x86_64 and aarch64


def pidfd_open(pid: int) -> int:
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid)
    fd = _libc.syscall(_SYS_PIDFD_OPEN, ctypes.c_int(pid), ctypes.c_uint(0))
    if fd < 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))
    return fd


def pidfd_send_signal(fd: int, sig: int) -> None:
    if hasattr(signal, "pidfd_send_signal"):
        return pidfd_send_signal(fd, sig)
    if _libc.syscall(_SYS_PIDFD_SEND_SIGNAL, ctypes.c_int(fd), ctypes.c_int(int(sig)), None, ctypes.c_uint(0)) < 0:
        e = ctypes.get_errno()
        raise (ProcessLookupError if e == 3 else OSError)(e, os.strerror(e))


def _alive(pid: int) -> bool:
    """Running and not a zombie (a zombie holds no memory)."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat = f.read()
        return stat[stat.rindex(")") + 2] != "Z"
    except (OSError, ValueError, IndexError):
        return False


class Terminator:
    def __init__(self, grace_s: float, zrt_timeout_s: float, log: Callable[..., None],
                 cgroup_root: str = "/sys/fs/cgroup", critical_grace_s: Optional[float] = None):
        self.grace_s, self.zrt_timeout_s, self.log, self.cgroup_root = grace_s, zrt_timeout_s, log, cgroup_root
        self.critical_grace_s = critical_grace_s if critical_grace_s is not None else grace_s
        self.victim: Optional[Victim] = None
        self._fds: dict[int, int] = {}
        self._deadline = 0.0
        self._killed = False
        self._zrt: Optional[subprocess.Popen] = None
        self._started = 0.0

    @property
    def busy(self) -> bool:
        return self.victim is not None

    def _open(self, pids, starts: dict[int, float]):
        for pid in pids:
            try:
                fd = pidfd_open(pid)
            except OSError:
                continue
            p = read_proc(pid)                          # same process as the one we classified?
            if p is None or (pid in starts and abs(p.start_epoch - starts[pid]) > 1.0):
                os.close(fd)
                continue
            self._fds[pid] = fd

    def _signal_all(self, sig) -> int:
        n = 0
        for pid, fd in list(self._fds.items()):
            try:
                pidfd_send_signal(fd, sig)
                n += 1
            except ProcessLookupError:
                pass
            except OSError as e:
                self.log("error", msg=f"signal {sig} to {pid} failed: {e}")
        return n

    def start(self, victim: Victim, now: float, starts: dict[int, float], reason: str) -> None:
        self.victim, self._started, self._killed = victim, now, False
        self._deadline = now + self.grace_s
        if victim.klass == "vllm_services":
            self._deadline = now + self.zrt_timeout_s
            self._open([victim.root], starts)
            cmd = ["sg", "zrt", "-c", f"zrt service stop {victim.service}"]
            self.log("kill", victim=victim.brief(), reason=reason, method="zrt service stop", cmd=" ".join(cmd))
            try:
                self._zrt = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as e:
                self.log("error", msg=f"zrt stop failed to start: {e}; SIGTERM to the vllm root")
                self._signal_all(signal.SIGTERM)
            return
        if victim.klass == "critical_jobs":              # last resort: say so loudly, give it time to save
            self._deadline = now + self.critical_grace_s
            self.log("critical_kill", victim=victim.brief(), reason=reason, grace_s=self.critical_grace_s,
                     msg=f"LAST RESORT: terminating CRITICAL job {victim.label}: nothing else left to free; SIGTERM "
                         f"now, SIGKILL in {self.critical_grace_s:g} s")
        pids = list(victim.pids)
        if victim.cgroup:                                # the whole scope, including anything forked since
            pids = sorted(set(pids) | set(cgroup_procs(victim.cgroup, self.cgroup_root)))
        self._open(pids, starts)
        n = self._signal_all(signal.SIGTERM)
        self.log("kill", victim=victim.brief(), reason=reason, method="SIGTERM", signalled=n)

    def poll(self, now: float) -> Optional[str]:
        """Advance the current kill; returns 'gone' once every victim process has exited, else None."""
        if self.victim is None:
            return None
        v = self.victim
        live = [pid for pid in self._fds if _alive(pid)]
        if v.klass == "vllm_services" and self._zrt is not None and self._zrt.poll() is None and now < self._deadline:
            return None
        if not live:
            self.log("victim_gone", victim=v.brief(), seconds=round(now - self._started, 2))
            self._reset()
            return "gone"
        if now >= self._deadline and not self._killed:
            self._killed = True
            if v.klass == "vllm_services":               # ZRT did not stop it in time: ask vLLM to shut down
                self.log("escalate", victim=v.brief(), method="SIGTERM vllm root")
                self._signal_all(signal.SIGTERM)
                self._deadline = now + self.zrt_timeout_s
                self._killed = False
                self._zrt = None
                return None
            if v.cgroup:
                kill = Path(self.cgroup_root, v.cgroup.lstrip("/"), "cgroup.kill")
                try:
                    kill.write_text("1")
                except OSError:
                    pass
            n = self._signal_all(signal.SIGKILL)
            self.log("sigkill", victim=v.brief(), signalled=n)
        elif now >= self._deadline + 10 * self.grace_s:  # unkillable (D state?): give up on it, pick another
            self.log("error", msg="victim did not exit after SIGKILL", victim=v.brief())
            self._reset()
            return "stuck"
        return None

    def _reset(self):
        for fd in self._fds.values():
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds, self.victim, self._zrt = {}, None, None


def wait_gone(term: Terminator, timeout_s: float, tick_s: float = 0.1) -> Optional[str]:
    """Block until the current kill finishes (used by `memguard.py once --kill` and tests)."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        r = term.poll(time.monotonic())
        if r:
            return r
        time.sleep(tick_s)
    return None
