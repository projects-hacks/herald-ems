"""Scales that sum exam items with a positive threshold (RACE, G.F.A.S.T.)."""
from __future__ import annotations

from typing import Any


class ItemSumScale:
    def __init__(self, definition: dict):
        self.d = definition
        self.id, self.name = definition["id"], definition["name"]
        self.items = definition["items"]
        self.alert_type = definition.get("alert_type")

    @property
    def key_prefix(self) -> str:
        return self.items[0]["key"].rsplit(".", 1)[0] + "."

    def evaluate(self, values: dict[str, Any]) -> dict:
        parts, missing = {}, []
        for it in self.items:
            v = values.get(it["key"])
            if v is None:
                missing.append(it["label"])
            else:
                v = max(0, min(int(v), it["max"]))
                parts[it["label"]] = {"value": v, "points": v, "max": it["max"]}
        total = sum(p["points"] for p in parts.values())
        complete = not missing
        return {"name": self.name, "score": total, "complete": complete,
                "positive": (total >= self.d["positive_at_least"]) if complete else None,
                "parts": parts, "missing": missing, "thresholds": self.d["thresholds_text"],
                "source": self.d["source"], "evidence": self.d["evidence"]}
