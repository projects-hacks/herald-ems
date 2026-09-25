"""Significant-change rules for vital-sign trends (config/trends.yaml). A display and alert aid, not a diagnosis.

This module also owns which facts a trend point may come from. Confirmed facts always count; an unconfirmed reading
counts when its source is listed in `unconfirmed_sources`, which is how a camera read of the patient monitor becomes
a trend point before anybody taps. Such a point is labelled, and the relay and the handoff report are unaffected:
both ask the incident for confirmed facts only.
"""
from __future__ import annotations

from typing import Any, Optional

from ..config import load_yaml


class TrendRules:
    def __init__(self, rules: dict[str, dict], unconfirmed_sources=(), text: Optional[dict] = None,
                 directions: Optional[dict] = None):
        self.rules = rules
        self.unconfirmed_sources = frozenset(unconfirmed_sources)
        self.unconfirmed_text = dict(text or {})
        self.directions = dict(directions or {})

    @classmethod
    def from_config(cls, rel: str = "trends.yaml") -> "TrendRules":
        c = load_yaml(rel)
        return cls(c["change_rules"], c.get("unconfirmed_sources") or (),
                   c.get("unconfirmed_text"), c.get("directions"))

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

    # ---------- which readings count as a trend point ----------
    def counts_unconfirmed(self, captured_by: str) -> bool:
        return captured_by in self.unconfirmed_sources

    def sentence(self, captured_by: str, *, label: str, value: Any, previous: Any, direction: str,
                 delta: Any, unit: Optional[str] = None) -> Optional[str]:
        """The configured wording for an unconfirmed reading, or None when that source has no wording."""
        template = self.unconfirmed_text.get(captured_by)
        if not template:
            return None
        return template.format(label=label, value=value, previous=previous, delta=delta, unit=f" {unit}" if unit else "",
                               direction=self.directions.get(direction, direction))
