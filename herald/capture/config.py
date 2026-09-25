"""Validated engineering policy from the reviewed capture configuration."""
from __future__ import annotations

import math
from copy import deepcopy

from ..config import load_yaml


def capture_config() -> dict:
    return validate_config(deepcopy(load_yaml("capture.yaml")))


def validate_config(c: dict) -> dict:
    positive = [c[k] for k in ("fps_in", "max_frame_bytes", "max_side", "buffer_s", "max_frames", "queue_size",
                               "decision_history", "poll_s", "manual_window_s", "manual_wait_s")]
    positive += [c["rate"]["auto_calls_per_s"], c["gate"]["width"], c["monitor"]["stable_frames"],
                 c["monitor"]["min_interval_s"], c["monitor"]["max_interval_s"]]
    if any(isinstance(n, bool) or not math.isfinite(n) or n <= 0 for n in positive):
        raise ValueError("capture limits must be finite and positive")
    if c["rate"]["max_in_flight"] != 1:
        raise ValueError("capture supports one in-flight request")
    g, m = c["gate"], c["monitor"]
    if not (0 <= g["bright_min"] < g["bright_max"] <= 255 and 0 <= g["change_min"] <= 1 and g["sharp_min"] >= 0):
        raise ValueError("invalid gate thresholds")
    if not (0 <= m["roi_margin"] <= 1 and m["max_interval_s"] >= m["min_interval_s"]):
        raise ValueError("invalid monitor policy")
    if c["privacy"]["store"] not in ("none", "used_only") or c["privacy"]["dir"] != "auto":
        raise ValueError("capture storage must be none or used_only in auto/")
    for rule in c["triggers"]:
        if rule["on"] not in ("fact", "alert_new", "eta_changed") or rule["purpose"] not in ("record", "verify"):
            raise ValueError("invalid capture trigger")
        if rule["mode"] not in c["record_keys"] or not 0 < rule["window_s"] < float("inf"):
            raise ValueError("invalid capture mode/window")
    return c
