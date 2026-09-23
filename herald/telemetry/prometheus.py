"""Minimal Prometheus text-format reader for the model server's /metrics endpoint."""
from __future__ import annotations

import re

_LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eE]+|NaN|\+Inf|-Inf)$")


def parse_prometheus(text: str) -> dict[str, float]:
    """Sum each metric over its label sets: {'vllm:generation_tokens_total': 35031.0, ...}."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line.strip())
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
