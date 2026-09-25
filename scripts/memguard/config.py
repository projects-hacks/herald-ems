"""Load and validate config/memguard.yaml into typed, frozen objects."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "memguard.yaml"
VICTIM_CLASSES = ("guarded_jobs", "user_processes", "vllm_services", "critical_jobs")
PRIORITIES = ("normal", "critical")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Thresholds:
    warn_below_gib: float
    kill_below_gib: float
    psi_full_avg10_kill: float


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern


@dataclass(frozen=True)
class Protected:
    ports: tuple[int, ...]
    port_descendants: bool
    vllm_keep: frozenset[str]
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class Paths:
    state_dir: Path
    status_file: Path
    log_file: Path
    demo_flag: Path
    jobs_dir: Path
    gpu_lock: Path


@dataclass(frozen=True)
class RunJob:
    reserve_gib: float
    wait_timeout_s: float
    host_margin_gib: float
    critical_coexist_gib: float
    oom_score_adj: int
    unit_prefix: str


@dataclass(frozen=True)
class Demo:
    thresholds: Thresholds
    kill_new_gpu_processes: bool
    gpu_min_mib: float


@dataclass(frozen=True)
class GuardConfig:
    thresholds: Thresholds
    poll_hz: float
    gpu_poll_s: float
    process_poll_s: float
    term_grace_s: float
    critical_term_grace_s: float
    critical_warn_log_every_s: float
    growth_window_s: float
    settle_s: float
    min_victim_gib: float
    warn_log_every_s: float
    zrt_stop_timeout_s: float
    demo: Demo
    paths: Paths
    run_job: RunJob
    protected: Protected
    victims: tuple[str, ...]

    def thresholds_for(self, demo: bool) -> Thresholds:
        return self.demo.thresholds if demo else self.thresholds


def _need(d: dict, key: str, where: str):
    if not isinstance(d, dict) or key not in d:
        raise ConfigError(f"memguard config: missing {where}{key}")
    return d[key]


def _positive(v, name: str) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ConfigError(f"memguard config: {name} must be a number, got {v!r}") from None
    if f <= 0:
        raise ConfigError(f"memguard config: {name} must be > 0, got {v!r}")
    return f


def _thresholds(d: dict, where: str) -> Thresholds:
    t = Thresholds(*(_positive(_need(d, k, where), where + k)
                     for k in ("warn_below_gib", "kill_below_gib", "psi_full_avg10_kill")))
    if t.kill_below_gib >= t.warn_below_gib:
        raise ConfigError(f"memguard config: {where}kill_below_gib must be below warn_below_gib")
    if t.psi_full_avg10_kill > 100:
        raise ConfigError(f"memguard config: {where}psi_full_avg10_kill is a percentage (0-100)")
    return t


def _path(v: str, home: Optional[Path]) -> Path:
    return Path(str(v).replace("~", str(home), 1)) if home and str(v).startswith("~") else Path(v).expanduser()


def parse(raw: dict, home: Optional[Path] = None) -> GuardConfig:
    """Build a GuardConfig from the YAML mapping; every missing or inconsistent value is a ConfigError."""
    g = lambda k: _need(raw, k, "")  # noqa: E731
    demo_raw, paths_raw, job_raw, prot_raw = g("demo"), g("paths"), g("run_job"), g("protected")
    rules = []
    for r in _need(prot_raw, "rules", "protected."):
        try:
            rules.append(Rule(str(_need(r, "name", "protected.rules[].")),
                              re.compile(_need(r, "cmdline", "protected.rules[]."))))
        except re.error as e:
            raise ConfigError(f"memguard config: bad regex in protected rule {r.get('name')}: {e}") from None
    victims = tuple(g("victims"))
    if not victims or any(v not in VICTIM_CLASSES for v in victims) or len(set(victims)) != len(victims):
        raise ConfigError(f"memguard config: victims must be distinct entries of {VICTIM_CLASSES}, got {victims}")
    ports = tuple(int(p) for p in _need(prot_raw, "ports", "protected."))
    if any(not 0 < p < 65536 for p in ports):
        raise ConfigError("memguard config: protected.ports must be TCP ports")
    prefix = str(_need(job_raw, "unit_prefix", "run_job."))
    if not re.fullmatch(r"[a-z][a-z0-9-]*-", prefix):
        raise ConfigError("memguard config: run_job.unit_prefix must look like 'herald-job-'")
    adj = int(_need(job_raw, "oom_score_adj", "run_job."))
    if not 0 <= adj <= 1000:
        raise ConfigError("memguard config: run_job.oom_score_adj must be 0..1000 (raising needs no privilege)")
    return GuardConfig(
        thresholds=_thresholds(g("thresholds"), "thresholds."),
        poll_hz=_positive(g("poll_hz"), "poll_hz"),
        gpu_poll_s=_positive(g("gpu_poll_s"), "gpu_poll_s"),
        process_poll_s=_positive(g("process_poll_s"), "process_poll_s"),
        term_grace_s=_positive(g("term_grace_s"), "term_grace_s"),
        critical_term_grace_s=_positive(g("critical_term_grace_s"), "critical_term_grace_s"),
        critical_warn_log_every_s=_positive(g("critical_warn_log_every_s"), "critical_warn_log_every_s"),
        growth_window_s=_positive(g("growth_window_s"), "growth_window_s"),
        settle_s=_positive(g("settle_s"), "settle_s"),
        min_victim_gib=float(g("min_victim_gib")),
        warn_log_every_s=_positive(g("warn_log_every_s"), "warn_log_every_s"),
        zrt_stop_timeout_s=_positive(g("zrt_stop_timeout_s"), "zrt_stop_timeout_s"),
        demo=Demo(thresholds=_thresholds(_need(demo_raw, "thresholds", "demo."), "demo.thresholds."),
                  kill_new_gpu_processes=bool(_need(demo_raw, "kill_new_gpu_processes", "demo.")),
                  gpu_min_mib=float(_need(demo_raw, "gpu_min_mib", "demo."))),
        paths=Paths(**{k: _path(_need(paths_raw, k, "paths."), home) for k in Paths.__dataclass_fields__}),
        run_job=RunJob(reserve_gib=float(_need(job_raw, "reserve_gib", "run_job.")),
                       wait_timeout_s=_positive(_need(job_raw, "wait_timeout_s", "run_job."), "wait_timeout_s"),
                       host_margin_gib=float(_need(job_raw, "host_margin_gib", "run_job.")),
                       critical_coexist_gib=float(_need(job_raw, "critical_coexist_gib", "run_job.")),
                       oom_score_adj=adj, unit_prefix=prefix),
        protected=Protected(ports=ports, port_descendants=bool(_need(prot_raw, "port_descendants", "protected.")),
                            vllm_keep=frozenset(str(x) for x in _need(prot_raw, "vllm_keep", "protected.")),
                            rules=tuple(rules)),
        victims=victims,
    )


def load(path: Optional[Path] = None, home: Optional[Path] = None) -> GuardConfig:
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p) as f:
        return parse(yaml.safe_load(f) or {}, home=home)
