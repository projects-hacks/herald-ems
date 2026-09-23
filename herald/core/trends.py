"""Significant-change rules for vital-sign trends (config/trends.yaml). A display and alert aid, not a diagnosis."""
from __future__ import annotations

from ..config import load_yaml


class TrendRules:
    def __init__(self, rules: dict[str, dict]):
        self.rules = rules

    @classmethod
    def from_config(cls, rel: str = "trends.yaml") -> "TrendRules":
        return cls(load_yaml(rel)["change_rules"])

    def keys(self) -> list[str]:
        return list(self.rules)

    def text(self, key: str) -> str:
        return self.rules[key]["text"]

    def significant(self, key: str, old: float, new: float) -> bool:
        r = self.rules[key]
        return any([
            "abs_change" in r and abs(new - old) >= r["abs_change"],
            "falls_by" in r and (old - new) >= r["falls_by"],
            "falls_to_or_below" in r and old > r["falls_to_or_below"] >= new,
            "falls_below" in r and old >= r["falls_below"] > new,
        ])
