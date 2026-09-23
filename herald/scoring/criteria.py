"""Guideline criteria lists (2021 field triage). Each criterion `type` is one small, tested rule."""
from __future__ import annotations

from typing import Any, Callable, Optional

Rule = Callable[[dict, dict[str, Any]], Optional[str]]


def _below(c, v):
    x = v.get(c["key"])
    return c["text"].format(value=x) if x is not None and x < c["value"] else None


def _outside(c, v):
    x = v.get(c["key"])
    return c["text"].format(value=x) if x is not None and (x < c["low"] or x > c["high"]) else None


def _room_air_below(c, v):
    x = v.get(c["key"])
    return c["text"].format(value=x) if x is not None and v.get("vitals.on_oxygen") is False and x < c["value"] else None


def _sbp_by_age(c, v):
    age, sbp = v.get("patient.age"), v.get("vitals.sbp")
    if age is None or sbp is None:
        return None
    for b in c["bands"]:
        if b.get("age_min", 0) <= age <= b.get("age_max", 200):
            limit = b["sbp_below"] if "sbp_below" in b else b["sbp_below_base"] + b["sbp_below_per_year"] * age
            return b["text"].format(sbp=sbp, limit=limit) if sbp < limit else None
    return None


def _hr_above_sbp(c, v):
    age, sbp, hr = v.get("patient.age"), v.get("vitals.sbp"), v.get("vitals.hr")
    if None in (age, sbp, hr) or age < c["min_age"]:
        return None
    return c["text"].format(hr=hr, sbp=sbp) if hr > sbp else None


def _anticoagulant(c, v):
    x = v.get(c["key"])
    return c["text"].format(value=x) if x and str(x).lower() not in ("none", "no", "false") else None


RULES: dict[str, Rule] = {"below": _below, "outside": _outside, "room_air_below": _room_air_below,
                          "sbp_by_age": _sbp_by_age, "hr_above_sbp": _hr_above_sbp, "anticoagulant": _anticoagulant}


class CriteriaScore:
    def __init__(self, definition: dict):
        self.d = definition
        self.id, self.name = definition["id"], definition["name"]

    def evaluate(self, values: dict[str, Any]) -> dict:
        def run(group):
            return [t for c in self.d.get(group, []) if (t := RULES[c["type"]](c, values))]
        missing = [r["label"] for r in self.d.get("required_for_display", []) if values.get(r["key"]) is None]
        return {"name": self.name, "red": run("red"), "yellow": run("yellow"), "missing": missing,
                "source": self.d["source"]}
