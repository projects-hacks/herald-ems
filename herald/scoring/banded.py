"""Scores built from per-parameter point bands plus total risk bands (NEWS2)."""
from __future__ import annotations

from typing import Any, Optional


class BandedScore:
    def __init__(self, definition: dict):
        self.d = definition
        self.id, self.name = definition["id"], definition["name"]
        self.county: Optional[str] = definition.get("county")
        self.parameters = definition["parameters"]

    def input_keys(self) -> set[str]:
        """Every vocabulary key the score reads."""
        return {p["key"] for p in self.parameters}

    def parameter(self, key: str) -> dict:
        return next(p for p in self.parameters if p["key"] == key)

    def points(self, key: str, value: Any) -> int:
        p = self.parameter(key)
        if "boolean" in p:
            return p["boolean"][bool(value)]
        if "levels" in p:
            level = str(value).strip().upper()[:1]
            return p["levels"][level]
        for upper, pts in p["bands"]:
            if value <= upper:
                return pts
        return p["above"]

    def evaluate(self, values: dict[str, Any]) -> dict:
        parts, missing = {}, []
        for p in self.parameters:
            v = values.get(p["key"])
            if v is None:
                missing.append(p["label"])
            else:
                parts[p["label"]] = {"value": v, "points": self.points(p["key"], v)}
        total = sum(x["points"] for x in parts.values())
        top = max((x["points"] for x in parts.values()), default=0)
        complete = not missing
        band = "incomplete"
        if complete:
            for rb in self.d["risk_bands"]:
                if ("total_at_least" in rb and total >= rb["total_at_least"]) or \
                        ("any_single" in rb and top >= rb["any_single"]):
                    band = rb["band"]
                    break
        return {"name": self.name, "score": total, "complete": complete, "band": band,
                "any_single_3": top >= 3, "parts": parts, "missing": missing,
                "thresholds": self.d["thresholds_text"], "source": self.d["source"], "evidence": self.d["evidence"]}

    def relay_text(self, result: dict) -> Optional[str]:
        """The line the relay sends once the score is complete (definition `relay_text`, e.g. "{score} {band}")."""
        fmt = self.d.get("relay_text")
        return fmt.format(score=result["score"], band=result["band"]) if fmt and result["complete"] else None
