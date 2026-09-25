"""Readings to show: coherent vital-sign profiles (content/vitals.yaml) and the unit formats a display prints.

A reading's canonical value is what the target carries (°C to one decimal, glucose in mg/dL as an integer); the
display may print °F or mmol/L, and the target is the conversion the prompt asks for."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random

import yaml

CONTENT = Path(__file__).resolve().parent / "content"
_CFG = yaml.safe_load((CONTENT / "vitals.yaml").read_text())
PROFILES = _CFG["profiles"]
MMOL = float(_CFG["mmol_to_mgdl"])


@dataclass
class Vitals:
    hr: int
    spo2: int
    sbp: int
    dbp: int
    rr: int
    temp_c: float
    glucose: int
    etco2: int
    profile: str


def sample(rng: Random, profile: str | None = None) -> Vitals:
    names = list(PROFILES)
    if profile is None:
        profile = rng.choices(names, weights=[PROFILES[n]["weight"] for n in names])[0]
    p = PROFILES[profile]
    ri = lambda k: rng.randint(*p[k])
    sbp = ri("sbp")
    dbp = min(ri("dbp"), sbp - _CFG["min_pulse_pressure"])
    return Vitals(hr=ri("hr"), spo2=ri("spo2"), sbp=sbp, dbp=dbp, rr=ri("rr"),
                  temp_c=round(rng.uniform(*p["temp"]), 1), glucose=ri("glucose"), etco2=ri("etco2"), profile=profile)


def c_to_f(c: float) -> float:
    return round(c * 9 / 5 + 32, 1)


def f_to_c(f: float) -> float:
    return round((f - 32) * 5 / 9, 1)


def temp_display(rng: Random, temp_c: float, fahrenheit: bool) -> tuple[str, float]:
    """(printed number, canonical °C). A °F display prints its own one-decimal number; the target converts it."""
    if fahrenheit:
        f = c_to_f(temp_c + rng.uniform(-0.04, 0.04))
        return f"{f:.1f}", f_to_c(f)
    return f"{temp_c:.1f}", temp_c


def glucose_display(rng: Random, mgdl: int, mmol: bool) -> tuple[str, int]:
    """(printed number, canonical mg/dL)."""
    if mmol:
        v = round(mgdl / MMOL, 1)
        return f"{v:.1f}", int(round(v * MMOL))
    return str(mgdl), mgdl
