"""Telemetry in HP's terms: tokens, tokens/s, watts, energy, and dollars vs a cloud equivalent.

Measured: GPU power from `nvidia-smi` (sampled every second and integrated into energy; GB10 exposes GPU power
only, so energy is a floor), token counts from our own calls and from the model server's Prometheus counters,
and speech seconds transcribed. The cost assumptions are content with sources (config/telemetry.yaml),
overridable by environment, and always returned next to the numbers. Cloud AI calls made by Herald: 0.
"""
from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from typing import Optional

import httpx

from ..config import load_yaml
from .prometheus import parse_prometheus


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
        self._gen_hist: deque = deque(maxlen=30)       # (t, generation_tokens_total) from the model server
        self._sampler: Optional[threading.Thread] = None
        self.util_now: Optional[float] = None

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
    def snapshot(self, model: Optional[str] = None) -> dict:
        now = time.time()
        with self.lock:
            recent = [w for t, w in self.power if now - t <= 60]
            p_now = self.power[-1][1] if self.power else None
            energy_wh = self.energy_j / 3600.0
            pt, ct, stt_min = self.prompt_tokens, self.completion_tokens, self.stt_audio_s / 60.0
            calls = {"llm": self.llm_calls, "vision": self.vision_calls, "stt": self.stt_calls}
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
            "energy_wh": round(energy_wh, 3),
            "tokens": {"prompt": pt, "completion": ct},
            "calls": calls,
            "stt_audio_min": round(stt_min, 2),
            "cost": {
                "local_usd": round(local_usd, 5),
                "cloud_equivalent_usd": round(cloud_llm + cloud_stt, 5),
                "cloud_breakdown": {"llm_usd": round(cloud_llm, 5), "stt_usd": round(cloud_stt, 5)},
                "net_savings_usd": round(cloud_llm + cloud_stt - local_usd, 5),
            },
            "cloud_ai_calls": 0,
            "model_server": self.model_server(model),
            "assumptions": {**r, "sources": self.rate_sources, "energy_scope": self.energy_scope},
        }

