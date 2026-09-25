"""Telemetry in HP's terms: tokens, tokens/s, watts, energy, and dollars vs a cloud equivalent.

Measured: GPU power from `nvidia-smi` (sampled every second and integrated into energy; GB10 exposes GPU power
only, so energy is a floor), token counts from our own calls and from the model server's Prometheus counters,
and speech seconds transcribed. The cost assumptions are content with sources (config/telemetry.yaml),
overridable by environment, and always returned next to the numbers. Cloud AI calls made by Herald: 0.

E3: `track()` attributes energy to one inference request as power x that request's own elapsed time -- the
sampled power integrated over exactly the window that request was in flight (`energy_j`, read before and after),
not a share of the whole process's since-start total. `energy_wh` (below) stays the session total for context;
`snapshot()["requests"]` is the per-request, defensible number.
"""
from __future__ import annotations

import subprocess
import threading
import time
from collections import Counter, deque
from contextlib import contextmanager, nullcontext
from typing import Optional

import httpx

from ..config import load_yaml
from .prometheus import parse_prometheus


def tracking(usage, kind: str):
    """E3: attribute one inference call's GPU energy to itself, when `usage` is a real `Telemetry` (it has
    `track()`); any other `UsageRecorder` (a minimal test double, or none) just runs the call untracked."""
    track = getattr(usage, "track", None)
    return track(kind) if track else nullcontext()


def load_rates(overrides: Optional[dict] = None) -> tuple[dict[str, float], dict[str, str], str]:
    """(rates, their sources, energy scope) from config/telemetry.yaml, with environment overrides applied."""
    cfg = load_yaml("telemetry.yaml")
    rates = {k: float(v["value"]) for k, v in cfg["rates"].items()}
    rates.update(overrides or {})
    return rates, {k: v["source"] for k, v in cfg["rates"].items()}, cfg["energy_scope"]


class Telemetry:
    """The `UsageRecorder` interface plus GPU power sampling and a cost snapshot."""

    def __init__(self, metrics_url: str = "http://127.0.0.1:8080/metrics", rates: Optional[dict] = None) -> None:
        self.metrics_url = metrics_url
        self.rates, self.rate_sources, self.energy_scope = load_rates(rates)
        self.started = time.time()
        self.lock = threading.Lock()
        self.energy_j = 0.0
        self.power: deque = deque(maxlen=120)          # (t, watts)
        self.llm_calls = self.prompt_tokens = self.completion_tokens = 0
        self.vision_calls = 0
        self.stt_calls = 0
        self.stt_audio_s = 0.0
        self.stt_dropped: Counter = Counter()          # clips the speech gates dropped, by reason (stt_gates.py)
        self._gen_hist: deque = deque(maxlen=30)       # (t, generation_tokens_total) from the model server
        self._sampler: Optional[threading.Thread] = None
        self.util_now: Optional[float] = None
        self.request_energy: deque = deque(maxlen=200)  # E3: bounded per-request attribution log
        self.energy_j_attributed = 0.0                  # sum of `track()` deltas: the genuinely measured share

    # ---------- per-request attribution (E3) ----------
    @contextmanager
    def track(self, kind: str):
        """Wrap one inference call (`with telemetry.track("text"): ...`): the GPU energy sampled between entry
        and exit is this call's own, not a slice of the running total. A caller with no `Telemetry` (tests, a
        fake model) never needs this -- it is only reached through the real `LocalLLMClient` / `WhisperSTT`."""
        t0 = time.time()
        with self.lock:
            e0 = self.energy_j
        try:
            yield
        finally:
            dt = time.time() - t0
            with self.lock:
                de = max(0.0, self.energy_j - e0)
                self.energy_j_attributed += de
                self.request_energy.append({
                    "kind": kind, "duration_s": round(dt, 3), "energy_j": round(de, 4),
                    "energy_wh": round(de / 3600.0, 6),
                    "watts_avg": round(de / dt, 2) if dt > 0 else None,
                })

    # ---------- recording (called by llm.py / stt.py) ----------
    def record_llm(self, usage: dict, kind: str = "text") -> None:
        with self.lock:
            self.llm_calls += 1
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
            if kind == "vision":
                self.vision_calls += 1

    def record_stt(self, audio_seconds: float) -> None:
        with self.lock:
            self.stt_calls += 1
            self.stt_audio_s += float(audio_seconds)

    def record_stt_dropped(self, reason: str) -> None:
        """A clip the speech gates did not read (no speech, another language, a looping decode). Its audio still
        counts above: the encoder ran, and a cloud API would have billed it."""
        with self.lock:
            self.stt_dropped[reason] += 1

    # ---------- power sampling ----------
    def start(self) -> None:
        if self._sampler is None:
            self._sampler = threading.Thread(target=self._sample_power, daemon=True)
            self._sampler.start()

    def _sample_power(self) -> None:
        cmd = ["nvidia-smi", "--query-gpu=power.draw,utilization.gpu", "--format=csv,noheader,nounits", "-lms", "1000"]
        while True:
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
                last = None
                for line in p.stdout:  # type: ignore[union-attr]
                    try:
                        parts = [x.strip() for x in line.split(",")]
                        w = float(parts[0])
                        util = float(parts[1]) if len(parts) > 1 and parts[1] not in ("", "[N/A]") else None
                    except ValueError:
                        continue
                    now = time.time()
                    with self.lock:
                        if last is not None:
                            self.energy_j += w * (now - last)
                        self.power.append((now, w))
                        self.util_now = util
                    last = now
            except Exception:
                pass
            time.sleep(5)       # nvidia-smi exited; restart it

    # ---------- model server ----------
    def model_server(self, model: Optional[str]) -> dict:
        if not model:
            return {}
        try:
            m = parse_prometheus(httpx.get(f"{self.metrics_url}/{model}", timeout=2.0).text)
        except Exception:
            return {"error": "metrics unavailable"}
        gen = m.get("vllm:generation_tokens_total", 0.0)
        now = time.time()
        with self.lock:
            self._gen_hist.append((now, gen))
            window = [x for x in self._gen_hist if now - x[0] <= 30]
        rate = None
        if len(window) >= 2 and window[-1][0] > window[0][0]:
            rate = round((window[-1][1] - window[0][1]) / (window[-1][0] - window[0][0]), 1)
        n = m.get("vllm:e2e_request_latency_seconds_count", 0.0)
        return {
            "model": model,
            "prompt_tokens_total": int(m.get("vllm:prompt_tokens_total", 0)),
            "generation_tokens_total": int(gen),
            "requests_total": int(n),
            "mean_request_latency_s": round(m.get("vllm:e2e_request_latency_seconds_sum", 0.0) / n, 3) if n else None,
            "generation_tok_s_last_30s": rate,
            "running": int(m.get("vllm:num_requests_running", 0)),
        }

    # ---------- snapshot ----------
    def snapshot(self, model: Optional[str] = None, jobs: Optional[dict] = None) -> dict:
        """`jobs` names the model doing each job (extraction, photos, knowledge). It is reported only when a split
        stack is configured (TRAINING_PLAN §7a), so the single-model response is unchanged."""
        now = time.time()
        with self.lock:
            recent = [w for t, w in self.power if now - t <= 60]
            p_now = self.power[-1][1] if self.power else None
            energy_wh = self.energy_j / 3600.0
            pt, ct, stt_min = self.prompt_tokens, self.completion_tokens, self.stt_audio_s / 60.0
            calls = {"llm": self.llm_calls, "vision": self.vision_calls, "stt": self.stt_calls}
            stt_dropped = dict(self.stt_dropped)
            attributed_wh = self.energy_j_attributed / 3600.0
            recent_requests = list(self.request_energy)[-20:]
        r = self.rates
        local_usd = energy_wh / 1000.0 * r["electricity_usd_per_kwh"]
        cloud_llm = pt / 1e6 * r["cloud_llm_usd_per_1m_in"] + ct / 1e6 * r["cloud_llm_usd_per_1m_out"]
        cloud_stt = stt_min * r["cloud_stt_usd_per_min"]
        return {
            "since_s": round(now - self.started),
            "power_w_now": p_now,
            "power_w_avg_60s": round(sum(recent) / len(recent), 1) if recent else None,
            "gpu_util_pct": self.util_now,
            "memory_bandwidth": None,   # not exposed by nvidia-smi on GB10 unified memory (utilization.memory reads 0 under load)
            "energy_wh": round(energy_wh, 3),          # since this process started (a floor: docstring above)
            "requests": {                              # E3: energy attributed per request (power x its own time),
                "attributed_energy_wh": round(attributed_wh, 6),   # not a share of the since-start total
                "count": len(self.request_energy),
                "recent": recent_requests,
            },
            "tokens": {"prompt": pt, "completion": ct},
            "calls": calls,
            "stt_audio_min": round(stt_min, 2),
            "stt_dropped": stt_dropped,                # clips not read, by gate reason (herald/models/stt_gates.py)
            "cost": {
                "local_usd": round(local_usd, 5),
                "cloud_equivalent_usd": round(cloud_llm + cloud_stt, 5),
                "cloud_breakdown": {"llm_usd": round(cloud_llm, 5), "stt_usd": round(cloud_stt, 5)},
                "net_savings_usd": round(cloud_llm + cloud_stt - local_usd, 5),
            },
            "cloud_ai_calls": 0,
            "model_server": self.model_server(model),
            **({"jobs": jobs} if jobs else {}),
            "assumptions": {**r, "sources": self.rate_sources, "energy_scope": self.energy_scope},
        }

