"""Which alert checklists are open for this call, and what each one needs."""
from __future__ import annotations

from typing import Optional

from ..config import load_yaml
from ..config.county import CountyRegistry


class ChecklistEngine:
    def __init__(self, definitions: dict, counties: CountyRegistry):
        self.alerts = definitions["alerts"]
        self.default_unknowns = definitions["default_unknowns"]
        self.counties = counties

    @classmethod
    def from_config(cls, counties: CountyRegistry, rel: str = "checklists.yaml") -> "ChecklistEngine":
        return cls(load_yaml(rel), counties)

    def active(self, dispatch: Optional[str], complaint: Optional[str], stroke_exam_started: bool) -> list[str]:
        text = f" {(dispatch or '')} {(complaint or '')} ".lower()
        out = [aid for aid, a in self.alerts.items() if any(t in text for t in a["triggers"])]
        if stroke_exam_started and "stroke" not in out:
            out.append("stroke")
        return out

    def label(self, alert_id: str) -> str:
        return self.alerts[alert_id]["label"]

    def items(self, alert_id: str) -> list[tuple[str, str]]:
        """(key, label) pairs; the stroke checklist is the active county's."""
        rows = self.counties.active["stroke"]["checklist"] if alert_id == "stroke" else self.alerts[alert_id]["items"]
        return [(k, label) for k, label in rows]

    def unknowns(self, alert_id: str) -> list[str]:
        return list(self.alerts[alert_id]["unknowns"])
