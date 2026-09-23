"""Telemetry in HP's terms: tokens, tokens/s, watts, energy, and dollars vs a cloud equivalent.

Measured:
- GPU power from `nvidia-smi` (sampled every second and integrated into energy). The GB10 reports
  GPU power only; whole-module power reads N/A on this box, so energy here is GPU energy (a floor).
- Token counts from our own calls (usage returned by the local model) and from the model server's
  Prometheus counters (ZRT: GET http://127.0.0.1:8080/metrics/<model>).
- Speech seconds transcribed and photos read by Herald.

Stated assumptions (override with env vars; always shown next to the numbers):
- Electricity: $0.15/kWh (the rate HP's ZGX console uses).
- Cloud LLM equivalent: $0.30 per 1M input tokens, $2.50 per 1M output tokens
  (Gemini 2.5 Flash list price: https://ai.google.dev/gemini-api/docs/pricing ; verify before the deck).
- Cloud speech-to-text equivalent: $0.006 per audio minute (OpenAI Whisper API list price; verify).
Cloud AI calls made by Herald: 0 (all inference is local; the LLM base URL is checked to be on this box).
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections import deque
from typing import Optional

import httpx

PRICE_KWH = float(os.getenv("HERALD_PRICE_KWH", "0.15"))
PRICE_IN_PER_M = float(os.getenv("HERALD_CLOUD_IN_PER_M", "0.30"))
PRICE_OUT_PER_M = float(os.getenv("HERALD_CLOUD_OUT_PER_M", "2.50"))
PRICE_STT_PER_MIN = float(os.getenv("HERALD_CLOUD_STT_PER_MIN", "0.006"))
ZRT_METRICS = os.getenv("HERALD_ZRT_METRICS", "http://127.0.0.1:8080/metrics")


def parse_prometheus(text: str) -> dict[str, float]:
    """Sum each metric over its label sets: {'vllm:generation_tokens_total': 35031.0, ...}."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eE]+|NaN|\+Inf|-Inf)$", line.strip())
        if not m:
            continue
        try:
            v = float(m.group(3))
        except ValueError:
            continue
        if v != v:  # NaN
            continue
        out[m.group(1)] = out.get(m.group(1), 0.0) + v
    return out


class Telemetry:
    def __init__(self) -> None:
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
            m = parse_prometheus(httpx.get(f"{ZRT_METRICS}/{model}", timeout=2.0).text)
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
        local_usd = energy_wh / 1000.0 * PRICE_KWH
        cloud_llm = pt / 1e6 * PRICE_IN_PER_M + ct / 1e6 * PRICE_OUT_PER_M
        cloud_stt = stt_min * PRICE_STT_PER_MIN
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
            "assumptions": {
                "electricity_usd_per_kwh": PRICE_KWH,
                "cloud_llm_usd_per_1m_in": PRICE_IN_PER_M, "cloud_llm_usd_per_1m_out": PRICE_OUT_PER_M,
                "cloud_stt_usd_per_min": PRICE_STT_PER_MIN,
                "energy_scope": "GPU power from nvidia-smi (whole-module power is not exposed on GB10): a floor",
            },
        }


TELEMETRY = Telemetry()
