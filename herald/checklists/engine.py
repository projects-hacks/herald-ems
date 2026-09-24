"""Which alert checklists are open for this call, and what each one needs.

Defaults come from config/checklists.yaml. The active county (config/counties/<id>.json) overrides any alert in its
`alerts` section, field by field, and replaces the stroke checklist's items with its `stroke.checklist`. A checklist
opens on words in the dispatch or chief complaint (`triggers`), on facts (`open_on.facts`: criteria rules over every
value, confirmed or not), or on a score that has any criterion hit (`open_on.scores`).
"""
from __future__ import annotations

from typing import Any, Optional

from ..config import load_yaml
from ..config.county import CountyRegistry
from ..scoring.rules import evaluate
from .items import ChecklistItem


class ChecklistEngine:
    def __init__(self, definitions: dict, counties: CountyRegistry):
        self.defaults: dict[str, dict] = definitions["alerts"]
        self.default_unknowns = definitions["default_unknowns"]
        self.counties = counties

    @classmethod
    def from_config(cls, counties: CountyRegistry, rel: str = "checklists.yaml") -> "ChecklistEngine":
        return cls(load_yaml(rel), counties)

    # ---------- definitions (the active county's, over the defaults) ----------
    @property
    def alerts(self) -> dict[str, dict]:
        county = self.counties.active
        overrides = county.get("alerts", {})
        out = {aid: {**d, **overrides.get(aid, {})} for aid, d in self.defaults.items()}
        out.update({aid: d for aid, d in overrides.items() if aid not in out})
        if "stroke" in out and "stroke" in county:
            out["stroke"] = {**out["stroke"], "items": county["stroke"]["checklist"]}
        return out

    def ids(self) -> list[str]:
        return list(self.alerts)

    def definition(self, alert_id: str) -> dict:
        return self.alerts[alert_id]

    def label(self, alert_id: str) -> str:
        return self.definition(alert_id)["label"]

    def source(self, alert_id: str) -> Optional[str]:
        return self.definition(alert_id).get("source")

    def items(self, alert_id: str) -> list[ChecklistItem]:
        return [ChecklistItem.parse(row) for row in self.definition(alert_id)["items"]]

    def unknowns(self, alert_id: str) -> list[str]:
        return list(self.definition(alert_id).get("unknowns", []))

    # ---------- which checklists are open ----------
    def active(self, dispatch: Optional[str], complaint: Optional[str], facts: dict[str, Any],
               scores: dict[str, dict]) -> list[str]:
        """`facts`: every value, confirmed or not (a checklist opens as soon as something is heard);
        `scores`: the scores computed from those values."""
        text = f" {(dispatch or '')} {(complaint or '')} ".lower()
        out = []
        for aid, d in self.alerts.items():
            on = d.get("open_on", {})
            if (any(t in text for t in d.get("triggers", []))
                    or any(evaluate(rule, facts).met for rule in on.get("facts", []))
                    or any((scores.get(sid) or {}).get("flagged") for sid in on.get("scores", []))):
                out.append(aid)
        return out

    # ---------- the county's rule for a met criteria score ----------
    def county_rules(self, score_id: str, values: dict[str, Any]) -> list[str]:
        """The active county's quoted rules for an alert whose score is met (e.g. Policy 602 destinations), each
        listed when its `when` rule is met (or it has none). Quoted, never paraphrased or chosen by a model."""
        out = []
        for d in self.alerts.values():
            if d.get("score") != score_id:
                continue
            for rule in d.get("county_rules", []):
                if "when" not in rule or evaluate(rule["when"], values).met:
                    out.append(rule["text"])
        return out
