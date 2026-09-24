"""Criteria scores: published or county criteria lists (2021 field triage, Santa Clara Policy 605, 700-A04 sepsis).

A definition names its groups (e.g. red, yellow) and lists criteria per group; each criterion is one rule from
rules.py plus its citation text. The result says which criteria are met, whether the definition's `met` groups have
any hit (`met`), whether every required input is present (`complete`), and what is missing. Nothing here decides a
destination or a treatment: the texts are the source's own words.
"""
from __future__ import annotations

from typing import Any, Optional

from .rules import Outcome, evaluate, rule_keys

# Result fields a group id may not reuse (each group's hits are listed under its own id).
_RESULT_FIELDS = {"name", "kind", "county", "applies", "met", "level", "flagged", "complete", "missing", "criteria",
                  "source", "thresholds"}

class CriteriaScore:
    def __init__(self, definition: dict):
        self.d = definition
        self.id, self.name = definition["id"], definition["name"]
        self.county: Optional[str] = definition.get("county")
        self.groups: list[dict] = definition["groups"]
        clash = {g["id"] for g in self.groups} & _RESULT_FIELDS
        if clash:
            raise ValueError(f"{self.id}: group ids {sorted(clash)} clash with result fields")

    # ---------- text ----------
    @staticmethod
    def _merged(c: dict, o: Outcome) -> dict:
        return {**c, **o.override}

    @staticmethod
    def _label(c: dict) -> str:
        return c.get("label", c.get("text", ""))

    def _hit_text(self, c: dict, o: Outcome) -> str:
        text = c.get("text", c.get("label", "")).format(**o.fields)
        return f"{text} ({c['finding'].format(**o.fields)})" if c.get("finding") else text

    def _needs(self, c: dict, o: Outcome) -> list[str]:
        """Labels for the inputs still missing under a rule (every undecided nested rule, even when the parent is
        already decided): its `needs` text, or a key -> label map."""
        if o.parts:
            return [x for r, p in o.parts for x in self._needs(self._merged(r, p), p)]
        if o.met is not None:
            return []
        needs = c.get("needs")
        if isinstance(needs, dict):
            return [needs.get(k, k) for k in o.needs] or list(dict.fromkeys(needs.values()))
        return [needs or self._label(c)]

    def _detail(self, c: dict, o: Outcome, group: Optional[str] = None) -> dict:
        state = {True: "met", False: "not_met", None: "unknown"}[o.met]
        row: dict[str, Any] = {"code": c.get("code"), "label": self._label(c), "state": state}
        if group:
            row["group"] = group
        if o.met is not None and c.get("finding"):
            row["finding"] = c["finding"].format(**o.fields)
        elif o.met and self._hit_text(c, o) != row["label"]:
            row["finding"] = self._hit_text(c, o)
        if o.met is None and not o.parts and c.get("needs"):
            row["needs"] = self._needs(c, o)
        if o.parts:
            row["parts"] = [self._detail(self._merged(r, p), p) for r, p in o.parts]
        return row

    @staticmethod
    def _decided_all(o: Outcome) -> bool:
        """The rule and every nested rule have all their inputs."""
        return o.met is not None and all(CriteriaScore._decided_all(p) for _, p in o.parts)

    # ---------- evaluation ----------
    def evaluate(self, values: dict[str, Any]) -> dict:
        hits: dict[str, list[str]] = {g["id"]: [] for g in self.groups}
        missing = [r["label"] for r in self.d.get("required", []) if values.get(r["key"]) is None]
        out = {"name": self.name, "kind": "criteria", "county": self.county, "applies": True, **hits,
               "met": False, "level": None, "flagged": False, "complete": False, "missing": missing,
               "criteria": [], "source": self.d["source"], "thresholds": self.d.get("thresholds_text")}
        gate = self.d.get("applies_when")
        if gate is not None and evaluate(gate, values).met is not True:
            out.update(applies=False, missing=[gate["needs"], *missing])
            return out
        complete = not missing
        for g in self.groups:
            for c in self.d.get(g["id"], []):
                o = evaluate(c, values)
                cm = self._merged(c, o)
                if o.met:
                    hits[g["id"]].append(self._hit_text(cm, o))
                if c.get("required") and not self._decided_all(o):
                    complete = False
                    missing.extend(x for x in self._needs(cm, o) if x not in missing)
                out["criteria"].append(self._detail(cm, o, g["id"]))
        met_groups = [g["id"] for g in self.groups if g.get("met") and hits[g["id"]]]
        out.update(hits, met=bool(met_groups), level=met_groups[0] if met_groups else None,
                   flagged=any(hits.values()), complete=complete, missing=missing)
        return out

    def input_keys(self) -> set[str]:
        keys = {r["key"] for r in self.d.get("required", [])}
        rules = [c for g in self.groups for c in self.d.get(g["id"], [])]
        if "applies_when" in self.d:
            rules.append(self.d["applies_when"])
        for c in rules:
            keys |= rule_keys(c)
        return keys

    def criteria_keys(self) -> list[tuple[str, set[str]]]:
        """(group id, the vocabulary keys the criterion reads) for every criterion, in the order of a result's
        `criteria` rows, so a met row can be traced back to the facts that decided it."""
        return [(g["id"], rule_keys(c)) for g in self.groups for c in self.d.get(g["id"], [])]

    # ---------- relay ----------
    def relay_text(self, result: dict) -> Optional[str]:
        """The line the relay sends: met criteria by group (codes) or met findings; `not met` only when complete."""
        fmt = self.d.get("relay_text")
        if not fmt or not result.get("applies", True):
            return None
        if result["met"] or (result["complete"] and result["flagged"]):
            by_group = "; ".join(f"{g.get('short', g['id'])} {_met_codes(result, g['id'])}"
                                 for g in self.groups if result[g["id"]])
            return fmt.format(by_group=by_group, leaves="; ".join(_met_leaves(result["criteria"])))
        return self.d.get("relay_text_not_met") if result["complete"] else None


def _met_codes(result: dict, group: str) -> str:
    return ", ".join(r["code"] for r in result["criteria"] if r.get("group") == group and r["state"] == "met")


def _met_leaves(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        if r["state"] != "met":
            continue
        out.extend(_met_leaves(r["parts"]) if r.get("parts") else [r.get("finding") or r["code"]])
    return out
