"""The UI contract as plain data: labels, units, relay tiers, change rules, checklists, county.

Served at GET /api/meta and exported to ui/public/contract/ by scripts/export_ui_contract.py; the screens use
it to name keys that are no longer in the snapshot. tests/test_contract.py keeps it in step.
"""
from __future__ import annotations

from ..core.schema import CapturedBy, Role, Status


class UIContract:
    def __init__(self, vocabulary, tiers, trends, checklists, counties):
        self.vocab, self.tiers, self.trends, self.checklists, self.counties = vocabulary, tiers, trends, checklists, counties

    def keys(self) -> dict:
        return {k: {**v, **({"range": list(v["range"])} if "range" in v else {})} for k, v in self.vocab.keys.items()}

    def relay_tiers(self) -> dict:
        return {k: {"tier": p, "why": why} for k, (p, why) in self.tiers.priority.items()}

    def change_rules(self) -> dict:
        return {k: self.trends.text(k) for k in self.trends.keys()}

    def checklist_defs(self) -> dict:
        out = {aid: {"label": self.checklists.label(aid),
                     "items": [{"key": k, "label": lbl} for k, lbl in self.checklists.items(aid)],
                     "unknowns": self.checklists.unknowns(aid)} for aid in self.checklists.alerts}
        return out | {"_default_unknowns": list(self.checklists.default_unknowns)}

    def all(self) -> dict:
        return {
            "keys": self.keys(), "relay_tiers": self.relay_tiers(), "relay_budget_bytes": dict(self.tiers.budget),
            "change_rules": self.change_rules(), "checklists": self.checklist_defs(),
            "contradiction_keys": sorted(self.vocab.contradiction_keys),
            "county": self.counties.summary(), "counties": self.counties.available(),
            "enums": {"role": [r.value for r in Role], "captured_by": [c.value for c in CapturedBy],
                      "status": [s.value for s in Status]},
        }

    def files(self) -> dict[str, dict]:
        """File name under ui/public/contract/ -> content."""
        return {"keys.json": self.keys(), "relay_tiers.json": self.relay_tiers(),
                "change_rules.json": self.change_rules(), "checklists.json": self.checklist_defs()}
