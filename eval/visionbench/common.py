"""Shared pieces of the vision bench: a recording wrapper around the product's model client, latency statistics,
and the fingerprint of every input that must be identical across the models being compared."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Call:
    """One model call as the bench saw it."""
    ms: float
    usage: dict
    raw: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class RecordingModel:
    """The `TextModel` interface around the product's LocalLLMClient: delegates every call unchanged and keeps
    latency, token usage, and the parsed response, so product code (VisionReader, LLMReranker, the figure
    transcription) runs exactly as in the app while the bench can still see what the model returned."""
    inner: object
    calls: list[Call] = field(default_factory=list)

    def available(self) -> bool:
        return self.inner.available()

    def model_name(self):
        return self.inner.model_name()

    def chat_json(self, system: str, user: str, **kw) -> dict:
        usage: dict = {}
        t0 = time.perf_counter()
        try:
            out = self.inner.chat_json(system, user, usage=usage, **kw)
        except Exception as e:
            self.calls.append(Call((time.perf_counter() - t0) * 1000, usage, None, f"{type(e).__name__}: {str(e)[:200]}"))
            raise
        self.calls.append(Call((time.perf_counter() - t0) * 1000, usage, out))
        return out

    def last(self) -> Optional[Call]:
        return self.calls[-1] if self.calls else None


def is_json_error(err: Optional[str], raw: Optional[dict]) -> bool:
    """The model answered but not with a usable JSON object (unparseable, or only salvaged fragments)."""
    return bool(err and err.startswith("JSONDecodeError")) or bool(raw and raw.get("_salvaged"))


def latency(ms: list[float]) -> dict:
    if not ms:
        return {"latency_ms_p50": None, "latency_ms_p95": None, "first_call_ms": None}
    s = sorted(ms)                                   # p95 by nearest rank, so it is never below the median
    return {"first_call_ms": round(ms[0]), "latency_ms_p50": round(statistics.median(s)),
            "latency_ms_p95": round(s[math.ceil(0.95 * len(s)) - 1])}


def token_stats(calls: list[Call]) -> dict:
    p = [c.usage.get("prompt_tokens") for c in calls if c.usage.get("prompt_tokens") is not None]
    c = [c.usage.get("completion_tokens") for c in calls if c.usage.get("completion_tokens") is not None]
    return {"prompt_tokens_avg": round(statistics.mean(p), 1) if p else None,
            "out_tokens_avg": round(statistics.mean(c), 1) if c else None}


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "tp": tp, "fp": fp, "fn": fn}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


INPUTS = {
    "vision_prompt": "config/prompts/vision.yaml",
    "figure_prompt": "config/prompts/figure_transcribe.md",
    "rerank_prompt": "config/prompts/protocol_rerank.md",
    "lexicons": "config/lexicons.yaml",
    "photo_gold": "eval/photos/gold.jsonl",
    "flowchart_key": "eval/protocols/flowchart_700a13_key.json",
    "qa_gold": "eval/protocols/qa_gold.jsonl",
}


def fingerprint() -> dict:
    """Hashes of the prompts and test sets. Two runs are a level comparison only if these match."""
    return {k: sha(ROOT / rel) for k, rel in INPUTS.items() if (ROOT / rel).exists()}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
