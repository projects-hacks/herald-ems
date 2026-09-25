"""The UI contract as plain data: labels, units, relay tiers, change rules, checklists, scores, county.

Served at GET /api/meta and exported to ui/public/contract/ by scripts/export_ui_contract.py; the screens use
it to name keys that are no longer in the snapshot. tests/test_contract.py keeps it in step.
"""
from __future__ import annotations

from ..core.schema import CapturedBy, Role, Status


class UIContract:
    def __init__(self, vocabulary, tiers, trends, checklists, counties, scales):
        self.vocab, self.tiers, self.trends, self.checklists = vocabulary, tiers, trends, checklists
        self.counties, self.scales = counties, scales

    def keys(self) -> dict:
        return {k: {**v, **({"range": list(v["range"])} if "range" in v else {})} for k, v in self.vocab.keys.items()}

    def relay_tiers(self) -> dict:
        return {k: {"tier": p, "why": why} for k, (p, why) in self.tiers.priority.items()}

    def change_rules(self) -> dict:
        return {k: self.trends.text(k) for k in self.trends.keys()}

    def checklist_defs(self) -> dict:
        """The active county's checklists (its overrides over the defaults)."""
        def item(i) -> dict:
            row = {"key": i.key, "label": i.label}
            row.update({k: v for k, v in (("note", i.note), ("source", i.source)) if v})
            if i.when is not None:
                row["conditional"] = True        # listed only when relevant (e.g. pregnancy weeks)
            return row

        out = {aid: {"label": self.checklists.label(aid), "source": self.checklists.source(aid),
                     "items": [item(i) for i in self.checklists.items(aid)],
                     "unknowns": self.checklists.unknowns(aid)} for aid in self.checklists.ids()}
        return out | {"_default_unknowns": list(self.checklists.default_unknowns)}

    def score_defs(self) -> dict:
        """Every score's name, kind, county (null = published) and source; criteria scores add their groups and
        each criterion's code and label, so a screen can name a criterion that isn't in the snapshot. A criterion
        that is decided by a plain `contains` rule over a list vocabulary key (e.g. trauma.criteria, "described
        in the county's own words") also carries `tap`: the exact key/value a medic's own tap can submit through
        the existing POST /api/facts, same as any other structured entry — never a new write path. Recall on
        speech-extracted criteria is low, so a screen renders these as a checklist, not just the ones already
        heard; a criterion with no `tap` (vitals, medications, computed values) has no one-tap way to record it
        here and stays read-only, sourced from its own capture flow."""
        out = {}
        for sid in self.scales.ids():
            s = self.scales[sid]
            row = {"name": s.name, "kind": s.d["kind"], "county": s.county, "source": s.d["source"],
                   "thresholds": s.d.get("thresholds_text"), "relay_key": f"score.{sid}"}
            if s.d["kind"] == "criteria":
                row["groups"] = [{k: g.get(k) for k in ("id", "label", "short", "met", "priority")} for g in s.groups]
                row["criteria"] = [x for g in s.groups for c in s.d.get(g["id"], []) for x in _criteria(c, g["id"], self.vocab)]
            out[sid] = row
        return out

    def all(self) -> dict:
        return {
            "keys": self.keys(), "relay_tiers": self.relay_tiers(), "relay_budget_bytes": dict(self.tiers.budget),
            "change_rules": self.change_rules(), "checklists": self.checklist_defs(), "scores": self.score_defs(),
            "contradiction_keys": sorted(self.vocab.contradiction_keys),
            "county": self.counties.summary(), "counties": self.counties.available(),
            "enums": {"role": [r.value for r in Role], "captured_by": [c.value for c in CapturedBy],
                      "status": [s.value for s in Status]},
        }

    def files(self) -> dict[str, dict]:
        """File name under ui/public/contract/ -> content."""
        return {"keys.json": self.keys(), "relay_tiers.json": self.relay_tiers(),
                "change_rules.json": self.change_rules(), "checklists.json": self.checklist_defs(),
                "scores.json": self.score_defs()}


def _tap(c: dict, vocab) -> dict | None:
    """A medic's tap can record this criterion iff it is decided by a plain `contains` rule over a list key that
    accumulates (config/vocabulary.yaml `merge: accumulate`): the exact value POST /api/facts should submit."""
    if c.get("type") != "contains":
        return None
    meta = vocab.meta(c["key"]) if c["key"] in vocab else None
    if not meta or meta.get("type") != "list" or meta.get("merge") != "accumulate":
        return None
    return {"key": c["key"], "value": c["value"]}


def _criteria(c: dict, group: str, vocab, parent=None) -> list[dict]:
    """A criterion and its nested rules, flattened (`parent` = the enclosing criterion's code)."""
    row = {"group": group, "code": c.get("code"), "label": c.get("label", c.get("text")), "parent": parent}
    tap = _tap(c, vocab)
    if tap:
        row["tap"] = tap
    rows = [row]
    for b in c.get("bands", ()):                     # age bands of one criterion (Policy 605 N.1-N.3)
        rows.append({"group": group, "code": b.get("code"), "label": b.get("label", b.get("text")),
                     "parent": c.get("code")})
    for r in c.get("rules", ()):
        rows.extend(_criteria(r, group, vocab, c.get("code")))
    return rows
