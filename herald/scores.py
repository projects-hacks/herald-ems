"""Published, validated clinical scores computed by plain code.

These are calculators, not predictions. Every function returns the score,
each parameter's points, the inputs used, what is missing, the published
threshold crossed, and the source. Nothing here is trained by us, and
nothing here recommends treatment.
"""
from __future__ import annotations

from typing import Any, Optional

NEWS2_SOURCE = "Royal College of Physicians, National Early Warning Score 2 (2017)"
NEWS2_EVIDENCE = ("Pooled across 30 studies / 185,835 patients: AUC 0.88 for 2-day mortality "
                  "(sens 0.81, spec 0.81), prehospital and ED combined")
RACE_SOURCE = "Pérez de la Ossa et al., Stroke 2014 (RACE scale)"
RACE_EVIDENCE = "RACE >= 5: sensitivity 0.85, specificity 0.68 for large-vessel occlusion"
TRIAGE_SOURCE = "National Guideline for the Field Triage of Injured Patients (2021)"


def _band(value: float, bands: list[tuple[float, int]], top: int) -> int:
    """bands: ascending list of (inclusive upper bound, points); `top` if above all."""
    for upper, pts in bands:
        if value <= upper:
            return pts
    return top


def news2_rr(rr: float) -> int:        # <=8:3, 9-11:1, 12-20:0, 21-24:2, >=25:3
    return _band(rr, [(8, 3), (11, 1), (20, 0), (24, 2)], 3)


def news2_spo2_scale1(spo2: float) -> int:  # <=91:3, 92-93:2, 94-95:1, >=96:0
    return _band(spo2, [(91, 3), (93, 2), (95, 1)], 0)


def news2_oxygen(on_oxygen: bool) -> int:
    return 2 if on_oxygen else 0


def news2_sbp(sbp: float) -> int:      # <=90:3, 91-100:2, 101-110:1, 111-219:0, >=220:3
    return _band(sbp, [(90, 3), (100, 2), (110, 1), (219, 0)], 3)


def news2_hr(hr: float) -> int:        # <=40:3, 41-50:1, 51-90:0, 91-110:1, 111-130:2, >=131:3
    return _band(hr, [(40, 3), (50, 1), (90, 0), (110, 1), (130, 2)], 3)


def news2_consciousness(acvpu: str) -> int:  # Alert:0; new Confusion/Voice/Pain/Unresponsive: 3
    return 0 if acvpu.strip().upper().startswith("A") else 3


def news2_temp(t: float) -> int:       # <=35.0:3, 35.1-36.0:1, 36.1-38.0:0, 38.1-39.0:1, >=39.1:2
    return _band(t, [(35.0, 3), (36.0, 1), (38.0, 0), (39.0, 1)], 2)


NEWS2_PARAMS = [
    ("vitals.rr", "Respiratory rate", news2_rr),
    ("vitals.spo2", "SpO2 (scale 1)", news2_spo2_scale1),
    ("vitals.on_oxygen", "Air or oxygen", news2_oxygen),
    ("vitals.sbp", "Systolic BP", news2_sbp),
    ("vitals.hr", "Pulse", news2_hr),
    ("vitals.consciousness", "Consciousness", news2_consciousness),
    ("vitals.temp", "Temperature", news2_temp),
]


def news2(values: dict[str, Any]) -> dict:
    """values: canonical key -> value (confirmed facts only)."""
    parts, missing = {}, []
    for key, label, fn in NEWS2_PARAMS:
        v = values.get(key)
        if v is None:
            missing.append(label)
        else:
            parts[label] = {"value": v, "points": fn(v)}
    total = sum(p["points"] for p in parts.values())
    any3 = any(p["points"] == 3 for p in parts.values())
    complete = not missing
    if not complete:
        band = "incomplete"
    elif total >= 7:
        band = "high"
    elif total >= 5:
        band = "medium"
    elif any3:
        band = "low-medium"
    else:
        band = "low"
    return {
        "name": "NEWS2", "score": total, "complete": complete, "band": band,
        "any_single_3": any3, "parts": parts, "missing": missing,
        "thresholds": "single parameter 3 = low-medium; 5-6 = medium; >=7 = high",
        "source": NEWS2_SOURCE, "evidence": NEWS2_EVIDENCE,
    }


RACE_ITEMS = [
    ("exam.race.facial", "Facial palsy", 2),
    ("exam.race.arm", "Arm motor", 2),
    ("exam.race.leg", "Leg motor", 2),
    ("exam.race.gaze", "Head and gaze deviation", 1),
    ("exam.race.aphasia_agnosia", "Aphasia or agnosia", 2),
]


def race(values: dict[str, Any]) -> dict:
    parts, missing = {}, []
    for key, label, mx in RACE_ITEMS:
        v = values.get(key)
        if v is None:
            missing.append(label)
        else:
            v = max(0, min(int(v), mx))
            parts[label] = {"value": v, "points": v, "max": mx}
    total = sum(p["points"] for p in parts.values())
    complete = not missing
    positive: Optional[bool] = (total >= 5) if complete else None
    return {
        "name": "RACE", "score": total, "complete": complete, "positive": positive,
        "parts": parts, "missing": missing, "thresholds": ">= 5 = large-vessel occlusion screen positive",
        "source": RACE_SOURCE, "evidence": RACE_EVIDENCE,
    }


def field_triage(values: dict[str, Any]) -> dict:
    """2021 national field-triage guideline: vital-sign RED criteria + anticoagulant YELLOW."""
    red, yellow, missing = [], [], []
    age = values.get("patient.age")
    sbp, hr = values.get("vitals.sbp"), values.get("vitals.hr")
    rr, spo2 = values.get("vitals.rr"), values.get("vitals.spo2")
    on_o2, gcs_m = values.get("vitals.on_oxygen"), values.get("vitals.gcs_motor")
    if gcs_m is not None and gcs_m < 6:
        red.append("Unable to follow commands (motor GCS < 6)")
    if rr is not None and (rr < 10 or rr > 29):
        red.append(f"RR {rr} (< 10 or > 29)")
    if spo2 is not None and on_o2 is False and spo2 < 90:
        red.append(f"Room-air SpO2 {spo2}% (< 90%)")
    if age is None:
        missing.append("Age")
    if sbp is None:
        missing.append("Systolic BP")
    if age is not None and sbp is not None:
        if age <= 9 and sbp < 70 + 2 * age:
            red.append(f"SBP {sbp} < 70 + 2×age ({70 + 2 * age})")
        elif 10 <= age <= 64 and sbp < 90:
            red.append(f"SBP {sbp} < 90")
        elif age >= 65 and sbp < 110:
            red.append(f"SBP {sbp} < 110 (age ≥ 65)")
        if age >= 10 and hr is not None and hr > sbp:
            red.append(f"HR {hr} > SBP {sbp}")
    ac = values.get("meds.anticoagulant")
    if ac and str(ac).lower() not in ("none", "no", "false"):
        yellow.append(f"Anticoagulant use ({ac})")
    return {"name": "Field triage (2021)", "red": red, "yellow": yellow,
            "missing": missing, "source": TRIAGE_SOURCE}
