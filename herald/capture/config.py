"""Validated engineering policy from the reviewed capture configuration."""
from __future__ import annotations

import math
from copy import deepcopy

from ..config import load_yaml

GATE_THRESHOLDS = ("sharp_min", "change_min", "bright_min", "bright_max", "width", "stable_max")


def capture_config() -> dict:
    return validate_config(deepcopy(load_yaml("capture.yaml")))


def monitor_gate_config(c: dict) -> dict:
    """The monitor-watch gate profile: the global gate with the `monitor.gate` overrides applied.

    Monitor-watch assesses a small ROI on a screen; the global profile assesses a whole new photo. They are separate
    profiles on purpose, so widening one cannot regress the other (config/capture.yaml carries the measurements).
    """
    return {**c["gate"], **(c["monitor"].get("gate") or {})}


def _positive(n) -> bool:
    return isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and n > 0


def _check_gate(g: dict, what: str) -> None:
    if not (0 <= g["bright_min"] < g["bright_max"] <= 255 and 0 <= g["change_min"] <= 1 and g["sharp_min"] >= 0
            and 0 <= g.get("stable_max", 0) <= 1 and g["width"] > 0):
        raise ValueError(f"invalid {what} gate thresholds")


def validate_config(c: dict) -> dict:
    positive = [c[k] for k in ("fps_in", "max_frame_bytes", "max_side", "buffer_s", "max_frames", "queue_size",
                               "decision_history", "poll_s", "manual_window_s", "manual_wait_s")]
    positive += [c["rate"]["auto_calls_per_s"], c["gate"]["width"], c["monitor"]["stable_frames"],
                 c["monitor"]["min_interval_s"], c["monitor"]["max_interval_s"]]
    if any(isinstance(n, bool) or not math.isfinite(n) or n <= 0 for n in positive):
        raise ValueError("capture limits must be finite and positive")
    if c["rate"]["max_in_flight"] != 1:
        raise ValueError("capture supports one in-flight request")
    m = c["monitor"]
    if unknown := set(m.get("gate") or {}) - set(GATE_THRESHOLDS):
        raise ValueError(f"monitor.gate may only override gate thresholds, not {sorted(unknown)}")
    _check_gate(c["gate"], "global")
    _check_gate(monitor_gate_config(c), "monitor-watch")
    if not (0 <= m["roi_margin"] <= 1 and m["max_interval_s"] >= m["min_interval_s"]):
        raise ValueError("invalid monitor policy")
    if not (_positive(m["speech_interval_s"]) and _positive(m["speech_quiet_s"])
            and m["speech_interval_s"] >= m["min_interval_s"]):
        raise ValueError("monitor.speech_interval_s and speech_quiet_s must be positive, and a back-off never reads "
                         "more often than min_interval_s")
    jump = m["jump"]
    if not _positive(jump["window_s"]) or not jump["max_step"] or not all(_positive(v) for v in jump["max_step"].values()):
        raise ValueError("monitor.jump needs a positive window_s and a positive max_step per key")
    try:
        jump["reason"].format(label="", value=0, previous=0, delta=0, seconds=0, limit=0)
    except (KeyError, IndexError, AttributeError) as e:
        raise ValueError(f"monitor.jump.reason has an unknown field: {e}") from None
    if c["privacy"]["store"] not in ("none", "used_only") or c["privacy"]["dir"] != "auto":
        raise ValueError("capture storage must be none or used_only in auto/")
    for rule in c["triggers"]:
        if rule["on"] not in ("fact", "alert_new", "eta_changed") or rule["purpose"] not in ("record", "verify"):
            raise ValueError("invalid capture trigger")
        if rule["mode"] not in c["record_keys"] or not 0 < rule["window_s"] < float("inf"):
            raise ValueError("invalid capture mode/window")
    return c
